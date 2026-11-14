from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.contratos.modelos import GeneralAssemblyAttempt
from backend.app.general_furniture.assembly import validate_assembly
from backend.app.general_furniture.assembly_live import (
    AssemblyAgentContext,
    AssemblyAgentLimits,
    AssemblyLiveError,
    assembly_tool_schemas,
    build_terminal_assembly_attempt,
    run_general_assembly_agent,
)
from backend.tests.test_general_furniture_assembly import (
    _candidate,
    _extraction,
    _review,
)


class _SequenceProvider:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.feedback = []

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.feedback.append(input_items)
        assert all(item["strict"] is True for item in tools)
        return self.responses.pop(0)


def _response(index: int, name: str, arguments: dict) -> ProviderResponse:
    return ProviderResponse(
        id=f"response-{index}", model="test-assembly",
        tool_calls=(ToolCall(
            call_id=f"call-{index}", name=name,
            arguments_json=json.dumps(arguments),
        ),),
    )


def test_assembly_agent_limits_enforce_approved_hard_caps() -> None:
    limits = AssemblyAgentLimits()

    assert limits.max_model_calls == 5
    assert limits.timeout_s == 180
    assert limits.max_instances == 100
    assert limits.max_contours == 512
    with pytest.raises(ValueError, match="assembly_model_call_budget_invalid"):
        AssemblyAgentLimits(max_model_calls=6)
    with pytest.raises(ValueError, match="assembly_instance_budget_invalid"):
        AssemblyAgentLimits(max_instances=101)
    with pytest.raises(ValueError, match="assembly_contour_budget_invalid"):
        AssemblyAgentLimits(max_contours=513)


def test_native_tool_schemas_are_recursively_strict_for_provider() -> None:
    def assert_strict(value) -> None:
        if isinstance(value, dict):
            assert "default" not in value
            if value.get("type") == "object" or "properties" in value:
                properties = value.get("properties", {})
                assert value.get("additionalProperties") is False
                assert set(value.get("required", ())) == set(properties)
            for child in value.values():
                assert_strict(child)
        elif isinstance(value, list):
            for child in value:
                assert_strict(child)

    for tool in assembly_tool_schemas():
        assert tool["strict"] is True
        assert_strict(tool["parameters"])


def test_invalid_tool_arguments_are_fed_back_then_valid_final_is_persisted() -> None:
    extraction, review = _extraction(), _review()
    candidate = _candidate(extraction, review)
    invalid = {"candidate": candidate.model_dump(mode="json"), "extra": True}
    provider = _SequenceProvider([
        _response(1, "entregar_montaje_final", invalid),
        _response(2, "entregar_montaje_final", {"candidate": candidate.model_dump(mode="json")}),
    ])
    persisted = []

    outcome = run_general_assembly_agent(
        AssemblyAgentContext(
            run_id="run", proposal_revision=2, review_revision=3,
            extraction=extraction, review=review,
        ),
        provider=provider,
        evaluator=lambda value: validate_assembly(extraction, review, value),
        attempt_sink=persisted.append,
    )

    assert outcome.attempt.report.status == "accepted"
    assert len(persisted) == 1
    feedback = json.loads(provider.feedback[1][0]["output"])
    assert feedback["error"] == "assembly_tool_arguments_invalid"


def test_exhausted_budget_never_exposes_a_rejected_scene() -> None:
    extraction, review = _extraction(), _review()
    valid = _candidate(extraction, review)
    bad = valid.model_copy(update={
        "placements": (valid.placements[0].model_copy(update={
            "projections": (
                valid.placements[0].projections[0].model_copy(update={"contour_id": "missing"}),
                valid.placements[0].projections[1],
            )
        }),)
    })
    provider = _SequenceProvider([
        _response(index, "entregar_montaje_final", {
            "candidate": bad.model_copy(update={"assembly_revision": index}).model_dump(mode="json")
        })
        for index in range(1, 6)
    ])

    with pytest.raises(AssemblyLiveError, match="model_call_budget_exhausted") as raised:
        run_general_assembly_agent(
            AssemblyAgentContext(
                run_id="run", proposal_revision=2, review_revision=3,
                extraction=extraction, review=review,
            ),
            provider=provider,
            evaluator=lambda value: validate_assembly(extraction, review, value),
        )

    assert len(raised.value.attempts) == 5
    assert all(item.report.status == "rejected" for item in raised.value.attempts)
    assert all(item.report.scene is None for item in raised.value.attempts)


def test_cancellation_after_provider_return_prevents_attempt_persistence() -> None:
    extraction, review = _extraction(), _review()
    candidate = _candidate(extraction, review)
    provider = _SequenceProvider([
        _response(1, "entregar_montaje_final", {
            "candidate": candidate.model_dump(mode="json")
        })
    ])
    checks = iter((False, True))
    persisted = []

    with pytest.raises(AssemblyLiveError, match="assembly_cancelled"):
        run_general_assembly_agent(
            AssemblyAgentContext(
                run_id="run", proposal_revision=2, review_revision=3,
                extraction=extraction, review=review,
            ),
            provider=provider,
            evaluator=lambda value: validate_assembly(extraction, review, value),
            attempt_sink=persisted.append,
            cancelled=lambda: next(checks),
        )

    assert persisted == []


def test_distinct_accepted_alternatives_are_both_persisted_before_final_selection() -> None:
    extraction, review = _extraction(), _review()
    first = _candidate(extraction, review).model_copy(update={
        "candidate_id": "candidate-a", "alternative_id": "alternative-a",
    })
    second = first.model_copy(update={
        "assembly_revision": 2,
        "candidate_id": "candidate-b",
        "alternative_id": "alternative-b",
    })
    provider = _SequenceProvider([
        _response(1, "evaluar_candidato_montaje", {
            "candidate": first.model_dump(mode="json")
        }),
        _response(2, "entregar_montaje_final", {
            "candidate": second.model_dump(mode="json")
        }),
    ])
    persisted = []

    outcome = run_general_assembly_agent(
        AssemblyAgentContext(
            run_id="run", proposal_revision=2, review_revision=3,
            extraction=extraction, review=review,
        ),
        provider=provider,
        evaluator=lambda value: validate_assembly(extraction, review, value),
        attempt_sink=persisted.append,
    )

    assert outcome.attempt.candidate.alternative_id == "alternative-b"
    assert [item.candidate.alternative_id for item in persisted] == [
        "alternative-a", "alternative-b",
    ]
    assert all(item.report.status == "accepted" for item in persisted)
    assert json.loads(provider.feedback[1][0]["output"])[
        "next_expected_assembly_revision"
    ] == 2


def test_provider_return_after_deadline_cannot_persist_accepted_scene() -> None:
    extraction, review = _extraction(), _review()
    candidate = _candidate(extraction, review)
    provider = _SequenceProvider([
        _response(1, "entregar_montaje_final", {
            "candidate": candidate.model_dump(mode="json")
        })
    ])
    times = iter((0.0, 0.0, 0.0, 181.0))
    persisted = []

    with pytest.raises(AssemblyLiveError, match="assembly_timeout"):
        run_general_assembly_agent(
            AssemblyAgentContext(
                run_id="run", proposal_revision=2, review_revision=3,
                extraction=extraction, review=review,
            ),
            provider=provider,
            evaluator=lambda value: validate_assembly(extraction, review, value),
            attempt_sink=persisted.append,
            clock=lambda: next(times),
        )

    assert persisted == []


def test_json_array_inspection_and_retry_revision_use_authoritative_context() -> None:
    extraction, review = _extraction(), _review()
    candidate = _candidate(extraction, review).model_copy(update={
        "assembly_revision": 2,
    })
    provider = _SequenceProvider([
        _response(1, "inspeccionar_contexto_montaje", {
            "measurement_ids": [], "offset": 0, "limit": 2,
        }),
        _response(2, "entregar_montaje_final", {
            "candidate": candidate.model_dump(mode="json")
        }),
    ])

    outcome = run_general_assembly_agent(
        AssemblyAgentContext(
            run_id="run", proposal_revision=2, review_revision=3,
            extraction=extraction, review=review,
        ),
        provider=provider,
        evaluator=lambda value: validate_assembly(extraction, review, value),
        base_assembly_revision=1,
    )

    initial = json.loads(provider.feedback[0][0]["content"][0]["text"])
    assert initial["expected_assembly_revision"] == 2
    assert initial["assembly_context"]["contours"]
    assert initial["assembly_context"]["regions"]
    assert "drawing:drawing" in initial["allowed_candidate_sources"]
    assert outcome.attempt.assembly_revision == 2


def test_visual_pages_are_bounded_public_multimodal_context() -> None:
    extraction, review = _extraction(), _review()
    candidate = _candidate(extraction, review)
    provider = _SequenceProvider([
        _response(1, "entregar_montaje_final", {
            "candidate": candidate.model_dump(mode="json")
        })
    ])
    page = SimpleNamespace(
        reference="page-1", sha256="a" * 64, media_type="image/png",
        content=b"png", source_view_ids=("front",),
        source_contour_ids=("front-1",),
        source_document_refs=("document:public-1",),
    )

    run_general_assembly_agent(
        AssemblyAgentContext(
            run_id="run", proposal_revision=2, review_revision=3,
            extraction=extraction, review=review, visual_pages=(page,),
        ),
        provider=provider,
        evaluator=lambda value: validate_assembly(extraction, review, value),
    )

    content = provider.feedback[0][0]["content"]
    assert [item["type"] for item in content] == ["input_text", "input_image"]
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    payload = json.loads(content[0]["text"])
    assert payload["visual_artifacts"][0]["reference"] == "visual:page-1"


def test_candidate_cannot_fabricate_private_or_cross_run_sources() -> None:
    extraction, review = _extraction(), _review()
    candidate = _candidate(extraction, review).model_copy(update={
        "sources": ("private:holdout",),
    })
    provider = _SequenceProvider([
        _response(1, "entregar_montaje_final", {
            "candidate": candidate.model_dump(mode="json")
        })
        for _ in range(5)
    ])

    with pytest.raises(AssemblyLiveError, match="model_call_budget_exhausted") as raised:
        run_general_assembly_agent(
            AssemblyAgentContext(
                run_id="run", proposal_revision=2, review_revision=3,
                extraction=extraction, review=review,
            ),
            provider=provider,
            evaluator=lambda value: validate_assembly(extraction, review, value),
        )

    assert all(
        item.get("code") == "assembly_candidate_source_not_allowed"
        for item in raised.value.trace
    )


def test_exhaustion_after_rejected_candidate_builds_new_terminal_with_full_trace() -> None:
    extraction, review = _extraction(), _review()
    valid = _candidate(extraction, review)
    bad = valid.model_copy(update={
        "placements": (valid.placements[0].model_copy(update={
            "projections": (
                valid.placements[0].projections[0].model_copy(
                    update={"contour_id": "missing"}
                ),
                valid.placements[0].projections[1],
            )
        }),)
    })
    provider = _SequenceProvider([
        _response(1, "evaluar_candidato_montaje", {
            "candidate": bad.model_dump(mode="json")
        }),
        *(
            _response(index, "herramienta_desconocida", {})
            for index in range(2, 6)
        ),
    ])
    context = AssemblyAgentContext(
        run_id="run", proposal_revision=2, review_revision=3,
        extraction=extraction, review=review,
    )
    persisted = []

    with pytest.raises(AssemblyLiveError, match="model_call_budget_exhausted") as raised:
        run_general_assembly_agent(
            context,
            provider=provider,
            evaluator=lambda value: validate_assembly(extraction, review, value),
            attempt_sink=persisted.append,
        )

    assert len(persisted) == 1
    assert persisted[0].candidate is not None
    assert persisted[0].report.status == "rejected"
    terminal = build_terminal_assembly_attempt(
        context,
        assembly_revision=2,
        attempt_index=2,
        model="test-assembly",
        error=raised.value,
    )
    assert terminal.candidate is not None
    assert terminal.candidate.candidate_id == bad.candidate_id
    assert terminal.report.status == "incomplete"
    assert terminal.report.issues[0].code == "assembly_model_call_budget_exhausted"
    assert len(terminal.trace) == 5
    assert "herramienta_desconocida" in terminal.trace[-1].summary


def test_terminal_preserves_safe_preflight_assembly_error_code() -> None:
    context = AssemblyAgentContext(
        run_id="run", proposal_revision=2, review_revision=3,
        extraction=_extraction(), review=_review(),
    )

    terminal = build_terminal_assembly_attempt(
        context,
        assembly_revision=1,
        attempt_index=1,
        model="test",
        error=ValueError("assembly_metric_scale_required"),
    )

    assert terminal.report.issues[0].code == "assembly_metric_scale_required"
    assert "assembly_metric_scale_required" in terminal.trace[0].summary


def test_terminal_preserves_rejected_deterministic_placements_without_scene() -> None:
    extraction, review = _extraction(), _review()
    candidate = _candidate(extraction, review)
    evaluated = validate_assembly(extraction, review, candidate)
    rejected = GeneralAssemblyAttempt(
        run_id="run", proposal_revision=2, review_revision=3,
        assembly_revision=1, attempt_index=1, candidate=candidate,
        report=evaluated.model_copy(update={"status": "rejected", "scene": None}),
        model="test", policy_version="general-assembly-v1",
        sources=candidate.sources, trace=(),
    )
    error = AssemblyLiveError(
        "assembly_model_call_budget_exhausted",
        attempts=(rejected,),
        trace=({"phase": "assembly_evaluate", "status": "rejected"},),
        model_calls=5,
        tool_calls=5,
    )
    context = AssemblyAgentContext(
        run_id="run", proposal_revision=2, review_revision=3,
        extraction=extraction, review=review,
    )

    terminal = build_terminal_assembly_attempt(
        context, assembly_revision=2, attempt_index=2,
        model="test", error=error,
    )

    assert terminal.report.status == "incomplete"
    assert terminal.report.scene is None
    assert terminal.report.placements == evaluated.placements
    assert terminal.report.global_bounds_mm == evaluated.global_bounds_mm
    assert terminal.report.issues[0].source_refs == ("assembly_revision:1",)


def test_provisional_occurrences_obey_instance_budget_before_provider():
    from backend.app.contratos.modelos import GeneralScenarioOccurrence
    review = _review()
    component = review.components[0]
    provisional = tuple(GeneralScenarioOccurrence(
        id=f"scenario-{index}", component_id=component.id, occurrence_index=index,
        scenario_id="scenario", quantity_target_ref=f"component:{component.id}.quantity",
        check_ids=("quantity", "duplicates"), premise_refs=("premise:quantity",),
        source_refs=("visual:page",),
    ) for index in range(1, 102))
    review = review.model_copy(update={"occurrences": (), "scenario_occurrences": provisional})
    provider = _SequenceProvider([])
    with pytest.raises(AssemblyLiveError, match="assembly_instance_budget_exhausted"):
        run_general_assembly_agent(
            AssemblyAgentContext(run_id="run", proposal_revision=1, review_revision=1,
                                 extraction=_extraction(), review=review),
            provider=provider, evaluator=lambda candidate: None, attempt_sink=lambda attempt: None,
        )
    assert provider.feedback == []
