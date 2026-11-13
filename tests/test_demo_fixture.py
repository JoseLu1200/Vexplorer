from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import ezdxf
import pytest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "data" / "planos_demo"
REFERENCE_PATH = ROOT / "evaluation" / "reference" / "estanteria_reference.json"
LIBRARY_REFERENCE_PATH = ROOT / "evaluation" / "reference" / "library_reference.json"

PUBLIC_CASES = (
    "estanteria_montada.dxf",
    "estanteria_incompleta.dxf",
    "mueble_demo_002.dxf",
    "mueble_demo_003.dxf",
    "mueble_demo_004.dxf",
    "mueble_demo_unidades_desconocidas.dxf",
    "mueble_demo_trapecio.dxf",
)


def _read(name: str):
    return ezdxf.readfile(PUBLIC_DIR / name)


def _model_texts(doc) -> set[str]:
    return {
        entity.dxf.text.strip()
        for entity in doc.modelspace().query("TEXT")
    }


@pytest.mark.parametrize(
    "filename",
    PUBLIC_CASES,
)
def test_demo_dxf_declares_mm_and_only_public_layers(filename: str) -> None:
    doc = _read(filename)

    expected_unit = 0 if filename == "mueble_demo_unidades_desconocidas.dxf" else 4
    assert doc.header["$INSUNITS"] == expected_unit
    assert _model_texts(doc) >= {"FRONT", "TOP", "RIGHT", "FIXTURE SINTETICO"}

    allowed_layers = {"0", "Defpoints", "VIEW_GEOMETRY", "DIMENSIONS", "LABELS"}
    used_layers = {
        entity.dxf.layer
        for entity in doc.modelspace()
    }
    assert used_layers <= allowed_layers

    forbidden_tokens = {
        "bom",
        "bill of materials",
        "side panel",
        "shelf",
        "back panel",
        "lateral",
        "balda",
        "trasera",
    }
    public_text = " ".join(_model_texts(doc)).casefold()
    assert all(token not in public_text for token in forbidden_tokens)


def test_public_dimensions_are_few_overall_observations() -> None:
    doc = _read("estanteria_montada.dxf")
    dimensions = list(doc.modelspace().query("DIMENSION"))
    measurements = sorted(
        round(float(dimension.get_measurement()), 6) for dimension in dimensions
    )

    # Oráculo escrito a mano a partir de las cotas públicas del caso,
    # no calculado mediante el generador ni el extractor del producto.
    assert measurements == [18.0, 300.0, 900.0, 1200.0]
    assert {
        float(dimension.get_dim_style().dxf.dimlfac) for dimension in dimensions
    } == {1.0}


@pytest.mark.parametrize(
    ("filename", "expected_measurements", "expected_shelf_lines", "expected_width"),
    [
        ("estanteria_montada.dxf", [18.0, 300.0, 900.0, 1200.0], 2, 900.0),
        ("estanteria_incompleta.dxf", [300.0, 900.0, 1200.0], 2, 900.0),
        ("mueble_demo_002.dxf", [18.0, 320.0, 1000.0, 1300.0], 2, 1000.0),
        ("mueble_demo_003.dxf", [18.0, 280.0, 700.0, 800.0], 1, 700.0),
        ("mueble_demo_004.dxf", [18.0, 300.0, 900.0, 1200.0], 2, 900.0),
    ],
)
def test_parametric_library_has_independent_dimensions_and_structure(
    filename: str,
    expected_measurements: list[float],
    expected_shelf_lines: int,
    expected_width: float,
) -> None:
    doc = _read(filename)
    dimensions = sorted(
        round(float(dimension.get_measurement()), 6)
        for dimension in doc.modelspace().query("DIMENSION")
    )
    front_lines = [
        line
        for line in doc.modelspace().query("LINE[layer=='VIEW_GEOMETRY']")
        if abs(line.dxf.start.y - line.dxf.end.y) < 1e-9
        and abs(line.dxf.end.x - line.dxf.start.x) == expected_width
    ]

    assert dimensions == expected_measurements
    assert len(front_lines) == expected_shelf_lines


def test_three_views_are_not_physical_quantity() -> None:
    doc = _read("estanteria_montada.dxf")
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))

    view_count = len({text for text in _model_texts(doc) if text in {"FRONT", "TOP", "RIGHT"}})
    physical_occurrences = sum(
        piece["quantity"] for piece in reference["reviewed_reference"]["pieces"]
    )

    assert view_count == 3
    assert physical_occurrences == 7
    assert physical_occurrences != view_count


def test_incomplete_variant_contains_no_thickness_evidence() -> None:
    doc = _read("estanteria_incompleta.dxf")
    measurements = {
        round(float(dimension.get_measurement()), 6)
        for dimension in doc.modelspace().query("DIMENSION")
    }

    assert measurements == {300.0, 900.0, 1200.0}
    manifest = json.loads(
        (PUBLIC_DIR / "fixture_manifest.json").read_text(encoding="utf-8")
    )
    incomplete = manifest["cases"]["estanteria_incompleta.dxf"]
    assert incomplete["expected_unknown_fields"] == ["thickness"]
    assert "expected_value" not in incomplete


def test_reference_records_real_ambiguity_and_is_not_unique_gold() -> None:
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))

    assert reference["evaluation_policy"]["requires_human_mounting_confirmation"] is True
    assert reference["evaluation_policy"]["unique_solution_claimed"] is False
    assert len(reference["acceptable_alternative_scenarios"]) >= 2


def test_private_library_groups_dimensions_separately_from_structure() -> None:
    reference = json.loads(LIBRARY_REFERENCE_PATH.read_text(encoding="utf-8"))

    assert reference["reference_version"] == "1.0.0"
    assert reference["expected_groups"]["same_structure"] == [
        "estanteria_montada.dxf",
        "mueble_demo_002.dxf",
        "mueble_demo_004.dxf",
    ]
    assert reference["expected_groups"]["different_structure"] == [
        "mueble_demo_003.dxf"
    ]
    assert reference["evaluation_policy"]["runtime_must_not_read_this_file"] is True


def test_translated_duplicate_changes_coordinates_not_public_dimensions() -> None:
    doc = _read("mueble_demo_004.dxf")
    front = next(
        entity
        for entity in doc.modelspace().query("LWPOLYLINE[layer=='VIEW_GEOMETRY']")
    )
    points = [(point[0], point[1]) for point in front.get_points("xy")]

    assert min(x for x, _ in points) == 5000.0
    assert min(y for _, y in points) == 2500.0
    assert max(x for x, _ in points) - min(x for x, _ in points) == 900.0
    assert max(y for _, y in points) - min(y for _, y in points) == 1200.0


def test_negative_preview_fixtures_do_not_encode_a_bom() -> None:
    unknown_units = _read("mueble_demo_unidades_desconocidas.dxf")
    trapezoid = _read("mueble_demo_trapecio.dxf")

    assert unknown_units.header["$INSUNITS"] == 0
    front = next(
        entity
        for entity in trapezoid.modelspace().query("LWPOLYLINE[layer=='VIEW_GEOMETRY']")
    )
    points = [(round(point[0], 6), round(point[1], 6)) for point in front.get_points("xy")]
    assert points == [(0.0, 0.0), (900.0, 0.0), (820.0, 1200.0), (80.0, 1200.0)]
    assert all(
        token not in " ".join(_model_texts(doc)).casefold()
        for doc in (unknown_units, trapezoid)
        for token in ("bom", "balda", "lateral", "shelf", "side panel")
    )


def test_fixture_generation_is_byte_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    command = [sys.executable, "-m", "tools.build_demo_fixture"]

    subprocess.run(command + ["--output-dir", str(first)], cwd=ROOT, check=True)
    subprocess.run(command + ["--output-dir", str(second)], cwd=ROOT, check=True)

    for filename in (*PUBLIC_CASES, "fixture_manifest.json"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()

