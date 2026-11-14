from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable


class BackupError(ValueError):
    """A backup cannot be created or trusted without operator intervention."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_entry(path: Path, archive_path: str) -> dict[str, object]:
    return {"path": archive_path, "size": path.stat().st_size, "sha256": _sha256(path)}


def _safe_archive_path(value: str) -> bool:
    if not value or "\\" in value or "\x00" in value:
        return False
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return (
        not posix.is_absolute()
        and not windows.is_absolute()
        and windows.drive == ""
        and all(part not in ("", ".", "..") for part in posix.parts)
    )


def _document_files(documents_dir: Path) -> Iterable[Path]:
    if not documents_dir.exists():
        return ()
    files: list[Path] = []
    for candidate in sorted(documents_dir.rglob("*")):
        if candidate.is_symlink():
            raise BackupError("document_symlink_not_allowed")
        if candidate.is_file():
            files.append(candidate)
    return files


def _validate_database(path: Path) -> None:
    try:
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as database:
            result = database.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error as exc:
        raise BackupError("invalid_database") from exc
    if result != ("ok",):
        raise BackupError("invalid_database")


def create_backup(data_dir: Path, archive: Path) -> Path:
    data_dir = data_dir.resolve()
    database_path = data_dir / "vexplorer.sqlite3"
    archive = archive.resolve()
    if not database_path.is_file():
        raise BackupError("database_not_found")
    if archive.exists():
        raise BackupError("archive_exists")
    archive.parent.mkdir(parents=True, exist_ok=True)

    temporary_archive = archive.with_name(f".{archive.name}.{os.getpid()}.tmp")
    if temporary_archive.exists():
        temporary_archive.unlink()
    try:
        with tempfile.TemporaryDirectory(prefix="vexplorer-backup-") as temporary:
            staging = Path(temporary)
            snapshot = staging / "vexplorer.sqlite3"
            with closing(sqlite3.connect(database_path)) as source, closing(
                sqlite3.connect(snapshot)
            ) as target:
                source.backup(target)
            _validate_database(snapshot)

            payloads: list[tuple[Path, str]] = [(snapshot, "database/vexplorer.sqlite3")]
            documents_dir = data_dir / "documents"
            for document in _document_files(documents_dir):
                relative = document.relative_to(documents_dir).as_posix()
                payloads.append((document, f"documents/{relative}"))

            manifest = {
                "format": "vexplorer-backup-v1",
                "created_at": datetime.now(UTC).isoformat(),
                "files": [_manifest_entry(path, name) for path, name in payloads],
            }
            with zipfile.ZipFile(
                temporary_archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as output:
                output.writestr("manifest.json", json.dumps(manifest, sort_keys=True, indent=2))
                for path, name in payloads:
                    output.write(path, name)
        os.replace(temporary_archive, archive)
    except Exception:
        temporary_archive.unlink(missing_ok=True)
        raise
    return archive


def _load_and_validate_archive(archive: Path) -> tuple[dict[str, object], zipfile.ZipFile]:
    try:
        backup = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BackupError("invalid_archive") from exc
    try:
        infos = backup.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)) or names.count("manifest.json") != 1:
            raise BackupError("invalid_archive_members")
        if any(not _safe_archive_path(name) for name in names):
            raise BackupError("unsafe_archive_path")
        for info in infos:
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise BackupError("unsafe_archive_path")
        manifest = json.loads(backup.read("manifest.json"))
        if not isinstance(manifest, dict) or manifest.get("format") != "vexplorer-backup-v1":
            raise BackupError("unsupported_backup_format")
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise BackupError("invalid_manifest")
        manifest_names: list[str] = []
        for item in files:
            if not isinstance(item, dict):
                raise BackupError("invalid_manifest")
            name = item.get("path")
            if not isinstance(name, str) or not _safe_archive_path(name):
                raise BackupError("unsafe_archive_path")
            if not isinstance(item.get("size"), int) or item["size"] < 0:
                raise BackupError("invalid_manifest")
            digest = item.get("sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                raise BackupError("invalid_manifest")
            manifest_names.append(name)
        if len(manifest_names) != len(set(manifest_names)):
            raise BackupError("invalid_manifest")
        if set(names) != {"manifest.json", *manifest_names}:
            raise BackupError("invalid_archive_members")
        if "database/vexplorer.sqlite3" not in manifest_names:
            raise BackupError("database_not_found")
        return manifest, backup
    except Exception:
        backup.close()
        raise


def restore_backup(archive: Path, destination: Path) -> Path:
    archive = archive.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise BackupError("destination_exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest, backup = _load_and_validate_archive(archive)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-restore-", dir=destination.parent))
    try:
        files = manifest["files"]
        assert isinstance(files, list)
        for item in files:
            assert isinstance(item, dict)
            name = item["path"]
            assert isinstance(name, str)
            archive_info = backup.getinfo(name)
            output_relative = (
                Path("vexplorer.sqlite3")
                if name == "database/vexplorer.sqlite3"
                else Path(*PurePosixPath(name).parts)
            )
            output_path = staging / output_relative
            output_path.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            written = 0
            with backup.open(archive_info) as source, output_path.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    written += len(chunk)
                    if written > item["size"]:
                        raise BackupError("size_mismatch")
                    digest.update(chunk)
                    output.write(chunk)
            if written != item["size"]:
                raise BackupError("size_mismatch")
            if digest.hexdigest() != item["sha256"]:
                raise BackupError("hash_mismatch")
        _validate_database(staging / "vexplorer.sqlite3")
        if destination.exists():
            raise BackupError("destination_exists")
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        backup.close()
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or restore verified Vexplorer backups.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--data-dir", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "create":
        result = create_backup(args.data_dir, args.output)
    else:
        result = restore_backup(args.archive, args.destination)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
