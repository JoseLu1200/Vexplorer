"""Pruebas deterministas de la regla de pandeo en el validador de plausibilidad."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.contratos.modelos import (
    Bounds2D,
    ComponentProposal,
    DrawingEntity,
    DrawingExtraction,
    DrawingView,
    Point2D,
)
from backend.app.validador.plausibilidad import (
    PANDEO_WARNING_CODE,
    evaluate_deflection_plausibility,
    evaluate_plausibility,
)


def _minimal_extraction() -> DrawingExtraction:
    points = (Point2D(x=0, y=0), Point2D(x=100, y=0))
    entity = DrawingEntity(
        id="ent-1",
        kind="LINE",
        layer="0",
        source_points=points,
        points_mm=points,
    )
    view = DrawingView(
        id="view-1",
        label="FRONT",
        entity_ids=("ent-1",),
        bounds_source=Bounds2D(min_x=0, min_y=0, max_x=100, max_y=10),
        bounds_mm=Bounds2D(min_x=0, min_y=0, max_x=100, max_y=10),
    )
    return DrawingExtraction(
        drawing_id="drawing-pandeo-test",
        status="ready",
        source_unit="mm",
        unit_scale_to_mm=1.0,
        coordinate_unit="mm",
        entities=(entity,),
        views=(view,),
        contours=(),
        dimensions=(),
        evidence=(),
        observations=(),
    )


def test_shelf_within_safe_span_has_no_pandeo_warning() -> None:
    shelf = ComponentProposal(
        id="comp-shelf-ok",
        label="Balda 700",
        role="shelf",
        quantity=2,
        length_mm=700.0,
        width_mm=300.0,
        thickness_mm=16.0,
        source_observation_ids=("obs-1",),
        evidence_ids=("ev-1",),
        assumptions=("medida observada",),
    )

    findings = evaluate_deflection_plausibility([shelf])

    assert len(findings) == 1
    finding = findings[0]
    assert finding["check"] == "structural_deflection"
    assert finding["status"] == "unknown"
    assert finding["code"] is None
    assert finding["observed"]["max_span_mm"] == 750.0


@pytest.mark.parametrize(
    ("thickness_mm", "span_mm", "expected_max"),
    [
        (16.0, 900.0, 750.0),
        (18.0, 1050.0, 900.0),
    ],
)
def test_shelf_exceeding_max_span_emits_pandeo_warning(
    thickness_mm: float, span_mm: float, expected_max: float
) -> None:
    shelf = {
        "id": "balda-larga",
        "label": "Balda superior",
        "role": "shelf",
        "length_mm": span_mm,
        "thickness_mm": thickness_mm,
        "evidence_ids": ["ev-span"],
    }

    findings = evaluate_deflection_plausibility([shelf])

    assert len(findings) == 1
    finding = findings[0]
    assert finding["check"] == "structural_deflection"
    assert finding["status"] == "warning"
    assert finding["severity"] == "warning"
    assert finding["code"] == PANDEO_WARNING_CODE
    assert "balda-larga" in finding["message"]
    assert f"{span_mm:.0f}" in finding["message"]
    assert f"{thickness_mm:g}" in finding["message"]
    assert f"{expected_max:.0f}" in finding["message"]
    assert finding["observed"]["length_mm"] == span_mm
    assert finding["observed"]["thickness_mm"] == thickness_mm
    assert finding["observed"]["max_span_mm"] == expected_max


def test_unknown_thickness_or_length_abstains_without_false_positive() -> None:
    no_thickness = ComponentProposal(
        id="comp-no-thick",
        label="Balda sin espesor",
        role="shelf",
        length_mm=1500.0,
        thickness_mm=None,
        source_observation_ids=("obs-1",),
        evidence_ids=("ev-1",),
        assumptions=("espesor desconocido",),
    )
    no_length = ComponentProposal(
        id="comp-no-len",
        label="Tapa sin luz",
        role="top_panel",
        length_mm=None,
        thickness_mm=16.0,
        source_observation_ids=("obs-1",),
        evidence_ids=("ev-1",),
        assumptions=("longitud desconocida",),
    )
    marked_unknown = {
        "id": "comp-state-unknown",
        "label": "Encimera marcada unknown",
        "role": "tabletop",
        "length_mm": 1600.0,
        "thickness_mm": 16.0,
        "field_states": {"thickness_mm": "unknown", "length_mm": "observed"},
    }

    findings = evaluate_deflection_plausibility([no_thickness, no_length, marked_unknown])

    assert findings == ()


def test_thicker_board_passes_span_that_fails_on_16mm() -> None:
    span_mm = 1100.0
    thin_shelf = {
        "id": "shelf-16",
        "label": "Balda 16mm",
        "role": "balda",
        "length_mm": span_mm,
        "thickness_mm": 16.0,
    }
    thick_shelf_25 = {
        "id": "shelf-25",
        "label": "Balda 25mm",
        "role": "balda",
        "length_mm": span_mm,
        "thickness_mm": 25.0,
    }
    thick_shelf_36 = {
        "id": "shelf-36",
        "label": "Tapa 36mm",
        "role": "tapa",
        "length_mm": span_mm,
        "thickness_mm": 36.0,
    }

    findings = evaluate_deflection_plausibility([thin_shelf, thick_shelf_25, thick_shelf_36])
    by_id = {item["observed"]["piece_id"]: item for item in findings}

    assert by_id["shelf-16"]["status"] == "warning"
    assert by_id["shelf-16"]["code"] == PANDEO_WARNING_CODE
    assert by_id["shelf-25"]["status"] == "unknown"
    assert by_id["shelf-25"]["code"] is None
    assert by_id["shelf-36"]["status"] == "unknown"
    assert by_id["shelf-36"]["code"] is None


def test_explicit_intermediate_vertical_support_reduces_effective_span() -> None:
    shelf = {
        "id": "shelf-1200",
        "label": "Balda con montante",
        "role": "shelf",
        "length_mm": 1200.0,
        "thickness_mm": 16.0,
        "intermediate_supports": 1,
    }
    divider = {
        "id": "divider-1",
        "label": "Montante central",
        "role": "divider",
        "quantity": 1,
        "length_mm": 700.0,
        "thickness_mm": 16.0,
    }

    findings = evaluate_deflection_plausibility([shelf, divider])

    assert len(findings) == 1
    assert findings[0]["status"] == "unknown"
    assert findings[0]["code"] is None
    assert findings[0]["observed"]["intermediate_supports"] == 1
    assert findings[0]["observed"]["effective_span_mm"] == 600.0


def test_unassociated_vertical_piece_does_not_shorten_shelf_span() -> None:
    shelf = {"id": "shelf-1200", "role": "shelf", "length_mm": 1200.0, "thickness_mm": 16.0}
    unrelated_divider = {"id": "divider-other-module", "role": "divider", "quantity": 1, "length_mm": 300.0, "thickness_mm": 16.0}
    finding = evaluate_deflection_plausibility([shelf, unrelated_divider])[0]
    assert finding["code"] == PANDEO_WARNING_CODE
    assert finding["observed"]["intermediate_supports"] == 0
    assert finding["observed"]["effective_span_mm"] == 1200.0


def test_unconfirmed_catalog_never_emits_structural_pass() -> None:
    shelf = {"id": "shelf-700", "role": "shelf", "length_mm": 700.0, "thickness_mm": 16.0}
    finding = evaluate_deflection_plausibility([shelf])[0]
    assert finding["status"] == "unknown"
    assert finding["severity"] == "info"
    assert finding["catalog"]["confirmed_by_workshop"] is False
    assert "pendientes de confirmación" in finding["catalog"]["source"]


def test_material_override_applies_stricter_mdf_limit() -> None:
    mdf_shelf = {
        "id": "shelf-mdf",
        "label": "Balda MDF",
        "role": "shelf",
        "length_mm": 700.0,
        "thickness_mm": 16.0,
        "material": "MDF crudo",
    }
    plywood_shelf = {
        "id": "shelf-plywood",
        "label": "Balda contrachapado",
        "role": "shelf",
        "length_mm": 700.0,
        "thickness_mm": 16.0,
        "material": "Contrachapado abedul",
    }

    findings = evaluate_deflection_plausibility([mdf_shelf, plywood_shelf])
    by_id = {item["observed"]["piece_id"]: item for item in findings}

    assert by_id["shelf-mdf"]["code"] == PANDEO_WARNING_CODE
    assert by_id["shelf-mdf"]["observed"]["max_span_mm"] == 650.0
    assert by_id["shelf-plywood"]["status"] == "unknown"
    assert by_id["shelf-plywood"]["observed"]["max_span_mm"] == 850.0


def test_evaluate_plausibility_integrates_pieces_and_ignores_vertical_panels(
    tmp_path: Path,
) -> None:
    legacy_catalog = tmp_path / "legacy_catalog.json"
    legacy_catalog.write_text(
        json.dumps(
            {
                "source": "legacy sin deflection_limits",
                "confirmed_by_workshop": False,
                "tolerance_mm": 0.1,
                "drilling_systems": [],
            }
        ),
        encoding="utf-8",
    )
    pieces = [
        {"id": "side-1", "label": "Costado", "role": "side_panel", "length_mm": 2000.0, "thickness_mm": 16.0},
        {"id": "top-1", "label": "Tapa", "role": "top_panel", "length_mm": 1100.0, "thickness_mm": 18.0},
    ]

    findings = evaluate_plausibility(_minimal_extraction(), legacy_catalog, pieces=pieces)
    pandeo_findings = [item for item in findings if item["check"] == "structural_deflection"]

    assert len(pandeo_findings) == 1
    assert pandeo_findings[0]["observed"]["piece_id"] == "top-1"
    assert pandeo_findings[0]["code"] == PANDEO_WARNING_CODE
