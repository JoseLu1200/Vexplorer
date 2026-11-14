from __future__ import annotations

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
    (documents / "doc-a.dxf").write_bytes(b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n")
    connection = sqlite3.connect(root / "vexplorer.sqlite3")
    connection.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, state TEXT NOT NULL)")
    connection.execute("INSERT INTO runs VALUES (?, ?)", ("run-1", "completed"))
    connection.commit()
    return connection


def test_backup_snapshots_live_sqlite_and_documents_and_restores_new_data_dir(tmp_path: Path) -> None:
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
        assert database.execute("SELECT id, state FROM runs").fetchall() == [("run-1", "completed")]
    assert (restored / "documents" / "doc-a.dxf").read_bytes().endswith(b"EOF\n")

    with zipfile.ZipFile(archive) as backup:
        manifest = json.loads(backup.read("manifest.json"))
    assert manifest["format"] == "vexplorer-backup-v1"
    assert {item["path"] for item in manifest["files"]} == {
        "database/vexplorer.sqlite3",
        "documents/doc-a.dxf",
    }
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])


def test_restore_rejects_hash_mismatch_without_creating_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    connection = _create_live_data_dir(source)
    connection.close()
    archive = tmp_path / "backup.zip"
    create_backup(source, archive)

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(tampered, "w") as output:
        for info in original.infolist():
            payload = original.read(info.filename)
            output.writestr(info, b"x" * len(payload) if info.filename.endswith(".dxf") else payload)

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


def test_users_file_contains_named_scrypt_hashes_and_is_replaced_atomically(tmp_path: Path) -> None:
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
        write_users_file(tmp_path / "users.json", {username: hash_password("valid password")})
