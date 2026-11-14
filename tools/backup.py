from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable, Mapping


class BackupError(ValueError):
    """A backup cannot be created or trusted without operator intervention."""


_DATABASE_ALIAS = re.compile(r"[a-z][a-z0-9_-]{0,62}")
_DEFAULT_OPTIONAL_DATABASES = ("general_furniture", "history")


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
        with closing(
            sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        ) as database:
            result = database.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error as exc:
        raise BackupError("invalid_database") from exc
    if result != ("ok",):
        raise BackupError("invalid_database")


def _snapshot_database(source_path: Path, snapshot: Path) -> None:
    try:
        with (
            closing(sqlite3.connect(source_path)) as source,
            closing(sqlite3.connect(snapshot)) as target,
        ):
            source.backup(target)
    except sqlite3.Error as exc:
        raise BackupError("invalid_database") from exc
    _validate_database(snapshot)


def _database_sources(
    data_dir: Path, databases: Mapping[str, Path] | None
) -> dict[str, Path]:
    sources = {"vexplorer": (data_dir / "vexplorer.sqlite3").resolve()}
    explicit = databases or {}
    for alias, path in explicit.items():
        if not _DATABASE_ALIAS.fullmatch(alias) or alias == "vexplorer":
            raise BackupError("invalid_database_alias")
        sources[alias] = Path(path).resolve()
    for alias in _DEFAULT_OPTIONAL_DATABASES:
        default_path = (data_dir / f"{alias}.sqlite3").resolve()
        if alias not in sources and default_path.is_file():
            sources[alias] = default_path

    resolved_paths: set[Path] = set()
    for path in sources.values():
        if not path.is_file():
            raise BackupError("database_not_found")
        if path in resolved_paths:
            raise BackupError("duplicate_database_path")
        resolved_paths.add(path)
    return sources


def create_backup(
    data_dir: Path,
    archive: Path,
    *,
    databases: Mapping[str, Path] | None = None,
) -> Path:
    data_dir = data_dir.resolve()
    archive = archive.resolve()
    database_sources = _database_sources(data_dir, databases)
    if archive.exists():
        raise BackupError("archive_exists")
    archive.parent.mkdir(parents=True, exist_ok=True)

    temporary_archive = archive.with_name(f".{archive.name}.{os.getpid()}.tmp")
    if temporary_archive.exists():
        temporary_archive.unlink()
    try:
        with tempfile.TemporaryDirectory(prefix="vexplorer-backup-") as temporary:
            staging = Path(temporary)
            payloads: list[tuple[Path, str]] = []
            for alias, database_path in sorted(database_sources.items()):
                snapshot = staging / f"{alias}.sqlite3"
                _snapshot_database(database_path, snapshot)
                payloads.append((snapshot, f"database/{alias}.sqlite3"))
            documents_dir = data_dir / "documents"
            for document in _document_files(documents_dir):
                relative = document.relative_to(documents_dir).as_posix()
                payloads.append((document, f"documents/{relative}"))

            manifest = {
                "format": "vexplorer-backup-v2",
                "created_at": datetime.now(UTC).isoformat(),
                "files": [_manifest_entry(path, name) for path, name in payloads],
            }
            with zipfile.ZipFile(
                temporary_archive,
                "x",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as output:
                output.writestr(
                    "manifest.json", json.dumps(manifest, sort_keys=True, indent=2)
                )
                for path, name in payloads:
                    output.write(path, name)
        os.replace(temporary_archive, archive)
    except Exception:
        temporary_archive.unlink(missing_ok=True)
        raise
    return archive


def _load_and_validate_archive(
    archive: Path,
) -> tuple[dict[str, object], zipfile.ZipFile]:
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
        if not isinstance(manifest, dict) or manifest.get("format") not in {
            "vexplorer-backup-v1",
            "vexplorer-backup-v2",
        }:
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
        database_names = [
            name for name in manifest_names if name.startswith("database/")
        ]
        if manifest["format"] == "vexplorer-backup-v1":
            if database_names != ["database/vexplorer.sqlite3"]:
                raise BackupError("invalid_archive_members")
        else:
            for name in database_names:
                parts = PurePosixPath(name).parts
                if len(parts) != 2 or not parts[1].endswith(".sqlite3"):
                    raise BackupError("invalid_database_alias")
                alias = parts[1][:-8]
                if not _DATABASE_ALIAS.fullmatch(alias):
                    raise BackupError("invalid_database_alias")
        for name in manifest_names:
            parts = PurePosixPath(name).parts
            if name.startswith("database/"):
                continue
            if len(parts) < 2 or parts[0] != "documents":
                raise BackupError("invalid_archive_members")
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
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-restore-", dir=destination.parent)
    )
    try:
        files = manifest["files"]
        assert isinstance(files, list)
        backup_format = manifest["format"]
        assert isinstance(backup_format, str)
        for item in files:
            assert isinstance(item, dict)
            name = item["path"]
            assert isinstance(name, str)
            archive_info = backup.getinfo(name)
            if name.startswith("database/"):
                if backup_format == "vexplorer-backup-v1":
                    output_relative = Path("vexplorer.sqlite3")
                else:
                    output_relative = Path(PurePosixPath(name).name)
            else:
                output_relative = Path(*PurePosixPath(name).parts)
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
        for database in staging.glob("*.sqlite3"):
            _validate_database(database)
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
    parser = argparse.ArgumentParser(
        description="Create or restore verified Vexplorer backups."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--data-dir", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument(
        "--database",
        action="append",
        default=[],
        metavar="ALIAS=PATH",
        help="Additional SQLite store (repeatable), for example history=/srv/history.sqlite3.",
    )
    restore = commands.add_parser("restore")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "create":
        databases: dict[str, Path] = {}
        for value in args.database:
            alias, separator, path = value.partition("=")
            if not separator or not path or alias in databases:
                raise BackupError("invalid_database_alias")
            databases[alias] = Path(path)
        result = create_backup(args.data_dir, args.output, databases=databases)
    else:
        result = restore_backup(args.archive, args.destination)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
