from __future__ import annotations

import json

import pytest

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.contratos.modelos import GeneralAutoReviewArgs, GeneralAutoReviewDecisionArgs, GeneralMachineFieldReview, GeneralModelVisualCheck, GeneralPieceGeometry, GeneralQuantity, GeneralReviewOperation, GeneralValue
from backend.app.general_furniture import autonomous
from backend.app.general_furniture.evidence_accounting import build_evidence_accounting_report
from backend.app.general_furniture.live import GeneralFurnitureAgentOutcome, GeneralVisualPage
from backend.app.general_furniture.router import GeneralFurnitureContext
from backend.tests.test_general_furniture_evidence_accounting import _vector_case
from backend.tests.test_general_furniture_proposal import _extraction, _proposal


def _context(extraction, regions) -> GeneralFurnitureContext:
    contour_ids = tuple(contour_id for region in regions for contour_id in region.contour_ids)
    return GeneralFurnitureContext(
        run_id="run-accounting-critic", extraction=extraction, ledger_revision="ledger-1",
        visual_pages=(GeneralVisualPage(
            reference="accounting-page", media_type="image/png", sha256="a" * 64, content=b"png",
            source_contour_ids=contour_ids, crop_bounds_source=(0.0, 0.0, 200.0, 10.0),
        ),),
    )


def test_critic_receives_compact_accounting_targets_without_duplicate_full_snapshots() -> None:
    extraction, proposal, draft, regions = _vector_case(assigned_count=10)
    outcome = GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ())

    payload = json.loads(autonomous._review_input(_context(extraction, regions), outcome)[0]["content"][0]["text"])

    report = build_evidence_accounting_report(extraction, proposal, draft)
    assert "proposal" not in payload and "draft" not in payload
    assert payload["schema_version"] == "compact-general-review-context-1"
    assert payload["required_existence_field_review_targets"] == list(report.required_existence_review_targets)
    assert set(payload["required_cut_piece_field_review_targets"]) == {
        f"component:panel.{field}"
        for field in ("kind", "existence", "geometry", "length", "width", "thickness", "quantity")
    }
    assert payload["required_evidence_disposition_review_targets"] == list(report.required_disposition_review_targets)
    assert payload["evidence_accounting"]["claims_physical_piece_recall"] is False
    assert payload["evidence_accounting"]["evidence_coverage"] == 1.0
    authority = payload["review_target_authority"]
    assert authority["allowed_targets"] == "allowed_target_refs_only"
    assert authority["invalid_accounting_regions"] == (
        "diagnostics_not_review_targets_unless_explicitly_allowed"
    )
    assert authority["accepted_quantity_requires"] == [
        "quantity_basis:pass",
        "duplicate_scan:pass",
    ]
    requirements = payload[
        "required_evidence_disposition_review_requirements"
    ]
    assert {item["target_ref"] for item in requirements} == set(
        report.required_disposition_review_targets
    )
    assert {item["disposition_kind"] for item in requirements} == {
        "multi_region_assigned"
    }
    assert all(item["check_kind_rule"] == "any_of" for item in requirements)
    assert all(item["required_pass_check_kinds"] == [
        "duplicate_scan", "cross_view_identity",
    ] for item in requirements)
    assert set(report.required_disposition_review_targets) <= set(payload["allowed_target_refs"])
    assert set(report.required_disposition_review_targets) <= set(payload["allowed_source_refs"])
    assert all(item["authority"].endswith("not_semantic_view_or_physical_identity_or_quantity") for item in payload["region_visual_links"])


def test_required_existence_and_disposition_reviews_are_individual_even_with_shared_check() -> None:
    targets = ("component:panel.existence", "evidence_region:evidence-candidate:a", "evidence_region:evidence-candidate:b")
    reviews = tuple(GeneralMachineFieldReview(target_ref=target, status="accepted", check_ids=("shared",)) for target in targets[:-1])

    with pytest.raises(ValueError, match="machine_required_field_reviews_missing") as error:
        autonomous._validate_required_review_coverage(reviews, required_existence_targets=targets[:1], required_disposition_targets=targets[1:])

    assert error.value.targets == (targets[-1],)


@pytest.mark.parametrize("disposition_kind", ["duplicate_projection", "multi_region_assigned"])
def test_duplicate_projection_disposition_needs_identity_or_duplicate_check(disposition_kind) -> None:
    target = "evidence_region:evidence-candidate:duplicate"
    weak = GeneralAutoReviewArgs(
        scenario_id="base",
        operations=(GeneralReviewOperation(kind="replace", source_component_ids=("panel",), result_component_ids=("panel",), reason="Continuidad."),),
        components=(),
        checks=(GeneralModelVisualCheck(id="weak", kind="visual_consistency", outcome="pass", target_refs=(target,), source_refs=("visual:accounting-page",), summary="Coincidencia visual genérica."),),
        field_reviews=(GeneralMachineFieldReview(target_ref=target, status="accepted", check_ids=("weak",)),),
        unresolved=(), status="accepted",
    )

    with pytest.raises(ValueError, match="duplicate_projection_requires_directed_duplicate_check"):
        autonomous._validate_evidence_disposition_checks(weak, {target: disposition_kind})


def test_shared_projection_support_requires_both_directed_checks_on_exact_target() -> None:
    target = "evidence_region:evidence-candidate:shared-side"
    wrong_target = "evidence_region:evidence-candidate:other"
    args = GeneralAutoReviewArgs(
        scenario_id="base",
        operations=(GeneralReviewOperation(
            kind="replace", source_component_ids=("panel",),
            result_component_ids=("panel",), reason="Continuidad.",
        ),),
        components=(),
        checks=(
            GeneralModelVisualCheck(
                id="duplicate", kind="duplicate_scan", outcome="pass",
                target_refs=(target,), source_refs=("visual:accounting-page",),
                summary="No se contó el apoyo compartido como otra pieza.",
            ),
            GeneralModelVisualCheck(
                id="shared-wrong-target", kind="shared_projection_support",
                outcome="pass", target_refs=(wrong_target,),
                source_refs=("visual:accounting-page",),
                summary="Contraste dirigido a otra región.",
            ),
        ),
        field_reviews=(GeneralMachineFieldReview(
            target_ref=target, status="accepted",
            check_ids=("duplicate", "shared-wrong-target"),
        ),),
        unresolved=("fixture incomplete",), status="incomplete",
    )

    with pytest.raises(ValueError) as caught:
        autonomous._validate_evidence_disposition_checks(
            args, {target: "shared_projection_support"},
        )

    details = autonomous._safe_autonomous_validation_details(caught.value)
    assert details[0]["expected_kinds"] == [
        "duplicate_scan", "shared_projection_support",
    ]
    assert details[0]["check_kind_rule"] == "all_of"
    assert details[0]["requires_exact_target"] is True


def test_shared_projection_support_accepts_both_directed_checks_on_exact_target() -> None:
    target = "evidence_region:evidence-candidate:shared-side"
    args = GeneralAutoReviewArgs(
        scenario_id="base",
        operations=(GeneralReviewOperation(
            kind="replace", source_component_ids=("panel",),
            result_component_ids=("panel",), reason="Continuidad.",
        ),),
        components=(),
        checks=tuple(
            GeneralModelVisualCheck(
                id=kind, kind=kind, outcome="pass", target_refs=(target,),
                source_refs=("visual:accounting-page",), summary="Contraste dirigido.",
            )
            for kind in ("duplicate_scan", "shared_projection_support")
        ),
        field_reviews=(GeneralMachineFieldReview(
            target_ref=target, status="accepted",
            check_ids=("duplicate_scan", "shared_projection_support"),
        ),),
        unresolved=(), status="accepted",
    )

    autonomous._validate_evidence_disposition_checks(
        args, {target: "shared_projection_support"},
    )


def test_shared_projection_support_context_announces_all_of_requirement() -> None:
    extraction, proposal, draft, _ = _vector_case(assigned_count=2)
    accounting = build_evidence_accounting_report(extraction, proposal, draft)
    first = proposal.evidence_dispositions[0].model_copy(update={
        "kind": "shared_projection_support",
        "component_id": None,
        "support_component_ids": ("panel", "panel-second"),
    })
    proposal = proposal.model_copy(update={
        "evidence_dispositions": (first, *proposal.evidence_dispositions[1:]),
    })

    requirements = autonomous._disposition_review_requirements(
        proposal, accounting,
    )
    shared = next(
        item for item in requirements
        if item["target_ref"] == f"evidence_region:{first.candidate_region_id}"
    )

    assert shared["disposition_kind"] == "shared_projection_support"
    assert shared["required_pass_check_kinds"] == [
        "duplicate_scan", "shared_projection_support",
    ]
    assert shared["check_kind_rule"] == "all_of"


def test_directed_disposition_feedback_reports_all_targets_and_requirements() -> None:
    duplicate_target = "evidence_region:evidence-candidate:duplicate"
    multi_region_target = "evidence_region:evidence-candidate:multi"
    weak = GeneralAutoReviewArgs(
        scenario_id="base",
        operations=(GeneralReviewOperation(
            kind="replace", source_component_ids=("panel",),
            result_component_ids=("panel",), reason="Continuidad.",
        ),),
        components=(),
        checks=(GeneralModelVisualCheck(
            id="weak", kind="visual_consistency", outcome="pass",
            target_refs=(duplicate_target, multi_region_target),
            source_refs=("visual:accounting-page",),
            summary="Coincidencia visual genérica.",
        ),),
        field_reviews=(
            GeneralMachineFieldReview(
                target_ref=duplicate_target, status="accepted",
                check_ids=("weak",),
            ),
            GeneralMachineFieldReview(
                target_ref=multi_region_target, status="accepted",
                check_ids=("weak",),
            ),
        ),
        unresolved=("diagnostic fixture",), status="incomplete",
    )

    with pytest.raises(ValueError) as caught:
        autonomous._validate_evidence_disposition_checks(
            weak,
            {
                duplicate_target: "duplicate_projection",
                multi_region_target: "multi_region_assigned",
            },
        )

    details = autonomous._safe_autonomous_validation_details(caught.value)
    assert details == [
        {
            "loc": ["field_reviews", duplicate_target],
            "msg": "duplicate_projection_requires_directed_duplicate_check",
            "type": "value_error",
            "target_ref": duplicate_target,
            "disposition_kind": "duplicate_projection",
            "check_ids": ["weak"],
            "selected_checks": [{
                "id": "weak", "kind": "visual_consistency",
                "outcome": "pass", "targets_exact": True,
            }],
            "expected_kinds": ["duplicate_scan", "cross_view_identity"],
            "check_kind_rule": "any_of",
            "required_outcome": "pass",
            "requires_exact_target": True,
            "truncated": False,
        },
        {
            "loc": ["field_reviews", multi_region_target],
            "msg": "duplicate_projection_requires_directed_duplicate_check",
            "type": "value_error",
            "target_ref": multi_region_target,
            "disposition_kind": "multi_region_assigned",
            "check_ids": ["weak"],
            "selected_checks": [{
                "id": "weak", "kind": "visual_consistency",
                "outcome": "pass", "targets_exact": True,
            }],
            "expected_kinds": ["duplicate_scan", "cross_view_identity"],
            "check_kind_rule": "any_of",
            "required_outcome": "pass",
            "requires_exact_target": True,
            "truncated": False,
        },
    ]


def test_autonomous_validation_feedback_still_sanitizes_arbitrary_value_errors() -> None:
    details = autonomous._safe_autonomous_validation_details(
        ValueError("secret-reviewer-body=" + "x" * 200)
    )

    assert details == [{"loc": [], "msg": "invalid_value", "type": "value_error"}]


def test_complete_accounting_never_promotes_and_unreviewable_accounting_blocks_acceptance() -> None:
    target = "component:panel.existence"
    args = GeneralAutoReviewArgs(
        scenario_id="base",
        operations=(GeneralReviewOperation(kind="replace", source_component_ids=("panel",), result_component_ids=("panel",), reason="Continuidad."),),
        components=(),
        checks=(GeneralModelVisualCheck(id="existence", kind="visual_consistency", outcome="pass", target_refs=(target,), source_refs=("visual:accounting-page",), summary="Existencia coherente solo para este escenario."),),
        field_reviews=(GeneralMachineFieldReview(target_ref=target, status="accepted", check_ids=("existence",)),),
        unresolved=(), status="accepted",
    )

    class Report:
        reviewable = False
        evidence_coverage = 1.0

    assert autonomous._effective_auto_status(args, accounting_report=Report()) == "incomplete"


def test_runtime_rejects_missing_existence_review_then_accepts_exact_shared_check() -> None:
    extraction = _extraction().model_copy(update={"input_kind": "general_furniture"})
    proposal = _proposal()
    from backend.app.general_furniture.proposal import materialize_general_proposal

    draft = materialize_general_proposal(extraction, proposal)

    class Provider:
        calls = 0
        feedback = None

        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            self.calls += 1
            if self.calls == 2:
                self.feedback = json.loads(input_items[0]["output"])
            targets = [
                f"component:panel.{field}"
                for field in ("kind", "geometry", "length", "width", "thickness")
            ]
            if self.calls == 2:
                targets.append("component:panel.existence")
            quantity_target = "component:panel.quantity"
            arguments = {
                "scenario_id": "base",
                "checks": [{
                    "id": "shared-visual",
                    "kind": "visual_consistency",
                    "outcome": "pass",
                    "method": "model_visual",
                    "target_refs": targets,
                    "source_refs": ["visual:accounting-page"],
                    "summary": "Contraste dirigido de los targets exactos.",
                }, {
                    "id": "quantity-basis", "kind": "quantity_basis", "outcome": "pass",
                    "method": "model_visual", "target_refs": [quantity_target],
                    "source_refs": ["visual:accounting-page"], "summary": "Base provisional dirigida.",
                }, {
                    "id": "quantity-duplicates", "kind": "duplicate_scan", "outcome": "pass",
                    "method": "model_visual", "target_refs": [quantity_target],
                    "source_refs": ["visual:accounting-page"], "summary": "Duplicados contrastados.",
                }],
                "field_reviews": [
                    {"target_ref": target, "status": "accepted", "check_ids": ["shared-visual"]}
                    for target in targets
                ] + [{"target_ref": quantity_target, "status": "accepted", "check_ids": ["quantity-basis", "quantity-duplicates"]}],
                "unresolved": [],
                "status": "accepted",
            }
            return ProviderResponse(
                id=f"critic-{self.calls}", model="reviewer",
                tool_calls=(ToolCall(call_id=f"call-{self.calls}", name="entregar_revision_autonoma", arguments_json=json.dumps(arguments)),),
            )

    provider = Provider()
    result = autonomous.run_general_autonomous(
        _context(extraction, ()),
        GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ()),
        reviewer_provider=provider,
        proposer_model="proposer",
    )

    assert provider.calls == 2
    assert provider.feedback["details"][0]["msg"] == "machine_required_field_reviews_missing"
    assert provider.feedback["details"][0]["missing_targets"] == ["component:panel.existence"]
    assert result.status == "incomplete"


def test_runtime_persists_directed_reviews_for_all_multi_region_dispositions() -> None:
    extraction, proposal, draft, regions = _vector_case(assigned_count=10)
    report = build_evidence_accounting_report(extraction, proposal, draft)
    targets = (
        "component:panel.length", "component:panel.width", "component:panel.thickness",
        *report.required_existence_review_targets,
        *report.required_disposition_review_targets,
    )

    class Provider:
        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            arguments = {
                "scenario_id": "base",
                "checks": [{"id": "directed-accounting", "kind": "duplicate_scan", "outcome": "pass", "method": "model_visual", "target_refs": targets, "source_refs": ["visual:accounting-page"], "summary": "Contraste dirigido; no prueba identidad física."}],
                "field_reviews": [{"target_ref": target, "status": "accepted", "check_ids": ["directed-accounting"]} for target in targets],
                "unresolved": ["quantity"], "status": "incomplete",
            }
            return ProviderResponse(id="critic-dispositions", model="reviewer", tool_calls=(ToolCall(call_id="call-dispositions", name="entregar_revision_autonoma", arguments_json=json.dumps(arguments)),))

    result = autonomous.run_general_autonomous(
        _context(extraction, regions), GeneralFurnitureAgentOutcome(proposal, draft, 1, 1, ()),
        reviewer_provider=Provider(), proposer_model="proposer",
    )

    assert result.status == "incomplete"
    assert set(report.required_disposition_review_targets) <= {item.target_ref for item in result.review.machine_field_reviews}
    assert result.review.status == "reviewed_incomplete"


def test_unknown_material_and_finish_do_not_block_geometric_coherence_status() -> None:
    _, _, draft, _ = _vector_case(assigned_count=10)
    component = draft.components[0].model_copy(update={
        "quantity": GeneralQuantity(value=1, state="deduced", dependency_refs=("premise:p1",)),
        "geometry": GeneralPieceGeometry(shape_kind="rectangle", source_contour_ids=(), basis_refs=("premise:p1",), rationale="Rectángulo provisional."),
        "unknown_fields": (),
    })
    draft = draft.model_copy(update={"components": (component,)})
    targets = tuple(f"component:panel.{field}" for field in ("kind", "existence", "geometry", "length", "width", "thickness", "quantity"))
    decision = GeneralAutoReviewDecisionArgs(
        scenario_id="base",
        checks=(GeneralModelVisualCheck(id="coherent", kind="visual_consistency", outcome="pass", target_refs=targets, source_refs=("visual:accounting-page",), summary="Coherencia geométrica provisional."),),
        field_reviews=tuple(GeneralMachineFieldReview(target_ref=target, status="accepted", check_ids=("coherent",)) for target in targets),
        unresolved=(), status="accepted",
    )
    args = autonomous._server_review_args(decision, draft, None)

    assert autonomous._effective_auto_status(args, required_review_targets=targets) == "accepted"

    abstained = decision.model_copy(update={
        "field_reviews": tuple(
            review.model_copy(update={"status": "abstained"})
            if review.target_ref == "component:panel.existence"
            else review
            for review in decision.field_reviews
        ),
        "unresolved": ("component:panel.existence",),
        "status": "incomplete",
    })
    abstained_args = autonomous._server_review_args(abstained, draft, None)
    assert autonomous._effective_auto_status(
        abstained_args, required_review_targets=targets
    ) == "incomplete"


def test_hardware_can_be_coherent_without_invented_catalog_dimensions() -> None:
    _, _, draft, _ = _vector_case(assigned_count=10)
    component = draft.components[0].model_copy(update={
        "kind": "hardware",
        "quantity": GeneralQuantity(value=1, state="deduced", dependency_refs=("premise:p1",)),
        "width": GeneralValue(value_mm=None, state="unknown"),
        "thickness": GeneralValue(value_mm=None, state="unknown"),
        "geometry": GeneralPieceGeometry(shape_kind="hardware", source_contour_ids=(), basis_refs=("premise:p1",), rationale="Herraje provisional."),
        "unknown_fields": ("width", "thickness"),
    })
    draft = draft.model_copy(update={"components": (component,)})
    targets = tuple(f"component:panel.{field}" for field in ("kind", "existence", "quantity"))
    decision = GeneralAutoReviewDecisionArgs(
        scenario_id="base",
        checks=(GeneralModelVisualCheck(id="hardware", kind="visual_consistency", outcome="pass", target_refs=targets, source_refs=("visual:accounting-page",), summary="Clasificación constructiva provisional."),),
        field_reviews=tuple(GeneralMachineFieldReview(target_ref=target, status="accepted", check_ids=("hardware",)) for target in targets),
        unresolved=(), status="accepted",
    )
    args = autonomous._server_review_args(decision, draft, None)

    assert args.components[0].width.state == "unknown"
    assert autonomous._effective_auto_status(args, required_review_targets=targets) == "accepted"
