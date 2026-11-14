from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.contratos.modelos import DrawingExtraction, TableConfirmedValue, TableProgramProposal, TableReviewDecision
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


def _catalog(analysis):
    try:
        from backend.app.geometria.mounted_table import catalog_table_programs
    except ImportError as exc:  # pragma: no cover - exercised only in the RED step
        pytest.fail(f"mounted table catalog is missing: {exc}")
    return catalog_table_programs(analysis)


def _evaluate(analysis, program, decisions=(), confirmed_values=()):
    try:
        from backend.app.geometria.mounted_table import evaluate_table_program
    except ImportError as exc:  # pragma: no cover - exercised only in the RED step
        pytest.fail(f"mounted table evaluator is missing: {exc}")
    return evaluate_table_program(
        analysis, program, decisions=decisions, confirmed_values=confirmed_values,
    )


def _accept_all(program):
    return (
        TableReviewDecision(target_kind="program", target_id=program.id, action="accept", reason="Selecciona esta topología"),
        *(TableReviewDecision(target_kind="component", target_id=item.id, action="accept", reason="Acepta el tipo propuesto") for item in program.components),
        *(TableReviewDecision(target_kind="premise", target_id=item.id, action="accept", reason="Acepta la premisa explícita") for item in program.premises),
    )


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


def test_catalog_lists_both_support_topologies_and_binds_observed_sections() -> None:
    _, analysis = _analyze("mesa_demo_001.dxf")

    programs = _catalog(analysis)

    assert [item.table_template_id for item in programs] == [
        "side_supports_v1",
        "corner_supports_v1",
    ]
    assert all(item.proposal_origin == "catalog_baseline" for item in programs)
    section_ids = {
        item.geometry_relation: item.id
        for item in analysis.measures
        if item.semantic == "unknown" and item.axis == "section"
    }
    side = programs[0]
    side_measure_refs = {
        operand.ref_id
        for binding in side.bindings
        for operand in binding.operand_refs
        if operand.ref_type == "measure"
    }
    assert section_ids["offset_from_max_y"] in side_measure_refs
    assert section_ids["opposite_offsets"] in side_measure_refs
    assert {item.role for item in side.components} == {"tabletop", "side_support"}
    assert {item.quantity_rule_id for item in side.components} == {"top_one", "two_side_supports"}
    corner = programs[1]
    assert {item.role for item in corner.components} == {"tabletop", "corner_support"}
    assert {item.quantity_rule_id for item in corner.components} == {"top_one", "four_corner_supports"}
    assert all(not hasattr(binding, "value_mm") for program in programs for binding in program.bindings)


def test_side_support_program_stays_proposed_until_each_target_is_accepted() -> None:
    _, analysis = _analyze("mesa_demo_001.dxf")
    program = _catalog(analysis)[0]

    proposed = _evaluate(analysis, program)

    assert proposed.state == "hypothesis"
    assert [item.quantity for item in proposed.components] == [1, 2]
    assert len(proposed.occurrences) == 3
    assert all(item.result.state == "proposed" for item in proposed.bindings)
    assert all(not item.accepted for item in proposed.components)
    assert all(item.state == "proposed" for item in proposed.placements)

    decisions = _accept_all(program)
    completed = _evaluate(analysis, program, decisions=decisions)

    assert completed.state == "completed"
    assert completed.overall_dimensions.model_dump() == {
        "width_mm": 1200.0,
        "depth_mm": 700.0,
        "height_mm": 750.0,
    }
    assert all(item.result.state == "calculated" for item in completed.bindings)
    assert all(item.accepted for item in completed.components)
    assert all(item.state == "pass" for item in completed.placements)
    placements = {item.occurrence_id: item for item in completed.placements}
    top = placements["occurrence-component-tabletop-1"]
    assert top.position_mm.model_dump() == {"x": 0.0, "y": 720.0, "z": 0.0}
    assert top.dimensions_mm.model_dump() == {"x": 1200.0, "y": 30.0, "z": 700.0}
    sides = [item for key, item in placements.items() if "side-support" in key]
    assert sorted(item.position_mm.x for item in sides) == [0.0, 1182.0]
    assert all(item.dimensions_mm.model_dump() == {"x": 18.0, "y": 720.0, "z": 700.0} for item in sides)


def test_swapped_tabletop_axes_cannot_be_approved_into_a_completed_program() -> None:
    _, analysis = _analyze("mesa_demo_001.dxf")
    original = _catalog(analysis)[0]
    bindings = {item.id: item for item in original.bindings}
    swapped = original.model_copy(update={
        "bindings": tuple(
            item.model_copy(update={
                "operand_refs": bindings[
                    "binding-top-width" if item.id == "binding-top-length" else "binding-top-length"
                ].operand_refs,
            }) if item.id in {"binding-top-length", "binding-top-width"} else item
            for item in original.bindings
        ),
    })

    evaluated = _evaluate(analysis, swapped, decisions=_accept_all(swapped))

    assert evaluated.state == "needs_review"
    assert any(item.code == "registry_semantic_mismatch" for item in evaluated.issues)
    assert any(item.state == "conflict" for item in evaluated.placements)


def test_component_evidence_is_derived_from_binding_operands_not_tool_claims() -> None:
    _, analysis = _analyze("mesa_demo_001.dxf")
    original = _catalog(analysis)[0]
    ungrounded = original.model_copy(update={
        "evidence_ids": (),
        "components": tuple(item.model_copy(update={"evidence_ids": ()}) for item in original.components),
    })

    evaluated = _evaluate(analysis, ungrounded, decisions=_accept_all(ungrounded))

    assert evaluated.state == "completed"
    assert all(item.evidence_ids for item in evaluated.components)
    binding_evidence = {
        item.id: set(item.result.evidence_ids) for item in evaluated.bindings
    }
    for component in evaluated.components:
        spec = next(item for item in ungrounded.components if item.id == component.id)
        expected = set().union(*(
            binding_evidence[spec.length_binding_id],
            binding_evidence[spec.width_binding_id],
            binding_evidence[spec.thickness_binding_id],
        ))
        assert set(component.evidence_ids) == expected


def test_review_cannot_confirm_a_support_section_outside_the_table_envelope() -> None:
    _, analysis = _analyze("mesa_demo_001.dxf")
    program = _catalog(analysis)[1]
    support_depth = next(item for item in analysis.measures if item.semantic == "support_depth")

    evaluated = _evaluate(
        analysis, program, decisions=_accept_all(program),
        confirmed_values=(TableConfirmedValue(
            target_id=support_depth.id, value_mm=900.0,
            reason="Valor humano deliberadamente incompatible con la profundidad global.",
        ),),
    )

    assert evaluated.state == "needs_review"
    assert any(item.code == "placement_outside_envelope" for item in evaluated.issues)
    assert any(item.state == "conflict" for item in evaluated.placements)


def test_redundant_observed_measure_is_visible_but_non_blocking() -> None:
    _, analysis = _analyze("mesa_demo_001.dxf")
    program = _catalog(analysis)[0]
    width = next(item for item in analysis.measures if item.semantic == "overall_width")
    redundant = width.model_copy(update={"id": "table-measure-overall-width-redundant"})
    analysis_with_redundancy = analysis.model_copy(update={
        "measures": (*analysis.measures, redundant),
        "admitted_measurement_ids": (*analysis.admitted_measurement_ids, redundant.id),
    })

    evaluated = _evaluate(
        analysis_with_redundancy, program, decisions=_accept_all(program),
    )

    disposition = next(
        item for item in evaluated.measurement_dispositions
        if item.measurement_id == redundant.id
    )
    assert disposition.blocking is False
    assert "redundant" in disposition.reason.lower()
    assert evaluated.state == "completed"


def test_corner_support_program_needs_one_explicit_section_before_five_placements() -> None:
    _, analysis = _analyze("mesa_demo_001.dxf")
    program = _catalog(analysis)[1]
    decisions = _accept_all(program)

    incomplete = _evaluate(analysis, program, decisions=decisions)

    assert incomplete.state == "needs_review"
    assert len(incomplete.occurrences) == 5
    assert any(item.state == "unknown" for item in incomplete.placements)
    support_depth = next(item for item in analysis.measures if item.semantic == "support_depth")
    completed = _evaluate(
        analysis,
        program,
        decisions=decisions,
        confirmed_values=(TableConfirmedValue(
            target_id=support_depth.id, value_mm=70.0,
            reason="La persona confirma la sección profunda del soporte.",
        ),),
    )

    assert completed.state == "completed"
    assert len(completed.placements) == 5
    assert all(item.state == "pass" for item in completed.placements)
    legs = [
        item for item in completed.placements
        if "corner-support" in item.occurrence_id
    ]
    assert sorted((item.position_mm.x, item.position_mm.z) for item in legs) == [
        (0.0, 0.0),
        (0.0, 630.0),
        (1182.0, 0.0),
        (1182.0, 630.0),
    ]
    assert all(item.dimensions_mm.model_dump() == {"x": 18.0, "y": 720.0, "z": 70.0} for item in legs)


def test_accepting_hypotheses_cannot_hide_a_missing_required_view() -> None:
    _, analysis = _analyze("mesa_demo_003.dxf")
    program = _catalog(analysis)[0]

    evaluated = _evaluate(analysis, program, decisions=_accept_all(program))

    assert evaluated.state == "needs_review"
    assert any(item.code == "missing_required_view" and item.severity == "error" for item in evaluated.issues)


def test_program_hash_ignores_arbitrary_ids_and_component_order() -> None:
    _, analysis = _analyze("mesa_demo_001.dxf")
    original = _catalog(analysis)[0]
    binding_ids = {item.id: f"arbitrary-binding-{index}" for index, item in enumerate(original.bindings, start=1)}
    premise_ids = {item.id: f"arbitrary-premise-{index}" for index, item in enumerate(original.premises, start=1)}
    renamed_bindings = tuple(
        item.model_copy(update={
            "id": binding_ids[item.id],
            "operand_refs": tuple(
                operand.model_copy(update={"ref_id": binding_ids[operand.ref_id]})
                if operand.ref_type == "binding" else operand
                for operand in item.operand_refs
            ),
        })
        for item in original.bindings
    )
    renamed_components = tuple(
        item.model_copy(update={
            "id": f"arbitrary-component-{index}",
            "length_binding_id": binding_ids[item.length_binding_id],
            "width_binding_id": binding_ids[item.width_binding_id],
            "thickness_binding_id": binding_ids[item.thickness_binding_id],
            "premise_ids": tuple(premise_ids[premise_id] for premise_id in item.premise_ids),
        })
        for index, item in enumerate(reversed(original.components), start=1)
    )
    renamed = TableProgramProposal.model_validate({
        **original.model_dump(),
        "id": "arbitrary-program-id",
        "bindings": [item.model_dump() for item in renamed_bindings],
        "components": [item.model_dump() for item in renamed_components],
        "premises": [
            item.model_copy(update={"id": premise_ids[item.id]}).model_dump()
            for item in reversed(original.premises)
        ],
    })

    assert _evaluate(analysis, renamed).program_hash == _evaluate(analysis, original).program_hash


def test_human_overlay_resolves_effective_conflict_without_mutating_cad_measure() -> None:
    _, analysis = _analyze("mesa_demo_004.dxf")
    program = _catalog(analysis)[0]
    width = next(item for item in analysis.measures if item.semantic == "overall_width")

    conflicted = _evaluate(analysis, program, decisions=_accept_all(program))
    resolved = _evaluate(
        analysis,
        program,
        decisions=_accept_all(program),
        confirmed_values=(TableConfirmedValue(
            target_id=width.id, value_mm=1200.0,
            reason="La persona resuelve el conflicto visible 1190/1200.",
        ),),
    )

    assert conflicted.state == "needs_review"
    assert any(item.state == "conflict" for item in conflicted.placements)
    assert resolved.state == "completed"
    assert resolved.overall_dimensions.width_mm == 1200.0
    assert width.state == "conflict"
    assert width.value_mm is None


def test_metric_envelope_remains_observed_when_general_dimensions_are_absent() -> None:
    extraction = extract_drawing(
        FIXTURES / "mesa_demo_001.dxf", input_kind="mounted_orthographic_views",
    )
    payload = extraction.model_dump()
    payload["dimensions"] = ()
    payload["dimension_graphics"] = ()
    payload["observations"] = tuple(
        {**item, "dimension_ids": ()} for item in payload["observations"]
    )
    without_dimensions = DrawingExtraction.model_validate(payload)
    from backend.app.geometria.mounted_table import analyze_mounted_table

    analysis = analyze_mounted_table(without_dimensions)

    overall = [item for item in analysis.measures if item.semantic.startswith("overall_")]
    assert [(item.semantic, item.value_mm) for item in overall] == [
        ("overall_width", 1200.0),
        ("overall_height", 750.0),
        ("overall_depth", 700.0),
    ]
    assert all(item.state == "observed" for item in overall)
    assert all(item.geometry_relation == "envelope_extent" for item in overall)
    assert all(not item.measurement_ids for item in overall)

