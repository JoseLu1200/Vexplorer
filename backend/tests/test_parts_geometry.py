from __future__ import annotations

from pathlib import Path

import ezdxf

from backend.app.geometria.extraction import extract_drawing
from backend.app.geometria.parts import derive_assembly_candidates, extract_separated_parts


def _parts_drawing(
    tmp_path: Path,
    *,
    unit_code: int = 4,
    top_length: float = 800.0,
    quantity: int | None = 2,
    translation: tuple[float, float] = (0.0, 0.0),
) -> Path:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = unit_code
    modelspace = document.modelspace()
    tx, ty = translation
    views = (
        ("FRONT", 800.0, 300.0, 0.0),
        ("TOP", top_length, 18.0, 1200.0),
        ("SIDE", 18.0, 300.0, 2400.0),
    )
    for role, width, height, offset in views:
        x, y = tx + offset, ty
        modelspace.add_lwpolyline(
            [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
            close=True,
        )
        horizontal = modelspace.add_linear_dim(base=(x, y - 40), p1=(x, y), p2=(x + width, y))
        horizontal.render()
        vertical = modelspace.add_linear_dim(base=(x - 40, y), p1=(x, y), p2=(x, y + height), angle=90)
        vertical.render()
        modelspace.add_text(f"PART P01 {role}").set_placement((x + width / 2, y + height / 2))
    if quantity is not None:
        modelspace.add_text(f"QTY P01 {quantity}").set_placement((tx + 400, ty + 100))
    path = tmp_path / "parts.dxf"
    document.saveas(path)
    return path


def test_parts_mode_exposes_distinct_explicitly_keyed_views(tmp_path: Path) -> None:
    extraction = extract_drawing(
        _parts_drawing(tmp_path), input_kind="separated_part_views",
    )

    assert extraction.input_kind == "separated_part_views"
    assert [(view.id, view.label) for view in extraction.views] == [
        ("view-part-p01-front", "FRONT"),
        ("view-part-p01-side", "SIDE"),
        ("view-part-p01-top", "TOP"),
    ]


def test_separated_part_views_resolve_local_axes_and_explicit_quantity(tmp_path: Path) -> None:
    extraction = extract_drawing(
        _parts_drawing(tmp_path), input_kind="separated_part_views",
    )

    parts = extract_separated_parts(extraction)

    assert len(parts.observations) == 1
    observation = parts.observations[0]
    assert observation.part_key == "P01"
    assert observation.association_basis == "explicit_key"
    assert [(view.role, view.local_bounds_mm.model_dump()) for view in observation.views] == [
        ("FRONT", {"min_x": 0.0, "min_y": 0.0, "max_x": 800.0, "max_y": 300.0}),
        ("SIDE", {"min_x": 0.0, "min_y": 0.0, "max_x": 18.0, "max_y": 300.0}),
        ("TOP", {"min_x": 0.0, "min_y": 0.0, "max_x": 800.0, "max_y": 18.0}),
    ]
    assert observation.dimensions.length.value_mm == 800.0
    assert observation.dimensions.width.value_mm == 300.0
    assert observation.dimensions.thickness.value_mm == 18.0
    assert observation.quantity.value == 2
    assert observation.quantity.state == "observed"
    assert observation.status == "complete"


def test_views_never_supply_quantity_and_unknown_units_never_supply_mm(tmp_path: Path) -> None:
    extraction = extract_drawing(
        _parts_drawing(tmp_path, unit_code=0, quantity=None),
        input_kind="separated_part_views",
    )

    observation = extract_separated_parts(extraction).observations[0]

    assert observation.quantity.value is None
    assert observation.quantity.state == "unknown"
    assert all(
        dimension.value_mm is None and dimension.state == "unknown"
        for dimension in (
            observation.dimensions.length,
            observation.dimensions.width,
            observation.dimensions.thickness,
        )
    )
    assert observation.status == "partial"


def test_disagreeing_views_preserve_dimension_conflict(tmp_path: Path) -> None:
    extraction = extract_drawing(
        _parts_drawing(tmp_path, top_length=810.0),
        input_kind="separated_part_views",
    )

    observation = extract_separated_parts(extraction).observations[0]

    assert observation.dimensions.length.value_mm is None
    assert observation.dimensions.length.state == "conflict"
    assert len(observation.dimensions.length.view_ids) == 2
    assert len(observation.dimensions.length.evidence_ids) >= 2
    assert "dimension_conflict:P01:length" in observation.warnings


def test_translation_changes_source_origins_but_not_local_part_analysis(tmp_path: Path) -> None:
    first = extract_separated_parts(extract_drawing(
        _parts_drawing(tmp_path), input_kind="separated_part_views",
    ))
    translated_dir = tmp_path / "translated"
    translated_dir.mkdir()
    second = extract_separated_parts(extract_drawing(
        _parts_drawing(translated_dir, translation=(5000.0, 2500.0)),
        input_kind="separated_part_views",
    ))

    assert first.candidate_revision == second.candidate_revision
    assert first.observations[0].dimensions == second.observations[0].dimensions
    assert first.observations[0].views[0].local_origin_source != second.observations[0].views[0].local_origin_source
    assert first.observations[0].views[0].local_bounds_source == second.observations[0].views[0].local_bounds_source


def test_public_complete_fixture_extracts_three_physical_part_types() -> None:
    extraction = extract_drawing(
        Path("data/planos_demo/piezas_completo.dxf"), input_kind="separated_part_views",
    )

    parts = extract_separated_parts(extraction)

    assert [item.part_key for item in parts.observations] == ["K1", "K2", "K3"]
    assert [item.quantity.value for item in parts.observations] == [2, 2, 2]
    assert [
        (item.dimensions.length.value_mm, item.dimensions.width.value_mm, item.dimensions.thickness.value_mm)
        for item in parts.observations
    ] == [(1200.0, 300.0, 18.0), (864.0, 300.0, 18.0), (864.0, 300.0, 18.0)]


def test_views_without_keys_remain_three_unassociated_observations() -> None:
    extraction = extract_drawing(
        Path("data/planos_demo/piezas_ambigua_sin_id.dxf"), input_kind="separated_part_views",
    )

    parts = extract_separated_parts(extraction)

    assert len(parts.observations) == 3
    assert all(item.part_key is None for item in parts.observations)
    assert all(item.association_basis == "unassociated" for item in parts.observations)
    assert all(item.status == "ambiguous" for item in parts.observations)
    assert all(len(item.views) == 1 for item in parts.observations)
    assert {item.views[0].view_id for item in parts.observations} <= {view.id for view in extraction.views}
    assert all(item.quantity.value is None and item.quantity.state == "unknown" for item in parts.observations)
    assert any(warning.startswith("unassociated_quantity_annotation:") for warning in parts.warnings)


def test_complete_types_preserve_only_dimensionally_compatible_role_hypotheses() -> None:
    parts = extract_separated_parts(extract_drawing(
        Path("data/planos_demo/piezas_completo.dxf"), input_kind="separated_part_views",
    ))

    candidates = derive_assembly_candidates(parts)

    assert len(candidates) == 2
    assert {item.layout for item in candidates} == {"between_sides"}
    assert all(item.family == "rectangular_shelving" and item.needs_review for item in candidates)
    assert all({use.part_observation_id for use in item.uses} == {part.id for part in parts.observations} for item in candidates)
    assert all(sum(use.allocated_quantity or 0 for use in item.uses) == 6 for item in candidates)
    assert all({dimension.axis for dimension in item.derived_dimensions} == {"width", "height", "depth"} for item in candidates)
    split_candidates = [
        item for item in candidates
        if any(use.part_observation_id == "part-observation-k2" and use.role == "top_panel" for use in item.uses)
    ]
    assert split_candidates
    assert all(
        {(use.role, use.occurrence_indices) for use in item.uses if use.part_observation_id == "part-observation-k2"}
        == {("top_panel", (1,)), ("base_panel", (2,))}
        for item in split_candidates
    )


def test_cap_sides_is_rejected_when_shelf_does_not_fit_between_sides() -> None:
    parts = extract_separated_parts(extract_drawing(
        Path("data/planos_demo/piezas_completo.dxf"), input_kind="separated_part_views",
    ))

    candidates = derive_assembly_candidates(parts)

    assert not any(item.layout == "cap_sides" for item in candidates)


def test_unknown_quantity_remains_null_in_candidates() -> None:
    parts = extract_separated_parts(extract_drawing(
        Path("data/planos_demo/piezas_qty_desconocida.dxf"), input_kind="separated_part_views",
    ))

    candidates = derive_assembly_candidates(parts)

    assert candidates
    uses = [
        use for item in candidates for use in item.uses
        if use.part_observation_id == "part-observation-k3"
    ]
    assert uses
    assert all(
        use.source_quantity is None
        and use.allocated_quantity is None
        and use.occurrence_indices == ()
        and use.quantity_source == "unknown"
        for use in uses
    )


def test_unassociated_views_do_not_create_an_assembly_candidate() -> None:
    parts = extract_separated_parts(extract_drawing(
        Path("data/planos_demo/piezas_ambigua_sin_id.dxf"), input_kind="separated_part_views",
    ))

    assert derive_assembly_candidates(parts) == ()


def test_conflicting_dimension_annotation_blocks_bbox_from_becoming_a_part_measurement(tmp_path: Path) -> None:
    path = _parts_drawing(tmp_path, quantity=1)
    document = ezdxf.readfile(path)
    dimension = document.modelspace().add_linear_dim(
        base=(0, -50), p1=(0, 0), p2=(800, 0), override={"dimlfac": 2},
    )
    dimension.render()
    document.saveas(path)

    parts = extract_separated_parts(extract_drawing(
        path, input_kind="separated_part_views",
    ))

    length = parts.observations[0].dimensions.length
    assert length.value_mm is None
    assert length.state == "conflict"
    assert length.measurement_ids
    assert len(length.evidence_ids) >= 2
    assert "dimension_annotation_conflict:P01:length" in parts.observations[0].warnings
