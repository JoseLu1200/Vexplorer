import json
import struct

import pytest
from pydantic import ValidationError

from backend.app.reconstruction3d.models import AssemblyProposal, Component
from backend.app.reconstruction3d.geometry import inspect_assembly
from backend.app.reconstruction3d.artifacts import export_package, render_assembly


def part(id, size, origin):
    return Component(
        id=id,
        label=id,
        size_mm=size,
        origin_mm=origin,
        source_refs=["input"],
        assumptions=["proposed construction"],
    )


def desk():
    return AssemblyProposal(
        status="proposed",
        intended_use="desk",
        unit="mm",
        components=[
            part("top", [900, 500, 20], [0, 0, 700]),
            part("left", [20, 500, 700], [0, 0, 0]),
            part("right", [20, 500, 700], [880, 0, 0]),
        ],
        assumptions=["panel joints unspecified"],
        missing_information=["material"],
        functional_notes=["provisional, no load certification"],
    )


def test_rejects_invalid_geometry_and_duplicate_ids():
    with pytest.raises(ValidationError):
        part("a", [-1, 2, 3], [0, 0, 0])
    with pytest.raises(ValidationError):
        part("a", [1, 2, 3], [float("nan"), 0, 0])
    with pytest.raises(ValidationError):
        desk().model_copy(update={}).__class__.model_validate(
            {
                **desk().model_dump(),
                "components": [part("a", [1, 2, 3], [0, 0, 0]).model_dump()] * 2,
            }
        )


def test_abstention_requires_reason_and_no_manufactured_parts():
    with pytest.raises(ValidationError):
        AssemblyProposal(
            status="insufficient_evidence", intended_use="unknown", unit="relative"
        )
    p = AssemblyProposal(
        status="insufficient_evidence",
        intended_use="unknown",
        unit="relative",
        missing_information=["need side view"],
    )
    assert not p.components


def test_geometry_checks_contact_floating_and_overlap_independently():
    assert inspect_assembly(desk())["floating_ids"] == []
    d = desk().model_dump()
    d["components"][0]["origin_mm"][2] = 710
    assert inspect_assembly(AssemblyProposal.model_validate(d))["floating_ids"] == [
        "top"
    ]
    d = desk().model_dump()
    d["components"][0]["origin_mm"][2] = 690
    assert len(inspect_assembly(AssemblyProposal.model_validate(d))["overlaps"]) == 2


def test_export_and_render_share_exact_component_count_and_units(tmp_path):
    p = desk()
    result = export_package(p, tmp_path)
    assert result["component_count"] == 3
    b = (tmp_path / "assembly.glb").read_bytes()
    magic, version, length = struct.unpack("<4sII", b[:12])
    assert (magic, version, length) == (b"glTF", 2, len(b))
    size = struct.unpack("<I", b[12:16])[0]
    g = json.loads(b[20 : 20 + size])
    assert len(g["nodes"]) == len(g["meshes"]) == 3
    assert g["asset"]["extras"]["provisional"] is True
    assert len((tmp_path / "bom.csv").read_text().splitlines()) == 4
    assert len(list((tmp_path / "parts").glob("*.svg"))) == 3
    image, mask = render_assembly(p, resolution=128)
    assert image.size == (128, 128) and mask.sum() > 300


def test_unscaled_assembly_exports_no_metric_glb_or_mm_bom(tmp_path):
    d = desk().model_dump()
    d["unit"] = "relative"
    p = AssemblyProposal.model_validate(d)
    result = export_package(p, tmp_path)
    assert not (tmp_path / "assembly.glb").exists()
    assert result["metric_export_available"] is False
    assert "relative" in (tmp_path / "bom.csv").read_text()
