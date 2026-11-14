"""Create verified scheduled backups and prune only older scheduled archives."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import shutil
import sqlite3

from tools.backup import create_backup, verify_backup


@dataclass(frozen=True)
class ScheduledBackupResult:
    archive: Path
    sha256: str
    size_bytes: int
    pruned: tuple[Path, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_scheduled_backup(
    data_dir: Path,
    output_dir: Path,
    *,
    keep: int = 14,
    now: datetime | None = None,
    quiescent: bool = False,
    max_total_bytes: int = 2 * 1024 * 1024 * 1024,
    min_free_bytes: int = 1024 * 1024 * 1024,
) -> ScheduledBackupResult:
    if not quiescent:
        raise RuntimeError("backup_requires_quiescence")
    if keep <= 0 or keep > 365:
        raise ValueError("backup_retention_invalid")
    if max_total_bytes <= 0 or min_free_bytes < 0:
        raise ValueError("backup_storage_budget_invalid")
    if active_job_count(data_dir):
        raise RuntimeError("backup_active_jobs")
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_bytes = sum(
        path.stat().st_size
        for path in data_dir.resolve().rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    if shutil.disk_usage(output_dir).free < min_free_bytes + source_bytes:
        raise RuntimeError("backup_free_space_guard")
    archive = output_dir / f"scheduled-{timestamp:%Y%m%dT%H%M%SZ}.zip"
    create_backup(data_dir, archive, quiescent=True)
    try:
        verify_backup(archive)
    except Exception:
        archive.unlink(missing_ok=True)
        raise

    scheduled = sorted(
        (
            path
            for path in output_dir.glob("scheduled-????????T??????Z.zip")
            if path.is_file() and not path.is_symlink()
        ),
        key=lambda path: path.name,
    )
    if archive.stat().st_size > max_total_bytes:
        archive.unlink()
        raise RuntimeError("backup_exceeds_total_budget")
    retained = list(scheduled)
    pruned_values: list[Path] = []
    total_bytes = sum(path.stat().st_size for path in retained)
    while len(retained) > keep or total_bytes > max_total_bytes:
        candidate = retained[0]
        if candidate == archive and len(retained) == 1:
            archive.unlink()
            raise RuntimeError("backup_exceeds_total_budget")
        retained.pop(0)
        total_bytes -= candidate.stat().st_size
        pruned_values.append(candidate)
    pruned = tuple(pruned_values)
    for path in pruned:
        path.unlink()
    return ScheduledBackupResult(
        archive=archive,
        sha256=_sha256(archive),
        size_bytes=archive.stat().st_size,
        pruned=pruned,
    )


def active_job_count(data_dir: Path) -> int:
    database_path = data_dir.resolve() / "vexplorer.sqlite3"
    if not database_path.is_file():
        raise RuntimeError("backup_database_not_found")
    try:
        with sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=ro", uri=True
        ) as database:
            table = database.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'"
            ).fetchone()
            if table is None:
                return 0
            return int(database.execute(
                "SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')"
            ).fetchone()[0])
    except sqlite3.Error as exc:
        raise RuntimeError("backup_job_check_failed") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--keep", type=int, default=14)
    parser.add_argument("--max-total-bytes", type=int, default=2 * 1024 * 1024 * 1024)
    parser.add_argument("--min-free-bytes", type=int, default=1024 * 1024 * 1024)
    parser.add_argument("--check-idle-only", action="store_true")
    parser.add_argument("--quiescent", action="store_true")
    args = parser.parse_args()
    active = active_job_count(args.data_dir)
    if args.check_idle_only:
        return 75 if active else 0
    result = create_scheduled_backup(
        args.data_dir,
        args.output_dir,
        keep=args.keep,
        quiescent=args.quiescent,
        max_total_bytes=args.max_total_bytes,
        min_free_bytes=args.min_free_bytes,
    )
    print(
        f"archive={result.archive} sha256={result.sha256} "
        f"size={result.size_bytes} pruned={len(result.pruned)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
