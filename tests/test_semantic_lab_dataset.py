from __future__ import annotations

import json
import math
from pathlib import Path

import ezdxf

from tools.semantic_lab.dataset import prepare_dataset
from tools.semantic_lab.features import UnsupportedGeometry, extract_dxf


def _write_shape(
    path: Path,
    *,
    dx: float = 0.0,
    dy: float = 0.0,
    z: float = 0.0,
    width: float = 80.0,
    include_text: bool = True,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    points = [(dx, dy, z), (dx + width, dy, z), (dx + width, dy + 40, z), (dx, dy + 40, z)]
    msp.add_lwpolyline(points, close=True)
    msp.add_line((dx + 10, dy + 10, z), (dx + 70, dy + 30, z))
    if include_text:
        msp.add_text("SOFAS secret title", dxfattribs={"insert": (dx, dy, z)})
    doc.saveas(path)


def test_extraction_is_invariant_to_filename_and_translation(tmp_path: Path) -> None:
    original = tmp_path / "sofas" / "category-and-title-must-not-leak.dxf"
    renamed = tmp_path / "beds" / "unrelated-name.dxf"
    _write_shape(original)
    _write_shape(renamed, dx=2500, dy=-730)

    first = extract_dxf(original, image_path=tmp_path / "first.png")
    second = extract_dxf(renamed, image_path=tmp_path / "second.png")

    assert first.features == second.features
    assert first.text == second.text
    assert first.geometry_signature == second.geometry_signature
    assert first.render_sha256 == second.render_sha256
    assert "sofa" not in first.text.lower()
    assert "secret" not in first.text.lower()
    assert (tmp_path / "first.png").read_bytes().startswith(b"\x89PNG")


def test_extraction_is_invariant_to_drawing_annotations(tmp_path: Path) -> None:
    annotated = tmp_path / "annotated.dxf"
    geometry_only = tmp_path / "geometry_only.dxf"
    _write_shape(annotated, include_text=True)
    _write_shape(geometry_only, include_text=False)

    first = extract_dxf(annotated)
    second = extract_dxf(geometry_only)

    assert first.features == second.features
    assert first.text == second.text
    assert first.geometry_signature == second.geometry_signature
    assert first.render_sha256 == second.render_sha256


def test_prepare_dataset_keeps_duplicate_groups_in_one_split(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write_shape(source / "dxf_metric" / "sofas" / "private_alpha_name.dxf")
    _write_shape(source / "dxf_metric" / "sofas" / "private_beta_name.dxf", dx=1000)
    _write_shape(source / "dxf_metric" / "beds" / "private_gamma_name.dxf")
    _write_shape(source / "dxf_metric" / "beds" / "private_delta_name.dxf", dx=-500)

    manifest = prepare_dataset(source, tmp_path / "out", categories=("sofas", "beds"))

    assert manifest["schema_version"] == 1
    assert len(manifest["samples"]) == 4
    by_group: dict[str, set[str]] = {}
    for sample in manifest["samples"]:
        by_group.setdefault(sample["group_id"], set()).add(sample["split"])
        assert sample["label_source"] == "cadblock_library_proxy"
        assert all(math.isfinite(value) for value in sample["features"].values())
        forbidden = (sample["label"], Path(sample["source_path"]).stem)
        assert all(token.lower() not in sample["text"].lower() for token in forbidden)
    assert all(len(splits) == 1 for splits in by_group.values())
    assert len(by_group) == 1
    frozen = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert frozen == manifest


def test_named_design_variants_are_metadata_grouped_before_split(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write_shape(
        source / "dxf_metric" / "sofas" / "two-seat-sofa-rolled-scroll-arms-plan-metric.dxf",
        width=80,
    )
    _write_shape(
        source / "dxf_metric" / "sofas" / "three-seat-sofa-rolled-scroll-arms-plan-metric.dxf",
        width=120,
    )

    manifest = prepare_dataset(source, tmp_path / "out", categories=("sofas",))

    assert len({sample["group_id"] for sample in manifest["samples"]}) == 1
    assert len({sample["split"] for sample in manifest["samples"]}) == 1
    assert manifest["metadata"]["variant_group_policy"].startswith("filename-derived metadata only")


def test_nonzero_z_geometry_is_excluded_with_reason(tmp_path: Path) -> None:
    source = tmp_path / "source"
    unsupported = source / "revisar_no_planos" / "dxf_metric" / "buffets" / "z.dxf"
    _write_shape(unsupported, z=3.0)

    manifest = prepare_dataset(source, tmp_path / "out", categories=("buffets",))

    assert manifest["samples"] == []
    assert manifest["metadata"]["candidate_count"] == 1
    assert "commercial serving counters" in manifest["metadata"]["category_definitions"]["buffets"]
    assert manifest["metadata"]["excluded"] == [
        {"source_path": str(unsupported.resolve()), "reason": "nonzero_z_geometry"}
    ]
    try:
        extract_dxf(unsupported)
    except UnsupportedGeometry as exc:
        assert exc.reason == "nonzero_z_geometry"
    else:
        raise AssertionError("nonzero Z geometry must be rejected")
