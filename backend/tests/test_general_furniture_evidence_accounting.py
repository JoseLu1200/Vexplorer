from __future__ import annotations

import json

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.agente.runner import AgentLimits
from backend.app.contratos.modelos import (
    DrawingContour,
    DrawingEntity,
    GeneralBinding,
    GeneralConstructionParameter,
    GeneralDimensionRange,
    GeneralEvidenceDisposition,
    ProposeGeneralFurnitureArgs,
    GeneralValue,
    Point2D,
)
from backend.app.general_furniture.evidence_accounting import (
    build_evidence_accounting_report,
    derive_relevant_candidate_regions,
)
from backend.app.general_furniture.proposal import materialize_general_proposal
from backend.app.general_furniture.live import run_general_furniture_agent
from backend.tests.test_general_furniture_proposal import _extraction, _proposal


def _vector_case(*, assigned_count: int):
    entities = tuple(
        DrawingEntity(
            id=f"entity-{index}",
            kind="LWPOLYLINE",
            layer="outline",
            source_points=(Point2D(x=index * 20, y=0),),
            points_mm=(Point2D(x=index * 20, y=0),),
        )
        for index in range(10)
    )
    contours = tuple(
        DrawingContour(
            id=f"contour-{index}",
            view_id="view-front",
            source_entity_ids=(f"entity-{index}",),
            points_source=(
                Point2D(x=index * 20, y=0),
                Point2D(x=index * 20 + 10, y=0),
                Point2D(x=index * 20 + 10, y=10),
                Point2D(x=index * 20, y=10),
            ),
            points_mm=(
                Point2D(x=index * 20, y=0),
                Point2D(x=index * 20 + 10, y=0),
                Point2D(x=index * 20 + 10, y=10),
                Point2D(x=index * 20, y=10),
            ),
            closed=True,
        )
        for index in range(10)
    )
    view = _extraction().views[0].model_copy(
        update={"entity_ids": tuple(item.id for item in entities)}
    )
    extraction = _extraction().model_copy(
        update={"entities": entities, "views": (view,), "contours": contours}
    )
    regions = derive_relevant_candidate_regions(extraction)
    contour_ids = tuple(item.contour_ids[0] for item in regions[:assigned_count])
    base = _proposal()
    component = base.components[0].model_copy(update={
        "source_contour_ids": contour_ids,
        "width_binding_id": "panel-width",
        "thickness_binding_id": "panel-thickness",
        "unknown_fields": ("quantity",),
    })
    width_parameter = GeneralConstructionParameter(
        id="panel-width", label="Fondo provisional", basis="estimated",
        nominal_mm=400, range_mm=GeneralDimensionRange(min_mm=350, max_mm=450),
        method="construction_assumption", source_refs=("premise:p1",),
        assumption_refs=("premise:p1",),
        rationale="Valor acotado solo para probar el ciclo de reparación.",
    )
    thickness_parameter = GeneralConstructionParameter(
        id="panel-thickness", label="Espesor provisional", basis="estimated",
        nominal_mm=18, range_mm=GeneralDimensionRange(min_mm=16, max_mm=20),
        method="construction_assumption", source_refs=("premise:p1",),
        assumption_refs=("premise:p1",),
        rationale="Valor acotado solo para probar el ciclo de reparación.",
    )
    dispositions = tuple(
        GeneralEvidenceDisposition(
            candidate_region_id=region.id,
            kind="assigned",
            component_id=component.id,
            source_refs=(f"contour:{region.contour_ids[0]}",),
            rationale="La región se asocia provisionalmente al panel.",
        )
        for region in regions[:assigned_count]
    )
    proposal = base.model_copy(update={
        "bindings": (
            *base.bindings,
            GeneralBinding(id="panel-width", operation="copy", operand_refs=("parameter:panel-width",)),
            GeneralBinding(id="panel-thickness", operation="copy", operand_refs=("parameter:panel-thickness",)),
        ),
        "construction_parameters": (width_parameter, thickness_parameter),
        "components": (component,),
        "evidence_dispositions": dispositions,
    })
    draft = materialize_general_proposal(extraction, proposal)
    resolved = GeneralValue(
        value_mm=400,
        state="deduced",
        dependency_refs=("binding:synthetic-test",),
    )
    draft_component = draft.components[0].model_copy(
        update={"width": resolved, "thickness": resolved}
    )
    draft = draft.model_copy(
        update={
            "components": (draft_component,),
            "evidence_dispositions": dispositions,
        }
    )
    return extraction, proposal, draft, regions


def test_ninety_percent_evidence_accounting_does_not_hide_unresolved_region() -> None:
    extraction, proposal, draft, regions = _vector_case(assigned_count=9)

    report = build_evidence_accounting_report(extraction, proposal, draft)

    assert report.evidence_coverage == 0.9
    assert report.unresolved_region_ids == (regions[-1].id,)
    assert report.reviewable is False
    assert report.claims_physical_piece_recall is False


def test_typed_frame_or_void_disposition_accounts_evidence_without_creating_piece() -> None:
    extraction, proposal, draft, regions = _vector_case(assigned_count=9)
    frame = GeneralEvidenceDisposition(
        candidate_region_id=regions[-1].id,
        kind="nonmaterial",
        reason_code="drawing_frame",
        source_refs=(f"contour:{regions[-1].contour_ids[0]}",),
        rationale="Marco gráfico, pendiente de crítica visual dirigida.",
    )
    proposal = proposal.model_copy(
        update={"evidence_dispositions": (*proposal.evidence_dispositions, frame)}
    )
    draft = draft.model_copy(
        update={"evidence_dispositions": proposal.evidence_dispositions}
    )

    report = build_evidence_accounting_report(extraction, proposal, draft)

    assert report.unresolved_region_ids == ()
    assert f"evidence_region:{regions[-1].id}" in (
        report.required_disposition_review_targets
    )
    assert report.reviewable is True
    assert len(draft.components) == 1


def test_same_evidence_region_cannot_be_claimed_by_multiple_components() -> None:
    extraction, proposal, draft, regions = _vector_case(assigned_count=10)
    second = proposal.components[0].model_copy(
        update={"id": "panel-copy", "source_contour_ids": (regions[0].contour_ids[0],)}
    )
    proposal = proposal.model_copy(update={"components": (*proposal.components, second)})
    draft_second = draft.components[0].model_copy(update={"id": "panel-copy"})
    draft = draft.model_copy(update={"components": (*draft.components, draft_second)})

    report = build_evidence_accounting_report(extraction, proposal, draft)

    assert regions[0].id in report.invalid_region_ids
    assert "candidate_region_reused_by_components" in report.warnings
    assert report.reviewable is False


def test_invalid_region_feedback_identifies_the_specific_accounting_failure() -> None:
    extraction, proposal, draft, regions = _vector_case(assigned_count=10)
    second = proposal.components[0].model_copy(
        update={"id": "panel-copy", "source_contour_ids": (regions[0].contour_ids[0],)}
    )
    proposal = proposal.model_copy(update={"components": (*proposal.components, second)})
    draft_second = draft.components[0].model_copy(update={"id": "panel-copy"})
    draft = draft.model_copy(update={"components": (*draft.components, draft_second)})

    report = build_evidence_accounting_report(extraction, proposal, draft)

    assert report.invalid_region_reasons == (
        (regions[0].id, "candidate_region_reused_by_components"),
    )


def test_many_regions_assigned_to_one_component_require_directed_review() -> None:
    extraction, proposal, draft, regions = _vector_case(assigned_count=10)

    report = build_evidence_accounting_report(extraction, proposal, draft)

    assert report.multi_region_component_ids == ("panel",)
    assert report.required_disposition_review_targets == tuple(
        sorted(f"evidence_region:{region.id}" for region in regions)
    )
    assert "component_claims_multiple_candidate_regions_requires_directed_review" in report.warnings


def test_panel_dimensions_must_be_numeric_and_traceable_before_review() -> None:
    extraction, proposal, draft, _ = _vector_case(assigned_count=10)
    component = draft.components[0].model_copy(
        update={
            "width": GeneralValue(value_mm=None, state="unknown"),
            "thickness": GeneralValue(value_mm=18, state="hypothesis"),
        }
    )
    draft = draft.model_copy(update={"components": (component,)})

    report = build_evidence_accounting_report(extraction, proposal, draft)

    assert report.missing_dimension_targets == ("component:panel.width",)
    assert report.untraceable_dimension_targets == ("component:panel.thickness",)
    assert report.reviewable is False


def test_unknown_disposition_is_invalid_even_without_vector_regions() -> None:
    extraction = _extraction()
    base = _proposal()
    disposition = GeneralEvidenceDisposition(
        candidate_region_id="evidence-candidate:not-in-ledger",
        kind="nonmaterial",
        reason_code="drawing_frame",
        source_refs=("contour:not-in-ledger",),
        rationale="Referencia inexistente.",
    )
    proposal = base.model_copy(update={"evidence_dispositions": (disposition,)})
    draft = materialize_general_proposal(extraction, proposal)

    report = build_evidence_accounting_report(extraction, proposal, draft)

    assert report.invalid_region_ids == ("evidence-candidate:not-in-ledger",)
    assert report.reviewable is False


def _proposal_arguments(proposal) -> dict:
    payload = proposal.model_dump(mode="json")
    return {
        field: payload[field]
        for field in ProposeGeneralFurnitureArgs.model_fields
    }


def test_live_proposer_receives_unresolved_regions_and_repairs_before_returning() -> None:
    extraction, incomplete, _, regions = _vector_case(assigned_count=9)
    _, repaired, _, _ = _vector_case(assigned_count=10)

    class Provider:
        calls = 0
        repair_input = None

        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            self.calls += 1
            if self.calls > 1:
                self.repair_input = input_items
            proposal = incomplete if self.calls == 1 else repaired
            return ProviderResponse(
                id=f"response-{self.calls}",
                model="fake",
                tool_calls=(ToolCall(
                    call_id=f"call-{self.calls}",
                    name="proponer_mueble_general",
                    arguments_json=json.dumps(_proposal_arguments(proposal)),
                ),),
            )

    provider = Provider()
    outcome = run_general_furniture_agent(
        extraction,
        ledger_revision="ledger-1",
        provider=provider,
    )

    feedback = json.loads(provider.repair_input[0]["output"])
    assert provider.calls == 2
    assert feedback["error"] == "invalid_arguments"
    assert feedback["details"][0]["msg"] == "proposal_evidence_accounting_incomplete"
    assert feedback["details"][0]["unresolved_candidate_region_ids"] == [
        regions[-1].id
    ]
    assert len(outcome.proposal.evidence_dispositions) == 10


def test_live_preserves_last_incomplete_proposal_after_bounded_repair_budget() -> None:
    extraction, incomplete, _, regions = _vector_case(assigned_count=9)

    class Provider:
        calls = 0

        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            self.calls += 1
            return ProviderResponse(
                id=f"response-{self.calls}",
                model="fake",
                tool_calls=(ToolCall(
                    call_id=f"call-{self.calls}",
                    name="proponer_mueble_general",
                    arguments_json=json.dumps(_proposal_arguments(incomplete)),
                ),),
            )

    provider = Provider()
    outcome = run_general_furniture_agent(
        extraction,
        ledger_revision="ledger-1",
        provider=provider,
        limits=AgentLimits(max_validation_repairs=1),
    )

    assert provider.calls == 2
    assert outcome.proposal.evidence_dispositions[-1].candidate_region_id != regions[-1].id
    assert outcome.trace[-1]["ok"] is False
    assert "preserved as incomplete" in outcome.trace[-1]["summary"]


def test_live_preserves_last_incomplete_proposal_when_provider_response_ends() -> None:
    extraction, incomplete, _, _ = _vector_case(assigned_count=9)

    class ProviderFailure(RuntimeError):
        code = "provider_response_incomplete"

    class Provider:
        calls = 0

        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            self.calls += 1
            if self.calls == 2:
                raise ProviderFailure("provider payload must not escape")
            return ProviderResponse(
                id="response-1",
                model="fake",
                tool_calls=(ToolCall(
                    call_id="call-1",
                    name="proponer_mueble_general",
                    arguments_json=json.dumps(_proposal_arguments(incomplete)),
                ),),
            )

    provider = Provider()
    outcome = run_general_furniture_agent(
        extraction,
        ledger_revision="ledger-1",
        provider=provider,
        limits=AgentLimits(max_model_calls=3, max_validation_repairs=2),
    )

    assert provider.calls == 2
    assert outcome.proposal.evidence_dispositions == incomplete.evidence_dispositions
    assert outcome.trace[-1]["reason_code"] == "provider_response_incomplete"
    assert outcome.trace[-1]["ok"] is False
    assert "preserved as incomplete" in outcome.trace[-1]["summary"]


def test_live_bounds_inspections_after_an_incomplete_proposal() -> None:
    extraction, incomplete, _, _ = _vector_case(assigned_count=9)

    class Provider:
        calls = 0

        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            self.calls += 1
            if self.calls == 1:
                call = ToolCall(
                    call_id="proposal-call",
                    name="proponer_mueble_general",
                    arguments_json=json.dumps(_proposal_arguments(incomplete)),
                )
            else:
                call = ToolCall(
                    call_id=f"inspect-call-{self.calls}",
                    name="inspeccionar_evidencia_general",
                    arguments_json=json.dumps({
                        "evidence_ids": [],
                        "view_ids": ["view-front"],
                        "measurement_ids": [],
                        "query_measurements": False,
                        "measurement_offset": 0,
                        "measurement_limit": 64,
                    }),
                )
            return ProviderResponse(
                id=f"response-{self.calls}", model="fake", tool_calls=(call,)
            )

    provider = Provider()
    outcome = run_general_furniture_agent(
        extraction,
        ledger_revision="ledger-1",
        provider=provider,
        limits=AgentLimits(max_model_calls=20, max_validation_repairs=2),
    )

    assert provider.calls == 3
    assert outcome.proposal.evidence_dispositions == incomplete.evidence_dispositions
    assert outcome.trace[-1]["reason_code"] == "post_proposal_inspection_budget_exhausted"
    assert outcome.trace[-1]["ok"] is False
