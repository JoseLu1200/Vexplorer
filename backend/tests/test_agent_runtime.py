from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from backend.app.agente.config import ProviderSettings
from backend.app.agente.provider import MAX_PROVIDER_RESPONSE_BYTES, OpenAIResponsesProvider, ProviderError, ProviderResponse, ToolCall
from backend.app.agente.runner import AgentLimits, run_agent, run_parts_agent, run_table_agent
from backend.app.geometria import extract_drawing
from backend.app.geometria.mounted_table import analyze_mounted_table, catalog_table_programs
from backend.app.geometria.parts import derive_assembly_candidates, extract_separated_parts
from backend.app.servicios.decomposition import derive_decomposition_scenarios


FIXTURES = Path(__file__).resolve().parents[2] / "data" / "planos_demo"


class DelayedProvider:
    def __init__(self, response: ProviderResponse, delay_s: float = 0.03) -> None:
        self.response = response
        self.delay_s = delay_s

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        time.sleep(self.delay_s)
        return self.response


class ChunkStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes], delay_s: float = 0) -> None:
        self.chunks = chunks
        self.delay_s = delay_s

    def __iter__(self):
        for chunk in self.chunks:
            if self.delay_s:
                time.sleep(self.delay_s)
            yield chunk


def _table_program_arguments(program) -> dict:
    return program.model_dump(
        mode="json",
        include={"bindings", "components", "premises", "assumptions", "evidence_ids"},
    )


def test_all_runners_reject_a_provider_result_returned_after_total_deadline() -> None:
    legacy_extraction = extract_drawing(FIXTURES / "estanteria_montada.dxf")
    scenarios = derive_decomposition_scenarios(legacy_extraction)
    parts_extraction = extract_drawing(FIXTURES / "piezas_completo.dxf", input_kind="separated_part_views")
    parts = extract_separated_parts(parts_extraction)
    candidates = derive_assembly_candidates(parts)
    table_extraction = extract_drawing(FIXTURES / "mesa_demo_001.dxf", input_kind="mounted_orthographic_views")
    table_analysis = analyze_mounted_table(table_extraction)
    table_arguments = _table_program_arguments(catalog_table_programs(table_analysis)[0])

    cases = (
        (
            run_agent,
            (legacy_extraction, scenarios),
            ToolCall("late-legacy", "entregar_despiece", {"scenario_id": scenarios[0].id}),
        ),
        (
            run_parts_agent,
            (parts_extraction, parts, candidates),
            ToolCall(
                "late-parts",
                "entregar_candidato_montaje",
                {"candidate_revision": parts.candidate_revision, "assembly_candidate_id": candidates[0].id},
            ),
        ),
        (
            run_table_agent,
            (table_extraction, table_analysis),
            ToolCall("late-table", "proponer_descomposicion", table_arguments),
        ),
    )

    for runner, args, tool_call in cases:
        provider = DelayedProvider(ProviderResponse(id="late-response", tool_calls=(tool_call,)))
        with pytest.raises(TimeoutError, match="agent_deadline_exceeded"):
            runner(*args, provider, AgentLimits(max_model_calls=1, max_tool_calls=1, timeout_s=0.005))


def test_table_runner_does_not_accept_terminal_result_when_tool_processing_finishes_late(monkeypatch) -> None:
    extraction = extract_drawing(FIXTURES / "mesa_demo_001.dxf", input_kind="mounted_orthographic_views")
    analysis = analyze_mounted_table(extraction)
    catalog_program = catalog_table_programs(analysis)[0]
    arguments = _table_program_arguments(catalog_program)
    provider = DelayedProvider(
        ProviderResponse(
            id="fast-response",
            tool_calls=(ToolCall("slow-terminal-tool", "proponer_descomposicion", arguments),),
        ),
        delay_s=0,
    )

    from backend.app.agente import runner as runner_module

    real_validate = runner_module.ProposeTableProgramArgs.model_validate_json

    def slow_validate(cls, value, **kwargs):
        time.sleep(0.03)
        return real_validate(value, **kwargs)

    monkeypatch.setattr(
        runner_module.ProposeTableProgramArgs,
        "model_validate_json",
        classmethod(slow_validate),
    )
    with pytest.raises(TimeoutError, match="agent_deadline_exceeded"):
        run_table_agent(
            extraction,
            analysis,
            provider,
            AgentLimits(max_model_calls=1, max_tool_calls=1, timeout_s=0.005),
        )


def test_provider_exposes_only_bounded_operational_metadata_and_native_timeout() -> None:
    seen_timeout = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_timeout.update(request.extensions["timeout"])
        return httpx.Response(
            200,
            json={
                "id": "response-123",
                "status": "completed",
                "model": "gpt-test-2026-11-14",
                "usage": {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19},
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call-123",
                        "name": "entregar_despiece",
                        "arguments": json.dumps({"scenario_id": "scenario-1"}),
                    }
                ],
                "secret_payload": "must-not-propagate",
            },
        )

    provider = OpenAIResponsesProvider(
        ProviderSettings(api_key="super-secret", model="gpt-test", base_url="https://example.test/v1"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    response = provider.create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=0.25)

    assert response.id == "response-123"
    assert response.model == "gpt-test-2026-11-14"
    assert response.input_tokens == 12
    assert response.output_tokens == 7
    assert response.total_tokens == 19
    assert response.duration_ms is not None and response.duration_ms >= 0
    assert response.tool_calls[0].call_id == "call-123"
    assert all(value <= 0.25 for value in seen_timeout.values())
    assert "secret" not in repr(response).lower()


def test_provider_errors_do_not_echo_credentials_or_remote_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="remote leaked super-secret credential")

    provider = OpenAIResponsesProvider(
        ProviderSettings(api_key="super-secret", model="gpt-test", base_url="https://example.test/v1"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(RuntimeError) as caught:
        provider.create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=0.25)
    assert str(caught.value) == "provider_request_failed"


def test_provider_http_error_exposes_only_safe_bounded_operational_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"x-request-id": "req-safe-123"},
            json={
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": "remote leaked super-secret credential",
                }
            },
        )

    provider = OpenAIResponsesProvider(
        ProviderSettings(api_key="super-secret", model="gpt-test", base_url="https://example.test/v1"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderError) as caught:
        provider.create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=0.25)

    assert str(caught.value) == "provider_request_failed"
    assert caught.value.status_code == 429
    assert caught.value.provider_code == "rate_limit_exceeded"
    assert caught.value.request_id == "req-safe-123"
    assert caught.value.response_id is None
    assert caught.value.incomplete_reason is None
    assert "secret" not in repr(caught.value).lower()
    assert "remote" not in repr(caught.value).lower()


def test_provider_incomplete_error_preserves_safe_response_identity_and_reason() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-request-id": "req-incomplete-456"},
            json={
                "id": "resp-incomplete-789",
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [],
                "private_debug": "must-not-propagate",
            },
        )

    provider = OpenAIResponsesProvider(
        ProviderSettings(api_key="super-secret", model="gpt-test", base_url="https://example.test/v1"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderError) as caught:
        provider.create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=0.25)

    assert str(caught.value) == "provider_response_incomplete"
    assert caught.value.status_code == 200
    assert caught.value.provider_code is None
    assert caught.value.request_id == "req-incomplete-456"
    assert caught.value.response_id == "resp-incomplete-789"
    assert caught.value.incomplete_reason == "max_output_tokens"
    assert "private_debug" not in repr(caught.value)


def test_provider_streams_valid_json_without_content_length() -> None:
    body = json.dumps({"id": "response-streamed", "status": "completed", "output": []}).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=ChunkStream([body[:13], body[13:]]))

    provider = OpenAIResponsesProvider(
        ProviderSettings(api_key="secret", model="gpt-test", base_url="https://example.test/v1"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert provider.create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=1).id == "response-streamed"


@pytest.mark.parametrize("headers", [{}, {"Content-Length": "1"}])
def test_provider_rejects_oversized_stream_even_when_content_length_is_missing_or_false(headers) -> None:
    chunks = [b"{" + b"x" * (MAX_PROVIDER_RESPONSE_BYTES // 2), b"x" * (MAX_PROVIDER_RESPONSE_BYTES // 2 + 1)]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, stream=ChunkStream(chunks))

    provider = OpenAIResponsesProvider(
        ProviderSettings(api_key="secret", model="gpt-test", base_url="https://example.test/v1"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(RuntimeError, match="^provider_response_too_large$"):
        provider.create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=1)


def test_provider_rejects_a_valid_stream_that_finishes_after_total_read_deadline() -> None:
    body = json.dumps({"id": "late-response", "status": "completed", "output": []}).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=ChunkStream([body[:10], body[10:]], delay_s=0.01))

    provider = OpenAIResponsesProvider(
        ProviderSettings(api_key="secret", model="gpt-test", base_url="https://example.test/v1"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(RuntimeError, match="^provider_request_timeout$"):
        provider.create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=0.005)


def test_runner_attaches_provider_provenance_to_each_action_without_raw_payload() -> None:
    extraction = extract_drawing(FIXTURES / "estanteria_montada.dxf")
    scenarios = derive_decomposition_scenarios(extraction)
    response = ProviderResponse(
        id="response-safe",
        model="gpt-test",
        input_tokens=21,
        output_tokens=8,
        total_tokens=29,
        duration_ms=14,
        tool_calls=(
            ToolCall("call-safe", "entregar_despiece", {"scenario_id": scenarios[0].id}),
        ),
    )

    outcome = run_agent(
        extraction,
        scenarios,
        DelayedProvider(response, delay_s=0),
        AgentLimits(max_model_calls=1, max_tool_calls=1, timeout_s=1),
    )

    action = outcome.actions[0]
    assert action.provider_response_id == "response-safe"
    assert action.provider_model == "gpt-test"
    assert action.provider_call_id == "call-safe"
    assert action.provider_duration_ms == 14
    assert (action.provider_input_tokens, action.provider_output_tokens, action.provider_total_tokens) == (21, 8, 29)
    assert "arguments" not in action.__dict__
    assert "raw" not in action.__dict__




def test_provider_classifies_incomplete_reason_without_echoing_remote_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "response-incomplete",
                "status": "incomplete",
                "incomplete_details": {
                    "reason": "max_output_tokens",
                    "unsafe_remote_detail": "do-not-propagate",
                },
                "usage": {
                    "input_tokens": 4653,
                    "output_tokens": 16384,
                    "output_tokens_details": {"reasoning_tokens": 16384},
                    "total_tokens": 21037,
                },
                "output": [],
            },
        )

    provider = OpenAIResponsesProvider(
        ProviderSettings(api_key="super-secret", model="gpt-6.1-sol", base_url="https://example.test/v1"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderError) as caught:
        provider.create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=1)

    assert str(caught.value) == "provider_response_incomplete"
    assert caught.value.response_id == "response-incomplete"
    assert caught.value.incomplete_reason == "max_output_tokens"
    assert "unsafe" not in repr(caught.value)
