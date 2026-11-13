from __future__ import annotations

import math

from backend.app.contratos.modelos import ComponentProposal, DecompositionScenario, DrawingExtraction, ExplanationBundle, FormulaExplanation, PieceExplanation, Result


def explain_proposal(extraction: DrawingExtraction, scenario: DecompositionScenario, proposal: ComponentProposal) -> PieceExplanation:
    observations = {item.id: item for item in extraction.observations}
    dimension_ids = tuple(sorted({dimension_id for observation_id in proposal.source_observation_ids if (observation := observations.get(observation_id)) for dimension_id in observation.dimension_ids}))
    field_states = {
        "quantity": "hypothesis" if proposal.quantity is not None else "unknown",
        "length_mm": "observed" if proposal.length_mm is not None and proposal.length_derivation == "direct_observation" else "unknown",
        "width_mm": "observed" if proposal.width_mm is not None else "unknown",
        "thickness_mm": "unknown", "material": "unknown", "finish": "unknown",
    }
    return PieceExplanation(piece_id=proposal.id, proposal_id=proposal.id, role=proposal.role, source_entity_ids=proposal.source_entity_ids, source_contour_ids=proposal.source_contour_ids, evidence_ids=proposal.evidence_ids, dimension_ids=dimension_ids, measurements={"quantity": proposal.quantity, "length_mm": proposal.length_mm, "width_mm": proposal.width_mm, "thickness_mm": proposal.thickness_mm}, formulas=(), premises=proposal.assumptions + scenario.assumptions, unknown_fields=tuple(sorted(field for field, state in field_states.items() if state == "unknown")), field_states=field_states)


def explain_result(extraction: DrawingExtraction, result: Result) -> ExplanationBundle:
    if result.input_semantics == "separated_part_views" and result.part_analysis is not None:
        return _explain_parts_result(result)
    proposals = {item.id: item for scenario in result.scenarios for item in scenario.components}
    observations = {item.id: item for item in extraction.observations}
    pieces: list[PieceExplanation] = []
    if not result.pieces:
        for scenario in result.scenarios:
            for proposal in scenario.components:
                pieces.append(explain_proposal(extraction, scenario, proposal))
        return ExplanationBundle(run_id=result.run_id, result_revision=result.result_revision, pieces=tuple(pieces), warnings=("hypotheses_require_human_review",))
    for piece in result.pieces:
        proposal = proposals[piece.proposal_id]
        dimension_ids = tuple(sorted({dimension_id for observation_id in proposal.source_observation_ids if (observation := observations.get(observation_id)) for dimension_id in observation.dimension_ids}))
        formulas: tuple[FormulaExplanation, ...] = ()
        if proposal.length_derivation in ("overall_width_minus_two_thickness", "overall_height_minus_two_thickness") and proposal.length_basis_mm is not None and piece.thickness_mm is not None and piece.length_mm is not None and math.isclose(piece.length_mm, proposal.length_basis_mm - 2 * piece.thickness_mm):
            basis_name = "overall_width_mm" if proposal.length_derivation == "overall_width_minus_two_thickness" else "overall_height_mm"
            formulas = (FormulaExplanation(field="length_mm", expression=f"{basis_name} - 2 * confirmed_thickness_mm", operands_mm={basis_name: proposal.length_basis_mm, "confirmed_thickness_mm": piece.thickness_mm}, result_mm=piece.length_mm),)
        premises = ["human_mounting_confirmation"]
        premises.extend(sorted(set(proposal.assumptions)))
        unknown_fields = tuple(sorted(field for field, state in piece.field_states.items() if state == "unknown"))
        pieces.append(PieceExplanation(piece_id=piece.id, proposal_id=piece.proposal_id, role=piece.role, source_entity_ids=proposal.source_entity_ids, source_contour_ids=piece.source_contour_ids, evidence_ids=piece.evidence_ids, dimension_ids=dimension_ids, measurements={"quantity": piece.quantity, "length_mm": piece.length_mm, "width_mm": piece.width_mm, "thickness_mm": piece.thickness_mm}, formulas=formulas, premises=tuple(premises), unknown_fields=unknown_fields, field_states=piece.field_states))
    warnings = ("result_has_unresolved_fields",) if any(item.unknown_fields for item in pieces) else ()
    return ExplanationBundle(run_id=result.run_id, result_revision=result.result_revision, pieces=tuple(pieces), warnings=warnings)


def _explain_parts_result(result: Result) -> ExplanationBundle:
    assert result.part_analysis is not None
    observations = {item.id: item for item in result.part_analysis.observations}
    candidates = (next(item for item in result.assembly_candidates if item.id == result.selected_assembly_candidate_id),) if result.selected_assembly_candidate_id else result.assembly_candidates
    uses = {item.id: (candidate, item) for candidate in candidates for item in candidate.uses}
    explanations: list[PieceExplanation] = []
    if not result.pieces:
        for use_id in sorted(uses):
            candidate, use = uses[use_id]
            observation = observations[use.part_observation_id]
            dimensions = observation.dimensions
            states = {"role": "hypothesis", "quantity": "observed" if use.allocated_quantity is not None else "unknown", "length_mm": dimensions.length.state if dimensions.length.state != "conflict" else "unknown", "width_mm": dimensions.width.state if dimensions.width.state != "conflict" else "unknown", "thickness_mm": dimensions.thickness.state if dimensions.thickness.state != "conflict" else "unknown", "material": "unknown", "finish": "unknown"}
            explanations.append(PieceExplanation(piece_id=use.id, proposal_id=use.id, role=use.role, source_entity_ids=observation.source_entity_ids, source_contour_ids=tuple(contour for view in observation.views for contour in view.contour_ids), evidence_ids=tuple(sorted(set(observation.evidence_ids) | set(use.evidence_ids))), dimension_ids=tuple(sorted(set(dimensions.length.measurement_ids + dimensions.width.measurement_ids + dimensions.thickness.measurement_ids))), measurements={"quantity": use.allocated_quantity, "length_mm": dimensions.length.value_mm, "width_mm": dimensions.width.value_mm, "thickness_mm": dimensions.thickness.value_mm}, formulas=(), premises=candidate.assumptions + ("role_assignment_is_hypothesis", "assembly_layout_is_hypothesis"), unknown_fields=tuple(sorted(field for field, state in states.items() if state == "unknown")), field_states=states))
        return ExplanationBundle(run_id=result.run_id, result_revision=result.result_revision, pieces=tuple(explanations), warnings=("assembly_hypotheses_require_human_review",))
    for piece in result.pieces:
        candidate, use = uses[piece.proposal_id]
        observation = observations[use.part_observation_id]
        explanations.append(PieceExplanation(piece_id=piece.id, proposal_id=piece.proposal_id, role=piece.role, source_entity_ids=observation.source_entity_ids, source_contour_ids=piece.source_contour_ids, evidence_ids=piece.evidence_ids, dimension_ids=tuple(sorted(set(observation.dimensions.length.measurement_ids + observation.dimensions.width.measurement_ids + observation.dimensions.thickness.measurement_ids))), measurements={"quantity": piece.quantity, "length_mm": piece.length_mm, "width_mm": piece.width_mm, "thickness_mm": piece.thickness_mm}, formulas=(), premises=candidate.assumptions + ("human_selected_assembly_candidate",), unknown_fields=tuple(sorted(field for field, state in piece.field_states.items() if state == "unknown")), field_states=piece.field_states))
    warnings = ("result_has_unresolved_fields",) if any(item.unknown_fields for item in explanations) else ()
    return ExplanationBundle(run_id=result.run_id, result_revision=result.result_revision, pieces=tuple(explanations), warnings=warnings)
