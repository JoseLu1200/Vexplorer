"""Build a deterministic, local-only Vexplorer runtime archive.

The archive snapshots the allowlisted working-tree bytes, including reviewed
uncommitted runtime changes. It never reads deployment state, data, references,
environment files or ``.runtime``.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


_REQUIRED = (
    "backend/__init__.py",
    "backend/app/ingesta/README.md",
    "backend/app/main.py",
    "deploy/SYSTEMD_RELEASE.md",
    "deploy/requirements-runtime.txt",
    "deploy/systemd-production.env.example",
    "deploy/systemd-user/vexplorer-backup.service",
    "deploy/systemd-user/vexplorer-backup.timer",
    "deploy/systemd-user/vexplorer.service",
    "frontend/api/client.js",
    "frontend/app.js",
    "frontend/index.html",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/styles.css",
    "frontend/vendor/three/LICENSE",
    "frontend/vendor/three/addons/controls/OrbitControls.js",
    "frontend/vendor/three/three.core.js",
    "frontend/vendor/three/three.module.js",
    "pyproject.toml",
    "requirements-demo.txt",
    "tools/__init__.py",
    "tools/backup.py",
    "tools/backup_rotate.py",
    "tools/manage_users.py",
)
_ROOT_FILES = (
    "backend/__init__.py",
    "backend/app/ingesta/README.md",
    "deploy/SYSTEMD_RELEASE.md",
    "deploy/requirements-runtime.txt",
    "deploy/systemd-production.env.example",
    "deploy/systemd-user/vexplorer-backup.service",
    "deploy/systemd-user/vexplorer-backup.timer",
    "deploy/systemd-user/vexplorer.service",
    "pyproject.toml",
    "requirements-demo.txt",
    "tools/__init__.py",
    "tools/backup.py",
    "tools/backup_rotate.py",
    "tools/manage_users.py",
)
_FRONTEND_TOP_LEVEL = (
    "frontend/app.js",
    "frontend/explorer.css",
    "frontend/explorer.html",
    "frontend/explorer.js",
    "frontend/index.html",
    "frontend/package-lock.json",
    "frontend/package.json",
    "frontend/reconstruction-state.js",
    "frontend/reconstruction.css",
    "frontend/reconstruction.html",
    "frontend/reconstruction.js",
    "frontend/styles.css",
)
_FRONTEND_DIRS = ("frontend/api", "frontend/assets", "frontend/components", "frontend/core", "frontend/vendor")
_BACKEND_SUFFIXES = frozenset({".py", ".json"})
_FRONTEND_SUFFIXES = frozenset({".css", ".html", ".js", ".json", ".png", ".svg", ".txt", ".webp", ".woff2"})


@dataclass(frozen=True)
class ReleaseResult:
    candidate_id: str
    git_head: str
    payload_tree_sha256: str
    archive: Path
    archive_sha256: str
    files: int


def _regular_files(root: Path) -> list[Path]:
    if root.is_symlink():
        raise ValueError(f"symlink_not_allowed:{root}")
    if not root.exists():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symlink_not_allowed:{path}")
        if path.is_file():
            files.append(path)
    return files


def collect_runtime_files(repository: Path) -> list[str]:
    """Return the sorted, explicit runtime allowlist relative to *repository*."""
    if repository.is_symlink():
        raise ValueError(f"symlink_not_allowed:{repository}")
    repository = repository.resolve()
    selected: set[str] = set()
    backend = repository / "backend" / "app"
    for path in _regular_files(backend):
        relative = path.relative_to(repository).as_posix()
        if "__pycache__" not in path.parts and path.suffix.lower() in _BACKEND_SUFFIXES:
            selected.add(relative)
    for relative in (*_ROOT_FILES, *_FRONTEND_TOP_LEVEL):
        path = repository / relative
        if path.is_symlink():
            raise ValueError(f"symlink_not_allowed:{path}")
        if path.is_file():
            selected.add(relative)
    for directory in _FRONTEND_DIRS:
        for path in _regular_files(repository / directory):
            relative = path.relative_to(repository).as_posix()
            if "/tests/" in f"/{relative}" or "/node_modules/" in f"/{relative}" or "/scripts/" in f"/{relative}":
                continue
            if path.suffix.lower() in _FRONTEND_SUFFIXES or path.name == "LICENSE":
                selected.add(relative)
    missing = [relative for relative in _REQUIRED if relative not in selected]
    if missing:
        raise ValueError(f"missing_required_runtime_files:{','.join(missing)}")
    return sorted(selected)


def _git_head(repository: Path) -> str:
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
    )
    head = process.stdout.strip().lower()
    if len(head) != 40 or any(character not in "0123456789abcdef" for character in head):
        raise ValueError("invalid_git_head")
    return head


def _digest_lines(entries: list[tuple[str, bytes]]) -> tuple[str, str]:
    lines = [f"{hashlib.sha256(content).hexdigest()}  {len(content)}  {name}" for name, content in entries]
    text = "\n".join(lines) + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), text


def _tar_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, content in sorted(entries):
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            info.mtime = 0
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(content))
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0, compresslevel=9) as stream:
        stream.write(raw.getvalue())
    return compressed.getvalue()


def build_release(repository: Path, output_directory: Path) -> ReleaseResult:
    repository = repository.resolve()
    output_directory = output_directory.resolve()
    paths = collect_runtime_files(repository)
    payload = [(relative, (repository / PurePosixPath(relative)).read_bytes()) for relative in paths]
    payload_digest, _ = _digest_lines(payload)
    head = _git_head(repository)
    candidate_id = f"{head[:12]}-tree{payload_digest[:16]}"
    metadata = {
        "candidate_id": candidate_id,
        "format": "vexplorer-runtime-release-v2",
        "git_head": head,
        "payload_tree_sha256": payload_digest,
        "working_tree": "includes_allowlisted_uncommitted_content",
    }
    release_json = (json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_entries = sorted(payload + [("RELEASE.json", release_json)])
    _, manifest_text = _digest_lines(manifest_entries)
    archive_entries = manifest_entries + [("MANIFEST.sha256", manifest_text.encode("utf-8"))]
    archive_bytes = _tar_bytes(archive_entries)
    output_directory.mkdir(parents=True, exist_ok=True)
    archive = output_directory / f"{candidate_id}.tar.gz"
    archive.write_bytes(archive_bytes)
    return ReleaseResult(
        candidate_id=candidate_id,
        git_head=head,
        payload_tree_sha256=payload_digest,
        archive=archive,
        archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        files=len(archive_entries),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path(".runtime/release-build"))
    args = parser.parse_args()
    result = build_release(args.repository, args.output)
    print(json.dumps(result.__dict__, default=str, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


