from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from tools.backup import BackupError, create_backup, restore_backup
from tools.manage_users import hash_password, verify_password, write_users_file


def _create_live_data_dir(root: Path) -> sqlite3.Connection:
    root.mkdir()
    documents = root / "documents"
    documents.mkdir()
    (documents / "doc-a.dxf").write_bytes(
        b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"
    )
    connection = sqlite3.connect(root / "vexplorer.sqlite3")
    connection.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, state TEXT NOT NULL)")
    connection.execute("INSERT INTO runs VALUES (?, ?)", ("run-1", "completed"))
    connection.commit()
    return connection


def test_backup_snapshots_live_sqlite_and_documents_and_restores_new_data_dir(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    connection = _create_live_data_dir(source)
    archive = tmp_path / "backup.zip"

    create_backup(source, archive)
    connection.execute("INSERT INTO runs VALUES (?, ?)", ("run-after", "completed"))
    connection.commit()
    connection.close()

    restored = tmp_path / "restored"
    restore_backup(archive, restored)

    with sqlite3.connect(restored / "vexplorer.sqlite3") as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert database.execute("SELECT id, state FROM runs").fetchall() == [
            ("run-1", "completed")
        ]
    assert (restored / "documents" / "doc-a.dxf").read_bytes().endswith(b"EOF\n")

    with zipfile.ZipFile(archive) as backup:
        manifest = json.loads(backup.read("manifest.json"))
    assert manifest["format"] == "vexplorer-backup-v2"
    assert {item["path"] for item in manifest["files"]} == {
        "database/vexplorer.sqlite3",
        "documents/doc-a.dxf",
    }
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])


def test_backup_snapshots_all_live_sqlite_stores_and_document_derivatives(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    primary = _create_live_data_dir(source)
    documents = source / "documents" / "doc-multiformat"
    documents.mkdir()
    (documents / "original.pdf").write_bytes(b"%PDF-1.7\nfixture\n")
    (documents / "original.dwg").write_bytes(b"AC1032 fixture")
    (documents / "preview.svg").write_text("<svg/>", encoding="utf-8")
    (documents / "conversion.json").write_text(
        '{"converter":"oda_file_converter","source_sha256":"abc"}', encoding="utf-8"
    )

    stores: list[sqlite3.Connection] = []
    for filename, table, row in (
        ("general_furniture.sqlite3", "proposals", ("proposal-1", "confirmed")),
        ("history.sqlite3", "historical_records", ("record-1", "EUR")),
    ):
        database = sqlite3.connect(source / filename)
        database.execute("PRAGMA journal_mode=WAL")
        database.execute(
            f"CREATE TABLE {table} (id TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        database.execute(f"INSERT INTO {table} VALUES (?, ?)", row)
        database.commit()
        stores.append(database)

    archive = tmp_path / "backup.zip"
    create_backup(source, archive)
    restored = tmp_path / "restored"
    restore_backup(archive, restored)

    primary.close()
    for database in stores:
        database.close()

    with sqlite3.connect(restored / "general_furniture.sqlite3") as database:
        assert database.execute("SELECT * FROM proposals").fetchall() == [
            ("proposal-1", "confirmed")
        ]
    with sqlite3.connect(restored / "history.sqlite3") as database:
        assert database.execute("SELECT * FROM historical_records").fetchall() == [
            ("record-1", "EUR")
        ]
    assert (
        (restored / "documents" / "doc-multiformat" / "original.pdf")
        .read_bytes()
        .startswith(b"%PDF")
    )
    assert (
        (restored / "documents" / "doc-multiformat" / "original.dwg")
        .read_bytes()
        .startswith(b"AC1032")
    )
    assert (restored / "documents" / "doc-multiformat" / "preview.svg").read_text(
        encoding="utf-8"
    ) == "<svg/>"
    assert (
        json.loads(
            (restored / "documents" / "doc-multiformat" / "conversion.json").read_text(
                encoding="utf-8"
            )
        )["converter"]
        == "oda_file_converter"
    )


def test_backup_accepts_explicit_external_store_and_restores_by_safe_alias(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    primary = _create_live_data_dir(source)
    primary.close()
    external = tmp_path / "external.sqlite3"
    with sqlite3.connect(external) as database:
        database.execute("CREATE TABLE records (id TEXT PRIMARY KEY)")
        database.execute("INSERT INTO records VALUES ('external-1')")

    archive = tmp_path / "backup.zip"
    create_backup(source, archive, databases={"history": external})
    restored = tmp_path / "restored"
    restore_backup(archive, restored)

    with sqlite3.connect(restored / "history.sqlite3") as database:
        assert database.execute("SELECT id FROM records").fetchall() == [
            ("external-1",)
        ]


@pytest.mark.parametrize(
    "alias", ["", ".", "../history", "history/db", "C:history", "histórico"]
)
def test_backup_rejects_invalid_database_aliases(tmp_path: Path, alias: str) -> None:
    source = tmp_path / "source"
    primary = _create_live_data_dir(source)
    primary.close()

    with pytest.raises(BackupError, match="invalid_database_alias"):
        create_backup(
            source,
            tmp_path / "backup.zip",
            databases={alias: source / "vexplorer.sqlite3"},
        )


def test_backup_rejects_two_aliases_for_same_database_path(tmp_path: Path) -> None:
    source = tmp_path / "source"
    primary = _create_live_data_dir(source)
    primary.close()

    with pytest.raises(BackupError, match="duplicate_database_path"):
        create_backup(
            source,
            tmp_path / "backup.zip",
            databases={"history": source / "vexplorer.sqlite3"},
        )


def test_backup_rejects_invalid_additional_database_without_publishing_archive(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    primary = _create_live_data_dir(source)
    primary.close()
    invalid = tmp_path / "invalid.sqlite3"
    invalid.write_bytes(b"not a sqlite database")
    archive = tmp_path / "backup.zip"

    with pytest.raises(BackupError, match="invalid_database"):
        create_backup(source, archive, databases={"history": invalid})

    assert not archive.exists()


def test_restore_accepts_previous_v1_backup_and_queries_data(tmp_path: Path) -> None:
    legacy_database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(legacy_database) as database:
        database.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, state TEXT NOT NULL)")
        database.execute("INSERT INTO runs VALUES ('legacy-run', 'completed')")
    payload = legacy_database.read_bytes()
    manifest = {
        "format": "vexplorer-backup-v1",
        "created_at": "2026-11-14T00:00:00+00:00",
        "files": [
            {
                "path": "database/vexplorer.sqlite3",
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
    }
    archive = tmp_path / "legacy-v1.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        output.writestr("database/vexplorer.sqlite3", payload)

    restored = tmp_path / "restored"
    restore_backup(archive, restored)

    with sqlite3.connect(restored / "vexplorer.sqlite3") as database:
        assert database.execute("SELECT id, state FROM runs").fetchall() == [
            ("legacy-run", "completed")
        ]


@pytest.mark.parametrize(
    "backup_format,extra_name",
    [
        ("vexplorer-backup-v1", "database/history.sqlite3"),
        ("vexplorer-backup-v2", "unexpected/payload.bin"),
    ],
)
def test_restore_rejects_database_aliases_in_v1_and_unknown_payload_namespaces(
    tmp_path: Path, backup_format: str, extra_name: str
) -> None:
    database_path = tmp_path / "source.sqlite3"
    with sqlite3.connect(database_path) as database:
        database.execute("CREATE TABLE data (id TEXT PRIMARY KEY)")
    payload = database_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    files = [
        {
            "path": "database/vexplorer.sqlite3",
            "size": len(payload),
            "sha256": digest,
        },
        {"path": extra_name, "size": len(payload), "sha256": digest},
    ]
    archive = tmp_path / "invalid-members.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "manifest.json", json.dumps({"format": backup_format, "files": files})
        )
        for item in files:
            output.writestr(item["path"], payload)

    destination = tmp_path / "restored"
    with pytest.raises(BackupError, match="invalid_archive_members"):
        restore_backup(archive, destination)
    assert not destination.exists()


def test_restore_rejects_hash_mismatch_without_creating_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    connection = _create_live_data_dir(source)
    connection.close()
    archive = tmp_path / "backup.zip"
    create_backup(source, archive)

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(tampered, "w") as output:
        for info in original.infolist():
            payload = original.read(info.filename)
            output.writestr(
                info, b"x" * len(payload) if info.filename.endswith(".dxf") else payload
            )

    destination = tmp_path / "restored"
    with pytest.raises(BackupError, match="hash_mismatch"):
        restore_backup(tampered, destination)
    assert not destination.exists()


@pytest.mark.parametrize(
    "unsafe_name",
    ["../escape", "/absolute", "C:/windows", "C:\\windows", "documents/../escape"],
)
def test_restore_rejects_unsafe_zip_paths_including_windows_forms(
    tmp_path: Path, unsafe_name: str
) -> None:
    archive = tmp_path / "unsafe.zip"
    manifest = {
        "format": "vexplorer-backup-v1",
        "files": [{"path": unsafe_name, "size": 1, "sha256": "0" * 64}],
    }
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        output.writestr(unsafe_name, b"x")

    destination = tmp_path / "restored"
    with pytest.raises(BackupError, match="unsafe_archive_path"):
        restore_backup(archive, destination)
    assert not destination.exists()


def test_restore_never_overwrites_existing_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    connection = _create_live_data_dir(source)
    connection.close()
    archive = tmp_path / "backup.zip"
    create_backup(source, archive)
    destination = tmp_path / "restored"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(BackupError, match="destination_exists"):
        restore_backup(archive, destination)
    assert marker.read_text(encoding="utf-8") == "keep"


def test_users_file_contains_named_scrypt_hashes_and_is_replaced_atomically(
    tmp_path: Path,
) -> None:
    users_file = tmp_path / "users.json"
    encoded = hash_password("correct horse battery staple")
    write_users_file(users_file, {"operador.1": encoded})

    stored = json.loads(users_file.read_text(encoding="utf-8"))
    assert set(stored) == {"operador.1"}
    assert stored["operador.1"].startswith("$scrypt$ln=14,r=8,p=1$")
    assert "correct horse" not in users_file.read_text(encoding="utf-8")
    assert verify_password("correct horse battery staple", stored["operador.1"])
    assert not verify_password("incorrect", stored["operador.1"])


def test_user_hash_rejects_password_backend_cannot_authenticate() -> None:
    with pytest.raises(ValueError, match="invalid_password"):
        hash_password("á" * 513)


@pytest.mark.parametrize("username", ["", ".admin", "space user", "a" * 65, "álvaro"])
def test_users_file_rejects_invalid_usernames(tmp_path: Path, username: str) -> None:
    with pytest.raises(ValueError, match="invalid_username"):
        write_users_file(
            tmp_path / "users.json", {username: hash_password("valid password")}
        )
