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


def _read(name: str):
    return ezdxf.readfile(PUBLIC_DIR / name)


def _model_texts(doc) -> set[str]:
    return {
        entity.dxf.text.strip()
        for entity in doc.modelspace().query("TEXT")
    }


@pytest.mark.parametrize(
    "filename",
    ["estanteria_montada.dxf", "estanteria_incompleta.dxf"],
)
def test_demo_dxf_declares_mm_and_only_public_layers(filename: str) -> None:
    doc = _read(filename)

    assert doc.header["$INSUNITS"] == 4
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


def test_fixture_generation_is_byte_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    command = [sys.executable, "-m", "tools.build_demo_fixture"]

    subprocess.run(command + ["--output-dir", str(first)], cwd=ROOT, check=True)
    subprocess.run(command + ["--output-dir", str(second)], cwd=ROOT, check=True)

    for filename in (
        "estanteria_montada.dxf",
        "estanteria_incompleta.dxf",
        "fixture_manifest.json",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()

