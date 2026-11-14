from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.contratos.modelos import GeneralAutoReviewCheck, GeneralMachineFieldReview, GeneralMachineProvenance, GeneralScenarioOccurrence, GeneralValue
from backend.app.general_furniture.autonomous import GeneralAutonomousError
from backend.app.general_furniture.autonomous import GENERAL_AUTO_REVIEW_PROMPT
from backend.app.general_furniture.autonomous import run_general_autonomous
from backend.app.general_furniture.autonomous import _reject_forged_machine_facts
from backend.app.general_furniture.autonomous import _review_input
from backend.app.general_furniture.autonomous import _materialize_repair
from backend.app.general_furniture.autonomous import _scenario_occurrences
from backend.app.general_furniture.autonomous import _tool_schemas
from backend.app.general_furniture.autonomous import _validate_visual_checks
from backend.app.general_furniture.live import GeneralFurnitureAgentOutcome, GeneralVisualPage
from backend.app.general_furniture.proposal import materialize_general_proposal
from backend.app.general_furniture.router import GeneralFurnitureContext
from backend.tests.test_general_furniture_proposal import _extraction, _proposal


def test_machine_review_is_orthogonal_to_hypothesis_state() -> None:
    value = GeneralValue(value_mm=600, state="hypothesis", dependency_refs=("measurement:contour:c1:span-x",))
    provenance = GeneralMachineProvenance(model="gpt-reviewer", policy_version="general-auto-review-v1", response_ids=("resp-1",), review_relation="separate_model")
    check = GeneralAutoReviewCheck(id="geometry-match", kind="geometry_match", outcome="pass", method="deterministic", target_refs=("component:c1.length",), source_refs=("measurement:contour:c1:span-x",), summary="La medida propuesta coincide con el ledger geométrico.")
    field_review = GeneralMachineFieldReview(target_ref="component:c1.length", status="accepted", check_ids=(check.id,))
    assert value.state == "hypothesis"
    assert provenance.review_relation == "separate_model"
    assert field_review.status == "accepted"


def test_critic_tool_only_accepts_checks_and_decisions_not_component_rewrites() -> None:
    schema = next(item for item in _tool_schemas() if item["name"] == "entregar_revision_autonoma")
    properties = schema["parameters"]["properties"]

    assert "components" not in properties
    assert "operations" not in properties
    assert {"scenario_id", "checks", "field_reviews", "unresolved", "status"} <= set(properties)


def test_critic_and_repair_reject_cross_geometry_observed_dimension_transfer() -> None:
    repair = next(
        item["description"]
        for item in _tool_schemas()
        if item["name"] == "proponer_mueble_general"
    )

    assert "misma geometría visible" in GENERAL_AUTO_REVIEW_PROMPT
    assert "pieza oculta" in GENERAL_AUTO_REVIEW_PROMPT
    assert "parámetro estimated separado" in repair
    assert "estabilidad" in GENERAL_AUTO_REVIEW_PROMPT
    assert "detalle estimated explícito" in repair


def test_provisional_occurrence_is_not_a_confirmed_physical_occurrence() -> None:
    occurrence = GeneralScenarioOccurrence(id="provisional:c1:1", component_id="c1", occurrence_index=1, scenario_id="scenario-auto-1", quantity_target_ref="component:c1.quantity", check_ids=("quantity-basis", "duplicate-scan"), premise_refs=("premise:four",), source_refs=("visual:page-1",))
    assert occurrence.state == "provisional"


def test_hypothesis_quantity_with_visual_basis_creates_only_scenario_occurrences() -> None:
    from backend.app.contratos.modelos import (
        GeneralAutoReviewArgs,
        GeneralComponentReview,
        GeneralQuantity,
        GeneralModelVisualCheck,
        GeneralReviewOperation,
        GeneralTextValue,
    )

    source = materialize_general_proposal(_extraction(), _proposal()).components[0]
    component = GeneralComponentReview(
        id="two-sides", label=source.label, kind=source.kind, role=source.role,
        length=source.length, width=source.width, thickness=source.thickness,
        quantity=GeneralQuantity(value=2, state="hypothesis", dependency_refs=("premise:two-instances",)),
        material=GeneralTextValue(value=None, state="unknown"), finish=GeneralTextValue(value=None, state="unknown"),
        replaces_component_ids=(source.id,), source_view_ids=source.source_view_ids,
        source_observation_ids=source.source_observation_ids, source_evidence_ids=source.source_evidence_ids,
        source_dimension_ids=source.source_dimension_ids, assumptions=("Dos grupos visuales distintos.",),
        unknown_fields=("width", "thickness", "material", "finish"),
    )
    checks = (
        GeneralModelVisualCheck(id="quantity-basis", kind="quantity_basis", outcome="pass", method="model_visual", target_refs=("component:two-sides.quantity",), source_refs=("visual:region-a",), summary="Dos grupos separados."),
        GeneralModelVisualCheck(id="duplicate-scan", kind="duplicate_scan", outcome="pass", method="model_visual", target_refs=("component:two-sides.quantity",), source_refs=("visual:region-a",), summary="No son proyecciones duplicadas."),
    )
    args = GeneralAutoReviewArgs(
        scenario_id="scenario-two-sides",
        operations=(GeneralReviewOperation(kind="replace", source_component_ids=(source.id,), result_component_ids=(component.id,), reason="Escenario visual."),),
        components=(component,), checks=checks,
        field_reviews=(GeneralMachineFieldReview(target_ref="component:two-sides.quantity", status="accepted", check_ids=("quantity-basis", "duplicate-scan")),),
        unresolved=("dimensions",), status="incomplete",
    )

    occurrences = _scenario_occurrences(args, checks)

    assert [item.occurrence_index for item in occurrences] == [1, 2]
    assert all(item.state == "provisional" for item in occurrences)


def test_machine_provenance_can_record_bounded_three_phase_flow_with_repairs() -> None:
    provenance = GeneralMachineProvenance(
        model="reviewer-model", policy_version="general-auto-review-v2",
        response_ids=("invalid", "critic-p1", "repair-p2", "critic-p2", "final"),
        review_relation="separate_model",
    )

    assert len(provenance.response_ids) == 5


def test_critic_receives_projection_candidates_without_treating_them_as_facts() -> None:
    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    proposal = _proposal()
    outcome = GeneralFurnitureAgentOutcome(
        proposal, materialize_general_proposal(extraction, proposal), 1, 1, ()
    )

    items = _review_input(_context(extraction), outcome)
    payload = json.loads(items[0]["content"][0]["text"])

    assert "regions" in payload["compact_geometry"]
    assert "projection_hypotheses" in payload["compact_geometry"]
    assert payload["projection_authority"] == "ambiguous_hypotheses_not_physical_identity_or_quantity"
    assert "raster_authority" not in payload
    assert "allowed_document_refs" not in payload


def test_critic_receives_exact_detail_for_segment_binding_omitted_from_initial_spans() -> None:
    from backend.app.contratos.modelos import (
        GeneralBinding, GeneralComponentProposal, GeneralFurnitureProposal,
        GeneralPremise, GeneralQuantity,
    )
    from backend.tests.test_general_furniture_measurements import _extraction as geometry_extraction

    extraction = geometry_extraction()
    proposal = GeneralFurnitureProposal(
        id="segment-proposal", drawing_id=extraction.drawing_id, ledger_revision="ledger-1",
        proposal_origin="native_tool",
        bindings=(GeneralBinding(id="edge", operation="copy", operand_refs=("measurement:contour:contour-panel:segment-001",)),),
        components=(GeneralComponentProposal(
            id="panel", label="Panel", kind="panel", role="unknown",
            length_binding_id="edge", width_binding_id=None, thickness_binding_id=None,
            quantity=GeneralQuantity(value=None, state="unknown"), premise_ids=("p",),
            source_view_ids=("view-front",), source_observation_ids=("observation-front",),
            source_contour_ids=("contour-panel",), source_evidence_ids=("evidence-panel",),
            assumptions=("Asignación de arista provisional.",), unknown_fields=("width", "thickness", "quantity"),
        ),),
        premises=(GeneralPremise(id="p", description="El contorno puede representar un panel."),),
        assumptions=("Escenario.",),
    )
    outcome = GeneralFurnitureAgentOutcome(
        proposal, materialize_general_proposal(extraction, proposal), 1, 1, ()
    )
    context = GeneralFurnitureContext(run_id="run-segment", extraction=extraction, ledger_revision="ledger-1")

    payload = json.loads(_review_input(context, outcome)[0]["content"][0]["text"])

    detail = payload["referenced_segment_measurements"][0]
    assert detail["binding_ref"] == "measurement:contour:contour-panel:segment-001"
    assert detail["value_mm"] == 100
    assert detail["semantic"] == "contour_segment_length"
    assert "component:panel.length" in payload["allowed_target_refs"]
    assert payload["required_dimension_field_review_targets"] == [
        "component:panel.length"
    ]


def test_raster_document_references_are_closed_and_shared_by_critic_and_repair() -> None:
    from backend.app.contratos.modelos import DrawingExtraction

    extraction = DrawingExtraction(
        drawing_id="raster-drawing", status="needs_review",
        source_unit="unknown", unit_scale_to_mm=None, coordinate_unit="source",
        entities=(), views=(), contours=(), dimensions=(), evidence=(), observations=(),
    )
    page = GeneralVisualPage(
        reference="pdf-sha:pdf-page:0001", media_type="image/png",
        sha256="b" * 64, content=b"png",
        source_document_refs=("document:pdf-child",),
    )
    context = GeneralFurnitureContext(
        run_id="run-raster", extraction=extraction,
        ledger_revision="ledger-raster", visual_pages=(page,),
    )
    raw = {
        "bindings": [],
        "components": [{
            "id": "visual-panel", "label": "Panel visual", "kind": "panel",
            "role": "unknown", "length_binding_id": None,
            "width_binding_id": None, "thickness_binding_id": None,
            "quantity": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
            "premise_ids": ["p"], "source_view_ids": [],
            "source_observation_ids": [], "source_contour_ids": [],
            "source_evidence_ids": [], "source_dimension_ids": [],
            "source_document_refs": ["document:pdf-child"],
            "assumptions": ["Escenario visual sin escala."],
            "unknown_fields": ["length", "width", "thickness", "quantity"],
        }],
        "premises": [{"id": "p", "description": "Hipótesis visual.", "required": True, "blocking": True}],
        "assumptions": ["No se miden píxeles."],
    }

    repaired = _materialize_repair(context, raw)
    payload = json.loads(_review_input(context, repaired)[0]["content"][0]["text"])

    assert repaired.draft.components[0].source_document_refs == ("document:pdf-child",)
    assert "pdf-sha:pdf-page:0001" in payload["allowed_source_refs"]
    assert "document:pdf-child" in payload["allowed_source_refs"]
    assert "pdf-sha:pdf-page:0001" in payload["allowed_document_refs"]
    assert "document:pdf-child" in payload["allowed_document_refs"]
    assert payload["raster_authority"]["allowed_source_view_ids"] == []


def test_autonomous_reviewer_keeps_deduced_authority_and_records_machine_proof() -> None:
    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    proposal = _proposal()
    draft = materialize_general_proposal(extraction, proposal)
    source = draft.components[0]

    class Provider:
        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            arguments = {
                "scenario_id": "scenario-auto-1",
                "checks": [{"id": "visual-length", "kind": "visual_consistency", "outcome": "pass", "method": "model_visual", "target_refs": [f"component:{source.id}.length"], "source_refs": ["visual:page-1"], "summary": "La vista es coherente con la asignación propuesta."}],
                "field_reviews": [{"target_ref": f"component:{source.id}.length", "status": "accepted", "check_ids": ["visual-length"]}],
                "unresolved": ["quantity", "thickness"], "status": "incomplete",
            }
            return ProviderResponse(id="review-response-1", model="reviewer-model", tool_calls=(ToolCall(call_id="review-call-1", name="entregar_revision_autonoma", arguments_json=json.dumps(arguments)),))

    context = GeneralFurnitureContext(run_id="run-1", extraction=extraction, ledger_revision="ledger-1", visual_pages=(GeneralVisualPage(reference="page-1", media_type="image/png", sha256="a" * 64, content=b"png"),))
    proposal_outcome = GeneralFurnitureAgentOutcome(proposal=proposal, draft=draft, model_calls=1, tool_calls=1, trace=())
    outcome = run_general_autonomous(context, proposal_outcome, reviewer_provider=Provider(), proposer_model="proposer-model")

    assert outcome.review.reviewer_kind == "machine"
    assert outcome.review.components[0].length.state == "deduced"
    assert outcome.review.machine_provenance.review_relation == "separate_model"
    assert outcome.status == "incomplete"


def test_machine_reviewer_cannot_forge_human_confirmation() -> None:
    from backend.app.contratos.modelos import GeneralAutoReviewArgs, GeneralComponentReview, GeneralQuantity, GeneralReviewOperation, GeneralTextValue

    forged = GeneralComponentReview(
        id="forged", label="Forjado", kind="panel", role="unknown",
        length=GeneralValue(value_mm=999, state="confirmed", dependency_refs=("human:fake",)),
        width=GeneralValue(value_mm=None, state="unknown"), thickness=GeneralValue(value_mm=None, state="unknown"),
        quantity=GeneralQuantity(value=None, state="unknown"),
        material=GeneralTextValue(value=None, state="unknown"), finish=GeneralTextValue(value=None, state="unknown"),
        replaces_component_ids=("component-1",), assumptions=("Ataque",), unknown_fields=(),
    )
    args = GeneralAutoReviewArgs(
        scenario_id="scenario-forged",
        operations=(GeneralReviewOperation(kind="replace", source_component_ids=("component-1",), result_component_ids=("forged",), reason="Forjado"),),
        components=(forged,), checks=(), field_reviews=(), unresolved=("forged",), status="incomplete",
    )

    with pytest.raises(ValueError, match="machine_review_cannot_confirm_fields"):
        _reject_forged_machine_facts(args)


def test_auto_review_input_schema_rejects_deterministic_check_claims() -> None:
    from backend.app.contratos.modelos import GeneralModelVisualCheck

    with pytest.raises(ValidationError, match="visual_consistency"):
        GeneralModelVisualCheck(
            id="forged", kind="dimension_binding", outcome="unknown",
            method="model_visual", target_refs=("component:x.length",),
            source_refs=("visual:x",), summary="Claim no permitido.",
        )


def test_auto_review_input_schema_rejects_colon_before_field_from_real_failure() -> None:
    from backend.app.contratos.modelos import GeneralModelVisualCheck

    with pytest.raises(ValidationError, match="component:.+"):
        GeneralModelVisualCheck(
            id="visual", kind="visual_consistency", outcome="pass",
            method="model_visual",
            target_refs=("component:laterales-candidatos:length",),
            source_refs=("visual:overview",), summary="Coherencia visual.",
        )


def test_visual_check_accepts_raw_contour_only_when_marked_in_visual_context() -> None:
    from backend.app.contratos.modelos import (
        GeneralAutoReviewArgs, GeneralComponentReview, GeneralModelVisualCheck,
        GeneralQuantity, GeneralReviewOperation, GeneralTextValue,
    )
    source = materialize_general_proposal(_extraction(), _proposal()).components[0]
    component = GeneralComponentReview(
        id="panel", label=source.label, kind=source.kind, role=source.role,
        length=source.length, width=source.width, thickness=source.thickness,
        quantity=GeneralQuantity(value=None, state="unknown"),
        material=GeneralTextValue(value=None, state="unknown"), finish=GeneralTextValue(value=None, state="unknown"),
        replaces_component_ids=(source.id,), assumptions=(), unknown_fields=("quantity",),
    )
    args = GeneralAutoReviewArgs(
        scenario_id="s",
        operations=(GeneralReviewOperation(kind="replace", source_component_ids=(source.id,), result_component_ids=(component.id,), reason="Continuidad."),),
        components=(component,),
        checks=(GeneralModelVisualCheck(
            id="marked", kind="visual_consistency", outcome="pass", method="model_visual",
            target_refs=("component:panel.length",), source_refs=("contour-visible",), summary="M001 corresponde al contorno.",
        ),),
        field_reviews=(GeneralMachineFieldReview(target_ref="component:panel.length", status="accepted", check_ids=("marked",)),),
        unresolved=("quantity",), status="incomplete",
    )

    _validate_visual_checks(args, {"contour-visible"}, {"contour-visible"})

    with pytest.raises(ValueError, match="visual_check_reference_outside_context"):
        _validate_visual_checks(args, {"contour-visible"}, {"visual:other"})


def test_partial_machine_coverage_cannot_report_accepted() -> None:
    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    proposal = _proposal()
    draft = materialize_general_proposal(extraction, proposal)
    source = draft.components[0]

    class Provider:
        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            arguments = {
                "scenario_id": "scenario-partial",
                "checks": [_visual_check("only-length", source.id, "length")],
                "field_reviews": [{"target_ref": f"component:{source.id}.length", "status": "accepted", "check_ids": ["only-length"]}],
                "unresolved": [],
                "status": "accepted",
            }
            return ProviderResponse(id="partial-response", model="reviewer-model", tool_calls=(ToolCall(call_id="partial-call", name="entregar_revision_autonoma", arguments_json=json.dumps(arguments)),))

    outcome = run_general_autonomous(_context(extraction), GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ()), reviewer_provider=Provider(), proposer_model="proposer-model")

    assert outcome.status == "incomplete"
    assert outcome.review.auto_review_status == "incomplete"


def test_numeric_component_dimension_omission_is_repaired_by_same_critic() -> None:
    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    proposal = _proposal()
    draft = materialize_general_proposal(extraction, proposal)
    source = draft.components[0]
    calls = 0
    feedback = None

    class Provider:
        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            nonlocal calls, feedback
            calls += 1
            if calls == 1:
                arguments = {
                    "scenario_id": "scenario-missing-dimension-decision",
                    "checks": [_visual_check("visual-length", source.id, "length")],
                    "field_reviews": [],
                    "unresolved": ["quantity", "thickness"],
                    "status": "incomplete",
                }
            else:
                feedback = json.loads(input_items[0]["output"])
                arguments = {
                    "scenario_id": "scenario-complete-dimension-decision",
                    "checks": [_visual_check("visual-length", source.id, "length")],
                    "field_reviews": [{
                        "target_ref": f"component:{source.id}.length",
                        "status": "accepted",
                        "check_ids": ["visual-length"],
                    }],
                    "unresolved": ["quantity", "thickness"],
                    "status": "incomplete",
                }
            return ProviderResponse(
                id=f"dimension-coverage-{calls}", model="reviewer-model",
                tool_calls=(ToolCall(
                    call_id=f"dimension-coverage-call-{calls}",
                    name="entregar_revision_autonoma",
                    arguments_json=json.dumps(arguments),
                ),),
            )

    outcome = run_general_autonomous(
        _context(extraction),
        GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ()),
        reviewer_provider=Provider(),
        proposer_model="proposer-model",
    )

    assert calls == 2
    assert outcome.semantic_repairs == 0
    assert feedback is not None
    assert feedback["error"] == "invalid_arguments"
    assert feedback["details"][0]["msg"] == "machine_dimension_field_reviews_required"
    assert feedback["details"][0]["missing_targets"] == [
        f"component:{source.id}.length"
    ]
    assert outcome.derived.bom_rows[0].length.value_mm == 800


def test_accepted_component_dimension_requires_visual_check_for_same_target() -> None:
    from backend.app.contratos.modelos import (
        GeneralAutoReviewArgs, GeneralComponentReview, GeneralModelVisualCheck,
        GeneralQuantity, GeneralReviewOperation, GeneralTextValue,
    )

    source = materialize_general_proposal(_extraction(), _proposal()).components[0]
    component = GeneralComponentReview(
        id="panel", label=source.label, kind=source.kind, role=source.role,
        length=source.length, width=source.width, thickness=source.thickness,
        quantity=GeneralQuantity(value=None, state="unknown"),
        material=GeneralTextValue(value=None, state="unknown"),
        finish=GeneralTextValue(value=None, state="unknown"),
        replaces_component_ids=(source.id,), assumptions=(), unknown_fields=("quantity",),
    )
    args = GeneralAutoReviewArgs(
        scenario_id="scenario-wrong-check-target",
        operations=(GeneralReviewOperation(
            kind="replace", source_component_ids=(source.id,),
            result_component_ids=(component.id,), reason="Continuidad.",
        ),),
        components=(component,),
        checks=(GeneralModelVisualCheck(
            id="visual-quantity", kind="visual_consistency", outcome="pass",
            method="model_visual", target_refs=("component:panel.quantity",),
            source_refs=("visual:page-1",), summary="Solo revisa cantidad.",
        ),),
        field_reviews=(GeneralMachineFieldReview(
            target_ref="component:panel.length", status="accepted",
            check_ids=("visual-quantity",),
        ),),
        unresolved=("quantity",), status="incomplete",
    )

    with pytest.raises(ValueError, match="accepted_machine_field_requires_targeted_visual_check"):
        _validate_visual_checks(
            args,
            {"visual:page-1"},
            {"visual:page-1"},
        )


def test_typed_hardware_requires_explicit_visual_classification_decision() -> None:
    from backend.app.contratos.modelos import GeneralFurnitureProposal

    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    raw = _proposal().model_dump(mode="python")
    raw["components"][0]["kind"] = "hardware"
    raw["components"][0]["geometry"] = {
        "shape_kind": "hardware", "source_contour_ids": [],
        "basis_refs": ["premise:p1"],
        "rationale": "Herraje comercial propuesto.",
    }
    proposal = GeneralFurnitureProposal.model_validate(raw)
    draft = materialize_general_proposal(extraction, proposal)
    source = draft.components[0]
    calls = 0
    feedback = None

    class Provider:
        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            nonlocal calls, feedback
            calls += 1
            checks = [_visual_check("visual-length", source.id, "length")]
            field_reviews = [{
                "target_ref": f"component:{source.id}.length",
                "status": "accepted", "check_ids": ["visual-length"],
            }]
            if calls == 2:
                feedback = json.loads(input_items[0]["output"])
                checks.append(_visual_check("visual-kind", source.id, "kind"))
                field_reviews.append({
                    "target_ref": f"component:{source.id}.kind",
                    "status": "accepted", "check_ids": ["visual-kind"],
                })
            arguments = {
                "scenario_id": "scenario-hardware",
                "checks": checks, "field_reviews": field_reviews,
                "unresolved": ["quantity", "width", "thickness"],
                "status": "incomplete",
            }
            return ProviderResponse(
                id=f"hardware-classification-{calls}", model="reviewer-model",
                tool_calls=(ToolCall(
                    call_id=f"hardware-classification-call-{calls}",
                    name="entregar_revision_autonoma",
                    arguments_json=json.dumps(arguments),
                ),),
            )

    outcome = run_general_autonomous(
        _context(extraction),
        GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ()),
        reviewer_provider=Provider(), proposer_model="proposer-model",
    )

    assert calls == 2
    assert feedback is not None
    assert feedback["details"][0]["msg"] == (
        "machine_hardware_classification_field_review_required"
    )
    assert feedback["details"][0]["missing_any_of"] == [[
        f"component:{source.id}.kind",
        f"component:{source.id}.geometry",
    ]]
    accepted = {
        item.target_ref for item in outcome.review.machine_field_reviews
        if item.status == "accepted"
    }
    assert f"component:{source.id}.kind" in accepted


def test_autonomous_critic_can_repair_proposal_with_new_ledger_binding_then_review_it() -> None:
    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    proposal = _proposal()
    draft = materialize_general_proposal(extraction, proposal)
    original = draft.components[0]
    calls = 0
    checkpoints = []

    class Provider:
        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            nonlocal calls
            calls += 1
            if calls == 1:
                arguments = {
                    "scenario_id": "scenario-p1",
                    "checks": [{"id": "wrong-role", "kind": "visual_consistency", "outcome": "fail", "method": "model_visual", "target_refs": [f"component:{original.id}.length"], "source_refs": ["visual:page-1"], "summary": "La cota fue asignada al eje semántico equivocado."}],
                    "field_reviews": [{"target_ref": f"component:{original.id}.length", "status": "rejected", "check_ids": ["wrong-role"]}],
                    "unresolved": ["repairable:length_binding"],
                    "status": "conflict",
                }
                name = "entregar_revision_autonoma"
            elif calls == 2:
                arguments = {
                    "bindings": [{"id": "corrected-width", "operation": "copy", "operand_refs": ["dimension:dim-width"]}],
                    "components": [{
                        "id": "panel-repaired", "label": "Panel reparado", "kind": "panel", "role": "unknown",
                        "length_binding_id": None, "width_binding_id": "corrected-width", "thickness_binding_id": None,
                        "quantity": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
                        "premise_ids": ["p-repair"], "source_view_ids": ["view-front"],
                        "source_observation_ids": ["observation-front"], "source_contour_ids": [],
                        "source_evidence_ids": ["evidence-width"], "source_dimension_ids": ["dim-width"],
                        "source_document_refs": [], "assumptions": ["La cota parece corresponder al ancho."],
                        "unknown_fields": ["length", "thickness", "quantity"],
                    }],
                    "premises": [{"id": "p-repair", "description": "Reasignación semántica del eje.", "required": True, "blocking": True}],
                    "assumptions": ["Reparación provisional, no instrucción industrial."],
                }
                name = "proponer_mueble_general"
            else:
                arguments = {
                    "scenario_id": "scenario-p2",
                    "checks": [_visual_check("width-consistent", "panel-repaired", "width")],
                    "field_reviews": [{"target_ref": "component:panel-repaired.width", "status": "accepted", "check_ids": ["width-consistent"]}],
                    "unresolved": ["length", "thickness", "quantity"], "status": "incomplete",
                }
                name = "entregar_revision_autonoma"
            return ProviderResponse(id=f"response-{calls}", model="reviewer-model", tool_calls=(ToolCall(call_id=f"call-{calls}", name=name, arguments_json=json.dumps(arguments)),))

    outcome = run_general_autonomous(
        _context(extraction), GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ()),
        reviewer_provider=Provider(), proposer_model="proposer-model",
        checkpoint_sink=checkpoints.append,
    )

    assert outcome.semantic_repairs == 1
    assert outcome.original_proposal_outcome.proposal.id == proposal.id
    assert outcome.effective_proposal_outcome.proposal.id != proposal.id
    assert outcome.effective_proposal_outcome.draft.components[0].width.value_mm == 800
    assert outcome.effective_proposal_outcome.draft.components[0].length.value_mm is None
    assert outcome.review.proposal_revision == 2
    assert len(outcome.critic_snapshots) == 2
    assert [item.phase for item in checkpoints] == ["critic", "semantic_repair"]
    assert checkpoints[0].proposal_revision == 1
    assert checkpoints[1].proposal_revision == 2
    assert checkpoints[1].proposal_outcome.proposal.id == outcome.effective_proposal_outcome.proposal.id


def test_autonomous_can_checkpoint_two_semantic_repairs_in_one_bounded_job() -> None:
    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    proposal = _proposal()
    draft = materialize_general_proposal(extraction, proposal)
    calls = 0
    checkpoints = []

    class Provider:
        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            nonlocal calls
            calls += 1
            if calls == 1:
                args = _repairable_decision(proposal.components[0].id, "length", "p1")
                name = "entregar_revision_autonoma"
            elif calls == 2:
                args = _repair_proposal_args("width-v1", "panel-v1")
                name = "proponer_mueble_general"
            elif calls == 3:
                args = _repairable_decision("panel-v1", "width", "p2")
                name = "entregar_revision_autonoma"
            elif calls == 4:
                args = _repair_proposal_args("width-v2", "panel-v2")
                name = "proponer_mueble_general"
            else:
                args = {
                    "scenario_id": "scenario-p3",
                    "checks": [_visual_check("width-final", "panel-v2", "width")],
                    "field_reviews": [{"target_ref": "component:panel-v2.width", "status": "accepted", "check_ids": ["width-final"]}],
                    "unresolved": ["length", "thickness", "quantity"],
                    "status": "incomplete",
                }
                name = "entregar_revision_autonoma"
            return ProviderResponse(
                id=f"two-repair-{calls}", model="reviewer-model",
                tool_calls=(ToolCall(call_id=f"two-call-{calls}", name=name, arguments_json=json.dumps(args)),),
            )

    outcome = run_general_autonomous(
        _context(extraction), GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ()),
        reviewer_provider=Provider(), proposer_model="proposer-model",
        limits=__import__("backend.app.general_furniture.autonomous", fromlist=["AutoReviewLimits"]).AutoReviewLimits(
            max_model_calls=5, max_tool_calls=5, max_semantic_repairs=2,
        ),
        checkpoint_sink=checkpoints.append,
    )

    assert calls == 5
    assert outcome.semantic_repairs == 2
    assert outcome.review.proposal_revision == 3
    assert outcome.effective_proposal_outcome.draft.components[0].width.value_mm == 800
    assert [item.phase for item in checkpoints] == ["critic", "semantic_repair", "critic", "semantic_repair"]
    assert [item.proposal_revision for item in checkpoints] == [1, 2, 2, 3]


def test_repair_preflight_returns_incomplete_review_when_budget_cannot_cover_repair_and_recritic() -> None:
    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    proposal = _proposal()
    draft = materialize_general_proposal(extraction, proposal)
    checkpoints = []

    class Provider:
        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            args = _repairable_decision(proposal.components[0].id, "length", "p1")
            return ProviderResponse(
                id="budget-response", model="reviewer-model",
                tool_calls=(ToolCall(call_id="budget-call", name="entregar_revision_autonoma", arguments_json=json.dumps(args)),),
            )

    outcome = run_general_autonomous(
        _context(extraction), GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ()),
        reviewer_provider=Provider(), proposer_model="proposer-model",
        limits=__import__("backend.app.general_furniture.autonomous", fromlist=["AutoReviewLimits"]).AutoReviewLimits(
            max_model_calls=1, max_tool_calls=1, max_semantic_repairs=2,
        ),
        checkpoint_sink=checkpoints.append,
    )

    assert outcome.semantic_repairs == 0
    assert outcome.status == "conflict"
    assert checkpoints[0].phase == "critic"
    assert outcome.trace[-2]["phase"] == "general_auto_repair_budget"
    assert outcome.trace[-2]["diagnostic"] == "increase_general_review_max_calls_or_resume_from_checkpoint"


def test_derivation_regenerates_once_without_another_provider_call(monkeypatch) -> None:
    import backend.app.general_furniture.autonomous as autonomous_module
    from backend.app.general_furniture.derivations import derive_general_package as real_derive

    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    proposal = _proposal()
    draft = materialize_general_proposal(extraction, proposal)
    provider_calls = 0
    derivation_calls = 0

    class Provider:
        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            nonlocal provider_calls
            provider_calls += 1
            args = {
                "scenario_id": "scenario-final",
                "checks": [_visual_check("visual-length", proposal.components[0].id, "length")],
                "field_reviews": [{
                    "target_ref": f"component:{proposal.components[0].id}.length",
                    "status": "accepted", "check_ids": ["visual-length"],
                }],
                "unresolved": ["quantity", "material", "finish"],
                "status": "incomplete",
            }
            return ProviderResponse(
                id="review-final", model="reviewer-model",
                tool_calls=(ToolCall(call_id="review-final-call", name="entregar_revision_autonoma", arguments_json=json.dumps(args)),),
            )

    def flaky_derive(review):
        nonlocal derivation_calls
        derivation_calls += 1
        if derivation_calls == 1:
            raise ValueError("transient_renderer_failure")
        return real_derive(review)

    monkeypatch.setattr(autonomous_module, "derive_general_package", flaky_derive)
    outcome = run_general_autonomous(
        _context(extraction), GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ()),
        reviewer_provider=Provider(), proposer_model="proposer-model",
    )

    assert provider_calls == 1
    assert derivation_calls == 2
    assert outcome.review.proposal_revision == 1
    assert outcome.derived.proposal_revision == 1
    assert [item["phase"] for item in outcome.trace if item.get("phase", "").startswith("general_auto_derivation")] == [
        "general_auto_derivation", "general_auto_derivation_recovered",
    ]


def test_terminal_derivation_failure_preserves_review_with_incomplete_package(monkeypatch) -> None:
    import backend.app.general_furniture.autonomous as autonomous_module

    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    proposal = _proposal()
    draft = materialize_general_proposal(extraction, proposal)
    provider_calls = 0

    class Provider:
        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            nonlocal provider_calls
            provider_calls += 1
            args = {
                "scenario_id": "scenario-final",
                "checks": [_visual_check("visual-length", proposal.components[0].id, "length")],
                "field_reviews": [{
                    "target_ref": f"component:{proposal.components[0].id}.length",
                    "status": "accepted", "check_ids": ["visual-length"],
                }],
                "unresolved": ["quantity", "material", "finish"], "status": "incomplete",
            }
            return ProviderResponse(
                id="review-final", model="reviewer-model",
                tool_calls=(ToolCall(call_id="review-final-call", name="entregar_revision_autonoma", arguments_json=json.dumps(args)),),
            )

    monkeypatch.setattr(
        autonomous_module, "derive_general_package",
        lambda review: (_ for _ in ()).throw(ValueError("renderer_unavailable")),
    )
    outcome = run_general_autonomous(
        _context(extraction), GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ()),
        reviewer_provider=Provider(), proposer_model="proposer-model",
    )

    assert provider_calls == 1
    assert outcome.review.proposal_revision == 1
    assert outcome.derived.proposal_revision == 1
    assert outcome.derived.status == "incomplete"
    assert outcome.derived.cost_basis.missing_data == ("derivation_failed",)
    assert outcome.trace[-2]["phase"] == "general_auto_derivation_fallback"


def test_autonomous_provider_failure_preserves_prior_safe_critique_trace() -> None:
    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    proposal = _proposal()
    draft = materialize_general_proposal(extraction, proposal)
    original = draft.components[0]

    class ProviderFailure(RuntimeError):
        code = "provider_response_incomplete"

    class Provider:
        calls = 0

        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            self.calls += 1
            if self.calls == 2:
                raise ProviderFailure("secret provider payload")
            arguments = {
                "scenario_id": "scenario-p1",
                "checks": [{
                    "id": "repairable", "kind": "visual_consistency",
                    "outcome": "fail", "method": "model_visual",
                    "target_refs": [f"component:{original.id}.length"],
                    "source_refs": ["visual:page-1"],
                    "summary": "La asignación visual es incoherente.",
                }],
                "field_reviews": [{
                    "target_ref": f"component:{original.id}.length",
                    "status": "rejected", "check_ids": ["repairable"],
                }],
                "unresolved": ["repairable:length_binding"],
                "status": "conflict",
            }
            return ProviderResponse(
                id="critic-response", model="reviewer-model",
                tool_calls=(ToolCall(
                    call_id="critic-call", name="entregar_revision_autonoma",
                    arguments_json=json.dumps(arguments),
                ),),
            )

    with pytest.raises(GeneralAutonomousError) as caught:
        run_general_autonomous(
            _context(extraction), GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ()),
            reviewer_provider=Provider(), proposer_model="proposer-model",
        )

    assert caught.value.code == "provider_response_incomplete"
    assert caught.value.model_calls == 2
    assert caught.value.tool_calls == 1
    assert caught.value.trace[-1]["phase"] == "general_auto_critique"
    assert "secret provider payload" not in json.dumps(caught.value.trace)


def test_semantic_repair_rejects_numeric_binding_outside_ledger() -> None:
    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    proposal = _proposal()
    draft = materialize_general_proposal(extraction, proposal)
    original = draft.components[0]
    calls = 0

    class Provider:
        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            nonlocal calls
            calls += 1
            if calls == 1:
                args = {"scenario_id": "scenario-p1", "checks": [{"id": "bad", "kind": "visual_consistency", "outcome": "fail", "method": "model_visual", "target_refs": [f"component:{original.id}.length"], "source_refs": ["visual:page-1"], "summary": "Binding incorrecto."}], "field_reviews": [{"target_ref": f"component:{original.id}.length", "status": "rejected", "check_ids": ["bad"]}], "unresolved": ["repairable:length_binding"], "status": "conflict"}
                name = "entregar_revision_autonoma"
            else:
                args = {"bindings": [{"id": "fabricated", "operation": "copy", "operand_refs": ["measurement:not-in-ledger"]}], "components": [{"id": "fabricated", "label": "Fabricado", "kind": "panel", "role": "unknown", "length_binding_id": "fabricated", "width_binding_id": None, "thickness_binding_id": None, "quantity": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []}, "premise_ids": ["p"], "source_view_ids": ["view-front"], "source_observation_ids": ["observation-front"], "source_contour_ids": [], "source_evidence_ids": [], "source_dimension_ids": [], "source_document_refs": [], "assumptions": ["Ataque."], "unknown_fields": ["width", "thickness", "quantity"]}], "premises": [{"id": "p", "description": "Intento fabricado.", "required": True, "blocking": True}], "assumptions": ["Ataque."]}
                name = "proponer_mueble_general"
            return ProviderResponse(id=f"bad-response-{calls}", model="reviewer-model", tool_calls=(ToolCall(call_id=f"bad-call-{calls}", name=name, arguments_json=json.dumps(args)),))

    with pytest.raises(RuntimeError, match="general_auto_review_repair_budget_exhausted") as error:
        run_general_autonomous(_context(extraction), GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ()), reviewer_provider=Provider(), proposer_model="proposer-model", limits=__import__("backend.app.general_furniture.autonomous", fromlist=["AutoReviewLimits"]).AutoReviewLimits(max_model_calls=3, max_tool_calls=3, max_validation_repairs=0))

    assert error.value.trace[-1]["ok"] is False
    assert any(
        item["msg"] == "proposal_reference_outside_ledger"
        for item in error.value.trace[-1]["details"]
    )


def _context(extraction):
    return GeneralFurnitureContext(run_id="run-1", extraction=extraction, ledger_revision="ledger-1", visual_pages=(GeneralVisualPage(reference="page-1", media_type="image/png", sha256="a" * 64, content=b"png"),))


def _replace(source_id: str, result_id: str) -> dict:
    return {"kind": "replace", "source_component_ids": [source_id], "result_component_ids": [result_id], "reason": "Revisión multimodal provisional."}


def _visual_check(check_id: str, component_id: str, field: str) -> dict:
    return {"id": check_id, "kind": "visual_consistency", "outcome": "pass", "method": "model_visual", "target_refs": [f"component:{component_id}.{field}"], "source_refs": ["visual:page-1"], "summary": "La imagen es coherente con la asignación provisional."}


def _repairable_decision(component_id: str, field: str, suffix: str) -> dict:
    check_id = f"repair-{suffix}"
    return {
        "scenario_id": f"scenario-{suffix}",
        "checks": [{
            "id": check_id, "kind": "visual_consistency", "outcome": "fail",
            "method": "model_visual", "target_refs": [f"component:{component_id}.{field}"],
            "source_refs": ["visual:page-1"], "summary": "La asignación requiere otra reparación.",
        }],
        "field_reviews": [{
            "target_ref": f"component:{component_id}.{field}",
            "status": "rejected", "check_ids": [check_id],
        }],
        "unresolved": [f"repairable:{field}_binding"],
        "status": "conflict",
    }


def _repair_proposal_args(binding_id: str, component_id: str) -> dict:
    return {
        "bindings": [{"id": binding_id, "operation": "copy", "operand_refs": ["dimension:dim-width"]}],
        "components": [{
            "id": component_id, "label": "Panel reparado", "kind": "panel", "role": "unknown",
            "length_binding_id": None, "width_binding_id": binding_id, "thickness_binding_id": None,
            "quantity": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
            "premise_ids": ["p-repair"], "source_view_ids": ["view-front"],
            "source_observation_ids": ["observation-front"], "source_contour_ids": [],
            "source_evidence_ids": ["evidence-width"], "source_dimension_ids": ["dim-width"],
            "source_document_refs": [], "assumptions": ["Reasignación provisional."],
            "unknown_fields": ["length", "thickness", "quantity"],
        }],
        "premises": [{"id": "p-repair", "description": "Reasignación semántica.", "required": True, "blocking": True}],
        "assumptions": ["Reparación provisional."],
    }


def _review_component(source, *, component_id: str) -> dict:
    return {
        "id": component_id, "label": source.label, "kind": source.kind, "role": source.role,
        "length": source.length.model_dump(mode="json"), "width": source.width.model_dump(mode="json"),
        "thickness": source.thickness.model_dump(mode="json"), "quantity": source.quantity.model_dump(mode="json"),
        "material": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
        "finish": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
        "replaces_component_ids": [source.id], "source_view_ids": list(source.source_view_ids),
        "source_observation_ids": list(source.source_observation_ids), "source_contour_ids": list(source.source_contour_ids),
        "source_evidence_ids": list(source.source_evidence_ids), "source_dimension_ids": list(source.source_dimension_ids),
        "source_document_refs": list(source.source_document_refs), "assumptions": list(source.assumptions),
        "unknown_fields": list(source.unknown_fields),
    }
