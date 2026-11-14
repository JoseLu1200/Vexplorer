from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import zipfile

from backend.app.ingesta.dxf_reader import parse_dxf
from tools.prepare_cad_completion_controls import build_controls
from tools.run_general_benchmark import _read_valid_bundle


def test_f01_public_bundle_is_sparse_assembled_cad_without_answer_leakage(
    tmp_path: Path,
) -> None:
    public_dir = tmp_path / "public"
    private_dir = tmp_path / "private"

    result = build_controls(public_dir, private_dir, case_ids=("F01",))

    bundle = public_dir / "F01.zip"
    assert result["F01"]["public_bundle_sha256"] == sha256(bundle.read_bytes()).hexdigest()
    with zipfile.ZipFile(bundle) as archive:
        assert set(archive.namelist()) == {"input.dxf", "case.json"}
        metadata = json.loads(archive.read("case.json"))
        raw_dxf = archive.read("input.dxf")

    assert (public_dir / "F01.dxf").read_bytes() == raw_dxf
    assert _read_valid_bundle(bundle) == ("F01", raw_dxf)

    assert metadata == {
        "id": "F01",
        "file": "input.dxf",
        "format": "dxf",
        "unit": "mm",
        "view_kind": "assembled_orthographic",
        "instruction": (
            "Interpret the assembled furniture views, deduce or estimate missing dimensions "
            "and construction details, and propose necessary parts with dimensioned piece "
            "drawings. Keep observations distinct from explicit estimates and explain "
            "important decisions."
        ),
        "sha256": sha256(raw_dxf).hexdigest(),
    }
    dxf_path = tmp_path / "F01.dxf"
    dxf_path.write_bytes(raw_dxf)
    parsed = parse_dxf(dxf_path)
    public_text = " ".join(
        entity.text or "" for entity in parsed.entities if entity.kind in {"TEXT", "MTEXT"}
    ).lower()
    for token in ("table", "mesa", "top", "leg", "apron", "faldon", "bom", "quantity"):
        assert token not in public_text
    assert parsed.source_unit == "mm"
    assert sorted(
        entity.measurement
        for entity in parsed.entities
        if entity.kind == "DIMENSION"
    ) == [30.0, 600.0, 750.0, 1200.0]
    assert not parsed.warnings


def test_f01_private_reference_encodes_utility_not_a_single_hidden_triplet(
    tmp_path: Path,
) -> None:
    public_dir = tmp_path / "public"
    private_dir = tmp_path / "private"
    build_controls(public_dir, private_dir, case_ids=("F01",))

    reference = json.loads((private_dir / "F01.reference.json").read_text("utf-8"))

    assert reference["case_id"] == "F01"
    assert reference["reference_kind"] == "developer_functional_control"
    assert reference["public_input_sha256"] == json.loads(
        zipfile.ZipFile(public_dir / "F01.zip").read("case.json")
    )["sha256"]
    scenario = reference["acceptable_scenarios"][0]
    by_role = {item["role"]: item for item in scenario["necessary_piece_types"]}
    assert {role: item["quantity"] for role, item in by_role.items()} == {
        "work_surface": 1,
        "vertical_support": 4,
        "longitudinal_apron": 2,
        "transverse_apron": 2,
    }
    assert by_role["vertical_support"]["dimensions_mm"]["length"] == {
        "kind": "deduced",
        "exact": 720.0,
        "relation": "overall_height - surface_thickness",
    }
    assert by_role["longitudinal_apron"]["dimensions_mm"]["thickness"] == {
        "kind": "estimated",
        "minimum": 18.0,
        "maximum": 25.0,
        "premise": "panel apron thickness is not visible in the source views",
    }
    assert "closure_constraints" in scenario
    assert reference["utility_checks"]["piece_drawings"] == {
        "required_formats": ["svg", "dxf"],
        "per_piece_type": True,
        "numeric_dimensions_required": True,
    }
    assert reference["epistemic_rules"]["scenario_occurrences"] == "hypothesis"


def test_control_generation_is_byte_deterministic(tmp_path: Path) -> None:
    build_controls(tmp_path / "public-a", tmp_path / "private-a")
    build_controls(tmp_path / "public-b", tmp_path / "private-b")

    for case_id in ("F01", "F02", "F03"):
        for relative in (f"{case_id}.dxf", f"{case_id}.zip"):
            assert (tmp_path / "public-a" / relative).read_bytes() == (
                tmp_path / "public-b" / relative
            ).read_bytes()
        assert (tmp_path / "private-a" / f"{case_id}.reference.json").read_bytes() == (
            tmp_path / "private-b" / f"{case_id}.reference.json"
        ).read_bytes()


def test_f02_and_f03_are_sparse_and_references_allow_coherent_alternatives(
    tmp_path: Path,
) -> None:
    public_dir = tmp_path / "public"
    private_dir = tmp_path / "private"
    build_controls(public_dir, private_dir, case_ids=("F02", "F03"))

    expected_dimensions = {
        "F02": [18.0, 450.0, 800.0, 900.0],
        "F03": [18.0, 300.0, 800.0, 1800.0],
    }
    for case_id, dimensions in expected_dimensions.items():
        with zipfile.ZipFile(public_dir / f"{case_id}.zip") as archive:
            raw = archive.read("input.dxf")
        source = tmp_path / f"{case_id}.dxf"
        source.write_bytes(raw)
        parsed = parse_dxf(source)
        assert sorted(
            entity.measurement
            for entity in parsed.entities
            if entity.kind == "DIMENSION"
        ) == dimensions
        public_text = " ".join(entity.text or "" for entity in parsed.entities).lower()
        for token in (
            "cabinet",
            "drawer",
            "cajon",
            "shelf",
            "estanter",
            "back panel",
            "bom",
        ):
            assert token not in public_text
        assert _read_valid_bundle(public_dir / f"{case_id}.zip")[0] == case_id

    f02 = json.loads((private_dir / "F02.reference.json").read_text("utf-8"))
    assert {item["key"] for item in f02["acceptable_scenarios"]} == {
        "horizontal_panels_between_sides",
        "horizontal_panels_cap_sides",
    }
    for scenario in f02["acceptable_scenarios"]:
        quantities = {
            item["role"]: item["quantity"]
            for item in scenario["necessary_piece_types"]
        }
        assert quantities["drawer_front"] == 3
        assert quantities["drawer_box_side"] == 6
        assert quantities["drawer_box_front_back"] == 6
        assert quantities["drawer_bottom"] == 3

    f03 = json.loads((private_dir / "F03.reference.json").read_text("utf-8"))
    assert {item["key"] for item in f03["acceptable_scenarios"]} == {
        "open_back_with_anchoring",
        "thin_structural_back",
    }
    open_back, backed = f03["acceptable_scenarios"]
    assert "anchoring" in " ".join(open_back["closure_constraints"]).lower()
    back = next(
        item for item in backed["necessary_piece_types"] if item["role"] == "back_panel"
    )
    assert back["dimensions_mm"]["thickness"]["kind"] == "estimated"
    assert back["dimensions_mm"]["thickness"]["minimum"] == 3.0
    assert back["dimensions_mm"]["thickness"]["maximum"] == 6.0

