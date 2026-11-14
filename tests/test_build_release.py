from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

from tools.build_release import build_release, collect_runtime_files


def _write(root: Path, relative: str, content: bytes = b"source\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "release@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Release Test"], cwd=repo, check=True)
    for relative in (
        "backend/__init__.py",
        "backend/app/main.py",
        "backend/app/catalog.json",
        "backend/app/ingesta/README.md",
        "deploy/SYSTEMD_RELEASE.md",
        "deploy/requirements-runtime.txt",
        "deploy/systemd-production.env.example",
        "deploy/systemd-user/vexplorer.service",
        "deploy/systemd-user/vexplorer-backup.service",
        "deploy/systemd-user/vexplorer-backup.timer",
        "frontend/index.html",
        "frontend/app.js",
        "frontend/api/client.js",
        "frontend/styles.css",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/components/SceneViewer.js",
        "frontend/vendor/three/LICENSE",
        "frontend/vendor/three/three.core.js",
        "frontend/vendor/three/three.module.js",
        "frontend/vendor/three/addons/controls/OrbitControls.js",
        "pyproject.toml",
        "requirements-demo.txt",
        "tools/__init__.py",
        "tools/backup.py",
        "tools/backup_rotate.py",
        "tools/manage_users.py",
    ):
        _write(repo, relative)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    return repo


def test_allowlist_includes_local_runtime_additions_and_excludes_private_content(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    _write(repo, "backend/app/main.py", b"changed backend\n")
    _write(repo, "frontend/core/ui.js", b"export const ui = true;\n")
    _write(repo, "frontend/assets/fonts/geist.woff2", b"font")
    _write(repo, "frontend/assets/fonts/OFL.txt", b"license")
    _write(repo, "frontend/tests/private.test.js", b"oracle")
    _write(repo, "evaluation/reference/oracle.json", b"secret")
    _write(repo, "data/input.dxf", b"private")
    _write(repo, ".runtime/state.sqlite3", b"private")
    _write(repo, ".env", b"OPENAI_API_KEY=secret")

    paths = collect_runtime_files(repo)

    assert "backend/app/main.py" in paths
    assert "frontend/core/ui.js" in paths
    assert "frontend/api/client.js" in paths
    assert "frontend/assets/fonts/geist.woff2" in paths
    assert "frontend/assets/fonts/OFL.txt" in paths
    assert "tools/backup_rotate.py" in paths
    assert "backend/app/ingesta/README.md" in paths
    assert {
        "deploy/SYSTEMD_RELEASE.md",
        "deploy/systemd-production.env.example",
        "deploy/systemd-user/vexplorer.service",
        "deploy/systemd-user/vexplorer-backup.service",
        "deploy/systemd-user/vexplorer-backup.timer",
    } <= set(paths)
    assert not any(path.startswith(("data/", "evaluation/", ".runtime/")) for path in paths)
    assert ".env" not in paths
    assert not any("/tests/" in f"/{path}" for path in paths)


def test_missing_required_entry_rejects_partial_release(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    (repo / "frontend/app.js").unlink()

    try:
        collect_runtime_files(repo)
    except ValueError as error:
        assert str(error) == "missing_required_runtime_files:frontend/app.js"
    else:
        raise AssertionError("partial runtime was accepted")


def test_build_is_byte_reproducible_and_manifest_matches_payload(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    _write(repo, "backend/app/main.py", b"changed backend\n")
    _write(repo, "frontend/core/ui.js", b"export const ui = true;\n")
    _write(repo, "frontend/assets/fonts/geist.woff2", b"font")

    first = build_release(repo, tmp_path / "out-a")
    second = build_release(repo, tmp_path / "out-b")

    assert first.candidate_id == second.candidate_id
    assert first.archive_sha256 == second.archive_sha256
    assert first.archive.read_bytes() == second.archive.read_bytes()
    with tarfile.open(first.archive, "r:gz") as archive:
        names = archive.getnames()
        assert names == sorted(names)
        assert "backend/app/main.py" in names
        assert "pyproject.toml" in names
        assert "requirements-demo.txt" in names
        assert "deploy/requirements-runtime.txt" in names
        assert "frontend/package-lock.json" in names
        assert "frontend/core/ui.js" in names
        assert "frontend/assets/fonts/geist.woff2" in names
        release = json.load(archive.extractfile("RELEASE.json"))  # type: ignore[arg-type]
        manifest = archive.extractfile("MANIFEST.sha256").read().decode("utf-8")  # type: ignore[union-attr]
        for line in manifest.splitlines():
            digest, size, name = line.split("  ", 2)
            payload = archive.extractfile(name).read()  # type: ignore[union-attr]
            assert len(payload) == int(size)
            assert hashlib.sha256(payload).hexdigest() == digest
    assert release["candidate_id"] == first.candidate_id
    assert release["git_head"] == first.git_head
    assert release["working_tree"] == "includes_allowlisted_uncommitted_content"
    assert "created_at" not in release





