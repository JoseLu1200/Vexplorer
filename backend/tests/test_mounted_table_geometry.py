from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.geometria.extraction import extract_drawing


FIXTURES = Path("data/planos_demo")


def _analyze(fixture: str):
    try:
        from backend.app.geometria.mounted_table import analyze_mounted_table
    except ImportError as exc:  # pragma: no cover - exercised only in the RED step
        pytest.fail(f"mounted table analyzer is missing: {exc}")
    extraction = extract_drawing(
        FIXTURES / fixture,
        input_kind="mounted_orthographic_views",
    )
    return extraction, analyze_mounted_table(extraction)


def test_complete_views_expose_observed_envelope_and_unknown_profile_slots() -> None:
    extraction, analysis = _analyze("mesa_demo_001.dxf")

    measures = {item.semantic: item for item in analysis.measures}
    assert extraction.input_kind == "mounted_orthographic_views"
    assert analysis.drawing_id == extraction.drawing_id
    assert analysis.profile == "rectangular_table_v1"
    assert analysis.state == "needs_review"
    assert {
        semantic: (measures[semantic].value_mm, measures[semantic].state)
        for semantic in ("overall_width", "overall_height", "overall_depth")
    } == {
        "overall_width": (1200.0, "observed"),
        "overall_height": (750.0, "observed"),
        "overall_depth": (700.0, "observed"),
    }
    for semantic in ("overall_width", "overall_height", "overall_depth"):
        assert measures[semantic].measurement_ids
        assert measures[semantic].view_ids
        assert measures[semantic].evidence_ids
        assert measures[semantic].slot_origin == "drawing"
    for semantic in (
        "tabletop_thickness",
        "support_width",
        "support_depth",
        "support_thickness",
    ):
        measure = measures[semantic]
        assert measure.value_mm is None
        assert measure.state == "unknown"
        assert measure.slot_origin == "profile_required_slot"
        assert not measure.measurement_ids
        assert not measure.evidence_ids
    sections = sorted(
        (item.value_mm, item.geometry_relation, item.view_ids)
        for item in analysis.measures
        if item.semantic == "unknown" and item.axis == "section"
    )
    assert sections == [
        (18.0, "opposite_offsets", ("view-front",)),
        (30.0, "offset_from_max_y", ("view-front", "view-side")),
    ]
    for item in analysis.measures:
        if item.semantic == "unknown" and item.axis == "section":
            assert item.state == "observed"
            assert item.source_entity_ids
            assert item.evidence_ids
    assert set(analysis.admitted_measurement_ids) == {item.id for item in analysis.measures}


def test_dimensions_and_internal_sections_vary_with_drawing_geometry() -> None:
    _, analysis = _analyze("mesa_demo_002.dxf")

    measures = {item.semantic: item for item in analysis.measures if item.semantic != "unknown"}
    assert (measures["overall_width"].value_mm, measures["overall_height"].value_mm) == (1400.0, 760.0)
    assert measures["overall_depth"].value_mm == 800.0
    assert sorted(
        item.value_mm for item in analysis.measures
        if item.semantic == "unknown" and item.axis == "section" and item.state == "observed"
    ) == [20.0, 32.0]


def test_missing_side_view_is_visible_and_never_created_as_phantom_evidence() -> None:
    _, analysis = _analyze("mesa_demo_003.dxf")

    assert analysis.state == "needs_review"
    assert "missing_required_view:SIDE" in analysis.warnings
    assert all("view-side" not in item.view_ids for item in analysis.measures)
    measures = {item.semantic: item for item in analysis.measures if item.semantic != "unknown"}
    assert (measures["overall_width"].value_mm, measures["overall_height"].value_mm, measures["overall_depth"].value_mm) == (1200.0, 750.0, 700.0)


def test_conflicting_dimension_override_does_not_replace_geometry() -> None:
    _, analysis = _analyze("mesa_demo_004.dxf")

    width = next(item for item in analysis.measures if item.semantic == "overall_width")
    assert width.state == "conflict"
    assert width.value_mm is None
    assert width.measurement_ids == ("dimension-entity-98",)
    assert len(width.evidence_ids) >= 2
    assert "table_measure_conflict" in analysis.warnings

