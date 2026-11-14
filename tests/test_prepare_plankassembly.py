import hashlib
import json
import zipfile
from pathlib import Path

import ezdxf
import pytest

from tools.prepare_plankassembly import prepare_plankassembly


def _write_fixture(root: Path) -> tuple[str, str]:
    model_dir = root / "extracted" / "data" / "model"
    split_dir = root / "extracted" / "data" / "splits"
    model_dir.mkdir(parents=True)
    split_dir.mkdir(parents=True)
    with_normal = "fixture_normal.json"
    without_normal = "fixture_missing_normal.json"
    common = {
        "planks": [
            [0, 0, 0, 1000, 500, 700],  # envelope: never a physical component
            [0, 0, 0, 20, 500, 700],
            [980, 0, 0, 1000, 500, 700],
            [20, 0, 680, 980, 500, 700],
        ],
        "attach": [
            [-1, -1, -1, -1, -1, -1],
            [0, 1, 2, -1, 4, 5],
            [-1, -1, 2, -1, 4, 5],
            [9, -1, -1, 12, 4, 5],
        ],
    }
    first = {"name": "revealing-source-name", "id": "source-a", **common,
             "normal": [[0, 0, 1], [-1, 0, 0], [-1, 0, 0], [0, 0, 1]]}
    second = {"name": "another-revealing-name", "id": "source-b", **common}
    (model_dir / with_normal).write_text(json.dumps(first), encoding="utf-8")
    (model_dir / without_normal).write_text(json.dumps(second), encoding="utf-8")
    (split_dir / "valid.txt").write_text(f"{with_normal}\n{without_normal}\n", encoding="utf-8")
    return with_normal, without_normal


def _tree_hash(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_prepares_assembled_views_and_private_reference_without_leaking_components(tmp_path: Path):
    source = tmp_path / "source"
    _write_fixture(source)
    public = tmp_path / "public"
    private = tmp_path / "private"

    manifest = prepare_plankassembly(source, public, private, split="valid", limit=2)

    assert manifest["case_count"] == 2
    assert manifest["source_split"] == "valid"
    public_cases = json.loads((public / "cases.json").read_text(encoding="utf-8"))
    assert [case["id"] for case in public_cases] == ["plank-001", "plank-002"]
    assert {case["split"] for case in public_cases} <= {"development", "holdout"}
    assert all(case["family_hash"] for case in public_cases)
    assert "revealing" not in json.dumps(public_cases).lower()

    for case in public_cases:
        dxf_path = public / case["file"]
        document = ezdxf.readfile(dxf_path)
        texts = [entity.dxf.text for entity in document.modelspace().query("TEXT")]
        assert texts == []
        assert all("part" not in layer.dxf.name.lower() for layer in document.layers)
        assert all("bom" not in layer.dxf.name.lower() for layer in document.layers)
        with zipfile.ZipFile(public / "agent_cases" / f"{case['id']}.zip") as archive:
            assert set(archive.namelist()) == {"input.dxf", "case.json"}
            assert archive.testzip() is None
            assert b"revealing-source-name" not in archive.read("input.dxf")

    references = json.loads((private / "references.json").read_text(encoding="utf-8"))
    assert references[0]["components"] == [
        {"source_index": 1, "bounds_mm": [0, 0, 0, 20, 500, 700], "normal": [-1, 0, 0]},
        {"source_index": 2, "bounds_mm": [980, 0, 0, 1000, 500, 700], "normal": [-1, 0, 0]},
        {"source_index": 3, "bounds_mm": [20, 0, 680, 980, 500, 700], "normal": [0, 0, 1]},
    ]
    assert references[0]["source_attach_indices"] == references[1]["source_attach_indices"]
    assert all(component["normal"] is None for component in references[1]["components"])
    assert not (public / "references.json").exists()


def test_output_is_reproducible_and_rejects_unsafe_scope(tmp_path: Path):
    source = tmp_path / "source"
    _write_fixture(source)
    first_public, first_private = tmp_path / "public-a", tmp_path / "private-a"
    second_public, second_private = tmp_path / "public-b", tmp_path / "private-b"

    prepare_plankassembly(source, first_public, first_private, split="valid", limit=2)
    prepare_plankassembly(source, second_public, second_private, split="valid", limit=2)

    assert _tree_hash(first_public) == _tree_hash(second_public)
    assert _tree_hash(first_private) == _tree_hash(second_private)
    with pytest.raises(ValueError, match="between 1 and 10"):
        prepare_plankassembly(source, tmp_path / "too-many", tmp_path / "private-many", split="valid", limit=11)
    with pytest.raises(ValueError, match="separate"):
        prepare_plankassembly(source, tmp_path / "same", tmp_path / "same", split="valid", limit=2)
