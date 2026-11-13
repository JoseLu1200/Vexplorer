from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = ROOT / "evaluation" / "reference"
PUBLIC_DIR = ROOT / "data" / "planos_demo"


def _iter_runtime_files() -> list[Path]:
    roots = [ROOT / "backend", ROOT / "frontend", ROOT / "tools", PUBLIC_DIR]
    suffixes = {".py", ".js", ".html", ".css", ".json", ".dxf"}
    return [
        path
        for root in roots
        if root.exists()
        for path in root.rglob("*")
        if path.is_file() and path.suffix.casefold() in suffixes
    ]


def test_private_reference_bytes_and_path_never_enter_runtime_surfaces() -> None:
    reference_files = [path for path in REFERENCE_DIR.rglob("*") if path.is_file()]
    assert reference_files

    private_hashes = {
        hashlib.sha256(path.read_bytes()).hexdigest() for path in reference_files
    }
    runtime_files = _iter_runtime_files()
    assert runtime_files

    for path in runtime_files:
        raw = path.read_bytes()
        folded = raw.decode("utf-8", errors="ignore").casefold()
        assert "evaluation/reference" not in folded.replace("\\", "/"), path
        assert hashlib.sha256(raw).hexdigest() not in private_hashes, path


def test_public_manifest_contains_no_bom_or_private_measurements() -> None:
    manifest = json.loads(
        (PUBLIC_DIR / "fixture_manifest.json").read_text(encoding="utf-8")
    )
    serialized = json.dumps(manifest, ensure_ascii=False).casefold()

    assert "pieces" not in serialized
    assert "quantity" not in serialized
    assert "reviewed_reference" not in serialized
    assert "evaluation/reference" not in serialized

