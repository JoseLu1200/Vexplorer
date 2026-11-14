"""Regresiones del contraste conservador con el catálogo del taller."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.contratos.modelos import (
    Bounds2D,
    DrawingContour,
    DrawingEntity,
    DrawingExtraction,
    DrawingObservation,
    DrawingView,
    Evidence,
    Point2D,
)
from backend.app.contratos import modelos
from backend.app.validador.plausibilidad import evaluate_plausibility


def _catalog(tmp_path: Path, *, confirmed: bool, setback_mm: float = 37.0) -> Path:
    path = tmp_path / "catalogo.json"
    path.write_text(
        json.dumps(
            {
                "source": "fixture de prueba",
                "confirmed_by_workshop": confirmed,
                "tolerance_mm": 0.1,
                "drilling_systems": [
                    {
                        "id": "system32",
                        "label": "Sistema 32 mm",
                        "pitch_mm": 32.0,
                        "hole_diameter_mm": 5.0,
                        "setback_mm": setback_mm,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _extraction(*, setback_mm: float = 37.0, include_contour: bool = True) -> DrawingExtraction:
    contour_points = (
        Point2D(x=0, y=0),
        Point2D(x=400, y=0),
        Point2D(x=400, y=700),
        Point2D(x=0, y=700),
        Point2D(x=0, y=0),
    )
    contour_entity = DrawingEntity(
        id="outline", kind="LWPOLYLINE", layer="0", source_points=contour_points, points_mm=contour_points
    )
    circles = []
    for index in range(4):
        center = Point2D(x=setback_mm, y=100 + 32 * index)
        entity_kwargs = {}
        if "circular" in DrawingEntity.model_fields:
            entity_kwargs["circular"] = modelos.CircularGeometry(
                kind="circle",
                center_source=center,
                center_mm=center,
                radius_source=2.5,
                radius_mm=2.5,
            )
        entity = DrawingEntity(
            id=f"circle-{index}",
            kind="CIRCLE",
            layer="HOLES",
            source_points=(Point2D(x=center.x + 2.5, y=center.y),),
            points_mm=(Point2D(x=center.x + 2.5, y=center.y),),
            **entity_kwargs,
        )
        # La rama base precede al contrato de B (f8c8fb4). Esto reproduce su
        # interfaz CircularGeometry sin sobrecargar points_mm.
        if "circular" not in DrawingEntity.model_fields:
            object.__setattr__(
                entity,
                "circular",
                SimpleNamespace(kind="circle", center_mm=center, radius_mm=2.5),
            )
        circles.append(entity)
    entity_ids = tuple(entity.id for entity in circles)
    view_ids = (("outline",) if include_contour else ()) + entity_ids
    view = DrawingView(
        id="view-front",
        label="FRONT",
        entity_ids=view_ids,
        bounds_source=Bounds2D(min_x=0, min_y=0, max_x=400, max_y=700),
        bounds_mm=Bounds2D(min_x=0, min_y=0, max_x=400, max_y=700),
    )
    contour = DrawingContour(
        id="contour-front",
        view_id=view.id,
        source_entity_ids=("outline",),
        points_source=contour_points,
        points_mm=contour_points,
        closed=True,
    )
    evidence = Evidence(
        id="evidence-holes-view-front-1",
        kind="geometry",
        source_entity_ids=entity_ids,
        description="texto humano deliberadamente irrelevante: paso 999 y retranqueo 999",
    )
    return DrawingExtraction(
        drawing_id="drawing-1",
        status="ready",
        source_unit="mm",
        unit_scale_to_mm=1.0,
        coordinate_unit="mm",
        entities=((contour_entity,) if include_contour else ()) + tuple(circles),
        views=(view,),
        contours=(contour,) if include_contour else (),
        dimensions=(),
        evidence=(evidence,),
        observations=(
            DrawingObservation(
                id="observation-front",
                view_id=view.id,
                contour_ids=(contour.id,) if include_contour else (),
                dimension_ids=(),
            ),
        ),
    )


def test_confirmed_catalog_passes_only_when_diameter_pitch_and_setback_match(tmp_path: Path) -> None:
    findings = evaluate_plausibility(_extraction(), _catalog(tmp_path, confirmed=True))

    assert len(findings) == 1
    assert findings[0]["status"] == "pass"
    assert findings[0]["system_id"] == "system32"
    assert findings[0]["observed"] == {"diameter_mm": 5.0, "pitch_mm": 32.0, "setback_mm": 37.0}
    assert findings[0]["evidence_ids"] == ["evidence-holes-view-front-1"]


def test_setback_100_against_system32_37_is_fail_not_pass(tmp_path: Path) -> None:
    findings = evaluate_plausibility(_extraction(setback_mm=100.0), _catalog(tmp_path, confirmed=True))

    assert [finding["status"] for finding in findings] == ["fail"]
    assert findings[0]["observed"]["setback_mm"] == 100.0


@pytest.mark.parametrize("setback_mm", [37.0, 100.0])
def test_unconfirmed_catalog_never_passes_or_fails(tmp_path: Path, setback_mm: float) -> None:
    findings = evaluate_plausibility(
        _extraction(setback_mm=setback_mm), _catalog(tmp_path, confirmed=False)
    )

    assert [finding["status"] for finding in findings] == ["unknown"]


def test_missing_geometry_is_unknown_and_does_not_invent_setback(tmp_path: Path) -> None:
    findings = evaluate_plausibility(
        _extraction(include_contour=False), _catalog(tmp_path, confirmed=True)
    )

    assert findings[0]["status"] == "unknown"
    assert findings[0]["observed"]["setback_mm"] is None


def test_default_catalog_is_packaged_unconfirmed_and_missing_override_is_explicit(tmp_path: Path) -> None:
    assert evaluate_plausibility(_extraction())[0]["status"] == "unknown"

    missing = tmp_path / "no-existe.json"
    with pytest.raises(FileNotFoundError, match="workshop_catalog_not_found"):
        evaluate_plausibility(_extraction(), missing)


def test_only_frozen_hole_row_evidence_shape_is_considered(tmp_path: Path) -> None:
    extraction = _extraction()
    unrelated = Evidence(
        id="evidence-other",
        kind="geometry",
        source_entity_ids=extraction.evidence[0].source_entity_ids,
        description="parece una fila, pero el extractor no la declaró como tal",
    )
    extraction = extraction.model_copy(update={"evidence": extraction.evidence + (unrelated,)})

    findings = evaluate_plausibility(extraction, _catalog(tmp_path, confirmed=True))

    assert len(findings) == 1
    assert findings[0]["id"] == "plausibility-evidence-holes-view-front-1"
