import hashlib
import json
import zipfile
from pathlib import Path

import fitz
import pytest

from tools.prepare_evaluation import archive_case, audit_dataset, prepare_dataset, render_crops


def fixture_dataset(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    (root / "drawing.dxf").write_bytes(b"controlled CAD fixture")
    (root / "index.json").write_text(json.dumps([{"id": "one", "track": "single_part_cad_dimension_extraction", "dxf": "drawing.dxf"}]))
    manifest = []
    for name in ["drawing.dxf", "index.json"]:
        digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
        manifest.append(f"{digest}  {name}")
    (root / "SHA256SUMS").write_text("\n".join(manifest))
    return root


def test_audit_counts_verified_files_and_cases(tmp_path):
    audit = audit_dataset(fixture_dataset(tmp_path))
    assert audit.verified_files == 2
    assert audit.indexed_cases == 1
    assert audit.indexed_paths == 1


@pytest.mark.parametrize("damage", ["corrupt", "missing"])
def test_rejects_corrupt_or_missing_source(tmp_path, damage):
    root = fixture_dataset(tmp_path)
    if damage == "missing":
        (root / "drawing.dxf").unlink()
    else:
        (root / "drawing.dxf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="missing|hash"):
        audit_dataset(root)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "C:/absolute", "..\\outside"])
def test_rejects_unsafe_manifest_paths(tmp_path, name):
    root = fixture_dataset(tmp_path)
    (root / "SHA256SUMS").write_text("0" * 64 + "  " + name)
    with pytest.raises(ValueError, match="path"):
        audit_dataset(root)


def test_rejects_index_path_not_in_manifest(tmp_path):
    root = fixture_dataset(tmp_path)
    (root / "extra.dxf").write_bytes(b"unverified")
    (root / "index.json").write_text(json.dumps([{"id": "one", "track": "single_part_cad_dimension_extraction", "dxf": "extra.dxf"}]))
    digest = hashlib.sha256((root / "index.json").read_bytes()).hexdigest()
    lines = (root / "SHA256SUMS").read_text().splitlines()
    lines[-1] = digest + "  index.json"
    (root / "SHA256SUMS").write_text("\n".join(lines))
    with pytest.raises(ValueError, match="manifest"):
        audit_dataset(root)


def test_refuses_existing_output_without_changing_it(tmp_path):
    root = fixture_dataset(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="exists"):
        prepare_dataset(root, output)
    assert (output / "keep.txt").read_text() == "keep"


def test_refuses_output_inside_source(tmp_path):
    root = fixture_dataset(tmp_path)
    with pytest.raises(ValueError, match="overlap"):
        prepare_dataset(root, root / "output")
    assert not (root / "output").exists()


def test_crop_contains_only_visible_region_no_hidden_source(tmp_path):
    source = tmp_path / "original.pdf"
    with fitz.open() as d:
        p = d.new_page(width=400, height=200)
        p.insert_text((25, 40), "VISIBLE")
        p.insert_text((230, 40), "SECRET ANSWER")
        d.set_metadata({"title": "SECRET ANSWER"})
        d.embfile_add("answer.txt", b"SECRET ANSWER")
        d.save(source)
    destination = tmp_path / "input.pdf"
    render_crops(source, destination, ((10, 10, 190, 100),))
    with fitz.open(source) as original, fitz.open(destination) as output:
        assert len(output) == 1
        assert output.embfile_count() == 0
        assert output[0].get_text() == ""
        assert not output.metadata.get("title")
        assert len(output[0].get_images()) == 1
        pix = original[0].get_pixmap(matrix=fitz.Matrix(2, 2), clip=fitz.Rect(10, 10, 190, 100), alpha=False)
        embedded = fitz.Pixmap(output, output[0].get_images()[0][0])
        assert embedded.samples == pix.samples
    assert b"SECRET ANSWER" not in destination.read_bytes()


def test_single_case_archive_cannot_include_sibling_answer(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "poor.pdf").write_bytes(b"poor input")
    (inputs / "complete.pdf").write_bytes(b"reveals thickness")
    case = {"id": "one", "file": "poor.pdf", "sha256": hashlib.sha256(b"poor input").hexdigest()}
    archive = tmp_path / "one.zip"
    archive_case(inputs, case, archive)
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == {"input.pdf", "case.json"}
        assert z.read("input.pdf") == b"poor input"
        assert json.loads(z.read("case.json"))["file"] == "input.pdf"
        assert all(b"reveals thickness" not in z.read(n) for n in z.namelist())


def test_single_case_archive_rejects_altered_input(tmp_path):
    (tmp_path / "poor.pdf").write_bytes(b"modified")
    with pytest.raises(ValueError, match="hash"):
        archive_case(tmp_path, {"file": "poor.pdf", "sha256": "0" * 64}, tmp_path / "one.zip")
    assert not (tmp_path / "one.zip").exists()
