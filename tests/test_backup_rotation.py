from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3

from tools.backup import BackupError, create_backup
from tools.backup_rotate import create_scheduled_backup
from tools.backup_rotate import active_job_count


def _data_dir(root: Path) -> Path:
    root.mkdir()
    with sqlite3.connect(root / "vexplorer.sqlite3") as database:
        database.execute("CREATE TABLE runs(id TEXT PRIMARY KEY)")
        database.execute("INSERT INTO runs VALUES('run-1')")
    return root


def test_scheduled_backup_is_verified_and_prunes_only_its_own_old_archives(
    tmp_path: Path,
) -> None:
    data_dir = _data_dir(tmp_path / "data")
    output_dir = tmp_path / "backups"
    output_dir.mkdir()
    preserved = output_dir / "accepted-manual.zip"
    preserved.write_bytes(b"operator-owned")
    for day in range(1, 4):
        (output_dir / f"scheduled-2026110{day}T030000Z.zip").write_bytes(b"old")

    result = create_scheduled_backup(
        data_dir,
        output_dir,
        keep=2,
        quiescent=True,
        now=datetime(2026, 11, 14, 3, 30, tzinfo=timezone.utc),
    )

    assert result.archive.name == "scheduled-20261114T033000Z.zip"
    assert result.archive.exists()
    assert len(result.sha256) == 64
    assert result.size_bytes > 0
    assert [item.name for item in result.pruned] == [
        "scheduled-20261101T030000Z.zip",
        "scheduled-20261102T030000Z.zip",
    ]
    assert preserved.read_bytes() == b"operator-owned"
    assert sorted(path.name for path in output_dir.glob("scheduled-*.zip")) == [
        "scheduled-20261103T030000Z.zip",
        "scheduled-20261114T033000Z.zip",
    ]


def test_scheduled_backup_refuses_nonpositive_retention(tmp_path: Path) -> None:
    data_dir = _data_dir(tmp_path / "data")

    try:
        create_scheduled_backup(
            data_dir, tmp_path / "backups", keep=0, quiescent=True
        )
    except ValueError as exc:
        assert str(exc) == "backup_retention_invalid"
    else:
        raise AssertionError("expected invalid retention to fail closed")


def test_scheduled_backup_requires_quiescence_and_no_active_jobs(
    tmp_path: Path,
) -> None:
    data_dir = _data_dir(tmp_path / "data")
    with sqlite3.connect(data_dir / "vexplorer.sqlite3") as database:
        database.execute(
            "CREATE TABLE jobs(id TEXT PRIMARY KEY, state TEXT NOT NULL)"
        )
        database.execute("INSERT INTO jobs VALUES('job-1','running')")

    assert active_job_count(data_dir) == 1
    try:
        create_scheduled_backup(
            data_dir, tmp_path / "backups", quiescent=True,
        )
    except RuntimeError as exc:
        assert str(exc) == "backup_active_jobs"
    else:
        raise AssertionError("expected active jobs to defer backup")

    try:
        create_scheduled_backup(data_dir, tmp_path / "backups")
    except RuntimeError as exc:
        assert str(exc) == "backup_requires_quiescence"
    else:
        raise AssertionError("expected missing quiescence to fail closed")


def test_scheduled_backup_defers_while_reconstruction_job_is_running(
    tmp_path: Path,
) -> None:
    data_dir = _data_dir(tmp_path / "data")
    reconstruction = data_dir / "reconstruction" / ("c" * 32)
    reconstruction.mkdir(parents=True)
    (reconstruction / "status.json").write_text(
        '{"job_id":"cccccccccccccccccccccccccccccccc","status":"running"}',
        encoding="utf-8",
    )

    assert active_job_count(data_dir) == 1
    try:
        create_scheduled_backup(
            data_dir, tmp_path / "backups", quiescent=True,
        )
    except RuntimeError as exc:
        assert str(exc) == "backup_active_jobs"
    else:
        raise AssertionError("expected running reconstruction to defer backup")


def test_scheduled_backup_refuses_when_free_space_guard_is_not_met(
    tmp_path: Path, monkeypatch
) -> None:
    data_dir = _data_dir(tmp_path / "data")
    output_dir = tmp_path / "backups"
    output_dir.mkdir()
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(total=10_000, used=9_500, free=500),
    )

    try:
        create_scheduled_backup(
            data_dir, output_dir, quiescent=True, min_free_bytes=1_000,
        )
    except RuntimeError as exc:
        assert str(exc) == "backup_free_space_guard"
    else:
        raise AssertionError("expected low free space to fail closed")


def test_scheduled_backup_prunes_to_total_byte_budget(tmp_path: Path) -> None:
    data_dir = _data_dir(tmp_path / "data")
    output_dir = tmp_path / "backups"
    first = create_scheduled_backup(
        data_dir, output_dir, keep=14, quiescent=True,
        min_free_bytes=0,
        now=datetime(2026, 11, 13, 3, 30, tzinfo=timezone.utc),
    )
    old_copy = output_dir / "scheduled-20261112T033000Z.zip"
    old_copy.write_bytes(first.archive.read_bytes())

    second = create_scheduled_backup(
        data_dir, output_dir, keep=14, quiescent=True,
        min_free_bytes=0,
        max_total_bytes=first.size_bytes * 2,
        now=datetime(2026, 11, 14, 3, 30, tzinfo=timezone.utc),
    )

    assert second.archive.exists()
    assert sum(path.stat().st_size for path in output_dir.glob("scheduled-*.zip")) <= first.size_bytes * 2
    assert old_copy in second.pruned


def test_quiescent_snapshot_opens_source_sqlite_immutable_read_only(
    tmp_path: Path, monkeypatch
) -> None:
    data_dir = _data_dir(tmp_path / "data")
    calls: list[tuple[object, bool]] = []
    real_connect = sqlite3.connect

    def recording_connect(database, *args, **kwargs):
        calls.append((database, bool(kwargs.get("uri"))))
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    create_scheduled_backup(
        data_dir, tmp_path / "backups", quiescent=True, min_free_bytes=0,
    )

    assert any(
        isinstance(database, str)
        and "mode=ro&immutable=1" in database
        and uri
        for database, uri in calls
    )


def test_quiescent_backup_rejects_committed_rows_still_present_in_wal(
    tmp_path: Path,
) -> None:
    data_dir = _data_dir(tmp_path / "data")
    database_path = data_dir / "vexplorer.sqlite3"
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("INSERT INTO runs VALUES('committed-only-in-wal')")
        connection.commit()
        wal = Path(f"{database_path}-wal")
        assert wal.stat().st_size > 0

        try:
            create_backup(
                data_dir, tmp_path / "must-not-exist.zip", quiescent=True
            )
        except BackupError as exc:
            assert str(exc) == "quiescent_database_has_uncheckpointed_sidecar"
        else:
            raise AssertionError("immutable backup must not ignore committed WAL rows")
        assert not (tmp_path / "must-not-exist.zip").exists()
    finally:
        connection.close()
