from __future__ import annotations

import json

import pytest

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.contratos.modelos import GeneralAutoReviewArgs, GeneralMachineFieldReview, GeneralModelVisualCheck, GeneralReviewOperation
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
    assert payload["required_evidence_disposition_review_targets"] == list(report.required_disposition_review_targets)
    assert payload["evidence_accounting"]["claims_physical_piece_recall"] is False
    assert payload["evidence_accounting"]["evidence_coverage"] == 1.0
    assert set(report.required_disposition_review_targets) <= set(payload["allowed_target_refs"])
    assert set(report.required_disposition_review_targets) <= set(payload["allowed_source_refs"])
    assert all(item["authority"].endswith("not_semantic_view_or_physical_identity_or_quantity") for item in payload["region_visual_links"])


def test_required_existence_and_disposition_reviews_are_individual_even_with_shared_check() -> None:
    targets = ("component:panel.existence", "evidence_region:evidence-candidate:a", "evidence_region:evidence-candidate:b")
    reviews = tuple(GeneralMachineFieldReview(target_ref=target, status="accepted", check_ids=("shared",)) for target in targets[:-1])

    with pytest.raises(ValueError, match="machine_required_field_reviews_missing") as error:
        autonomous._validate_required_review_coverage(reviews, required_existence_targets=targets[:1], required_disposition_targets=targets[1:])

    assert error.value.targets == (targets[-1],)


def test_duplicate_projection_disposition_needs_identity_or_duplicate_check() -> None:
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
        autonomous._validate_evidence_disposition_checks(weak, {target: "duplicate_projection"})


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
            targets = ["component:panel.length"]
            if self.calls == 2:
                targets.append("component:panel.existence")
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
                }],
                "field_reviews": [
                    {"target_ref": target, "status": "accepted", "check_ids": ["shared-visual"]}
                    for target in targets
                ],
                "unresolved": ["width", "thickness", "quantity"],
                "status": "incomplete",
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
