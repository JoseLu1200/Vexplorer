from __future__ import annotations

import math

from backend.app.contratos.modelos import DrawingExtraction, ExplanationBundle, FormulaExplanation, PieceExplanation, Result


def explain_result(extraction: DrawingExtraction, result: Result) -> ExplanationBundle:
    proposals = {item.id: item for scenario in result.scenarios for item in scenario.components}
    observations = {item.id: item for item in extraction.observations}
    pieces: list[PieceExplanation] = []
    if not result.pieces:
        for scenario in result.scenarios:
            for proposal in scenario.components:
                dimension_ids = tuple(sorted({dimension_id for observation_id in proposal.source_observation_ids if (observation := observations.get(observation_id)) for dimension_id in observation.dimension_ids}))
                field_states = {
                    "quantity": "hypothesis" if proposal.quantity is not None else "unknown",
                    "length_mm": "observed" if proposal.length_mm is not None and proposal.length_derivation == "direct_observation" else "unknown",
                    "width_mm": "observed" if proposal.width_mm is not None else "unknown",
                    "thickness_mm": "unknown", "material": "unknown", "finish": "unknown",
                }
                pieces.append(PieceExplanation(piece_id=proposal.id, proposal_id=proposal.id, role=proposal.role, source_entity_ids=proposal.source_entity_ids, source_contour_ids=proposal.source_contour_ids, evidence_ids=proposal.evidence_ids, dimension_ids=dimension_ids, measurements={"quantity": proposal.quantity, "length_mm": proposal.length_mm, "width_mm": proposal.width_mm, "thickness_mm": proposal.thickness_mm}, formulas=(), premises=proposal.assumptions + scenario.assumptions, unknown_fields=tuple(sorted(field for field, state in field_states.items() if state == "unknown")), field_states=field_states))
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
