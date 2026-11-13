from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.contratos.modelos import Bounds3D, DimensionGraphic, DrawingExtraction, DrawingText, Point2D, Point3D, ReconstructionScene, SceneObject, Size3D
from backend.tests.test_backend_contract import _unknown_extraction


def test_old_extraction_payload_gets_empty_additive_viewer_fields() -> None:
    payload = _unknown_extraction().model_dump(mode="json")
    payload.pop("texts", None)
    payload.pop("dimension_graphics", None)
    restored = DrawingExtraction.model_validate(payload)
    assert restored.texts == ()
    assert restored.dimension_graphics == ()


def test_unknown_units_reject_metric_text_points() -> None:
    payload = _unknown_extraction().model_dump(mode="json")
    payload["texts"] = [{"id": "text-1", "source_entity_id": "entity-1", "view_id": "view-1", "layer": "LABELS", "text": "FRONT", "position_source": {"x": 1, "y": 2}, "position_mm": {"x": 1, "y": 2}}]
    with pytest.raises(ValidationError, match="unknown unit"):
        DrawingExtraction.model_validate(payload)


def test_viewer_ledger_validates_text_and_dimension_graphic_references() -> None:
    payload = _unknown_extraction().model_dump(mode="json")
    payload["texts"] = [DrawingText(id="text-1", source_entity_id="missing", view_id="view-1", layer="LABELS", text="FRONT", position_source=Point2D(x=0, y=0), position_mm=None).model_dump(mode="json")]
    with pytest.raises(ValidationError, match="text has an unknown reference"):
        DrawingExtraction.model_validate(payload)

    payload = _unknown_extraction().model_dump(mode="json")
    graphic = DimensionGraphic(id="graphic-1", dimension_id="dimension-1", source_entity_id="entity-1", view_id="view-1", layer="DIMENSIONS", display_text="100", raw_text="<>", extension_start_a_source=Point2D(x=0, y=0), extension_start_a_mm=None, extension_start_b_source=Point2D(x=100, y=0), extension_start_b_mm=None, dimension_start_source=Point2D(x=0, y=10), dimension_start_mm=None, dimension_end_source=Point2D(x=100, y=10), dimension_end_mm=None, text_position_source=Point2D(x=50, y=10), text_position_mm=None)
    payload["dimension_graphics"] = [graphic.model_dump(mode="json")]
    payload["dimensions"][0]["graphic_id"] = "missing"
    with pytest.raises(ValidationError, match="dimension has an unknown reference"):
        DrawingExtraction.model_validate(payload)


def test_reconstruction_scene_is_revision_bound_and_rejects_unordered_bounds() -> None:
    scene = ReconstructionScene(run_id="run-1", result_revision=2, state="ready", selected_scenario_id="scenario-between-sides", objects=(SceneObject(id="object-1", piece_id="piece-1", proposal_id="proposal-1", role="shelf", label="Balda", occurrence_index=1, position_mm=Point3D(x=18, y=300, z=0), dimensions_mm=Size3D(x=864, y=18, z=300), bbox_mm=Bounds3D(min=Point3D(x=18, y=300, z=0), max=Point3D(x=882, y=318, z=300)), source_contour_ids=("contour-1",), evidence_ids=("evidence-1",), placement_basis="confirmed_mounting_rule"),), assumptions=("selected_mounting_rule",), collision_status="not_evaluated")
    assert scene.result_revision == 2
    assert scene.coordinate_system == "x=width,y=height,z=depth; origin=front-left-bottom"
    with pytest.raises(ValidationError, match="bounds must be ordered"):
        Bounds3D(min=Point3D(x=2, y=0, z=0), max=Point3D(x=1, y=1, z=1))
