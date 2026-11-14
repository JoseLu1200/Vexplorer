from __future__ import annotations

import json

import pytest

from backend.app.agente.provider import ProviderResponse, ToolCall


class _LiveProvider:
    def __init__(self) -> None:
        self.calls = 0

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.calls += 1
        return ProviderResponse(
            id="response-live-1",
            model="model-test",
            input_tokens=12,
            output_tokens=4,
            total_tokens=16,
            duration_ms=8,
            tool_calls=(ToolCall(call_id="call-1", name="entregar_despiece", arguments={"scenario_id": "scenario-1"}),),
        )


def test_recording_persists_only_bounded_transcript_hashes_and_safe_responses() -> None:
    from backend.app.agente.replay import RecordingProvider

    live = _LiveProvider()
    recorder = RecordingProvider(live)
    request = [{"role": "user", "content": [
        {"type": "input_text", "text": "ledger"},
        {"type": "input_image", "image_url": "data:image/png;base64,TOPSECRETBASE64"},
    ]}]
    tools = [{"type": "function", "name": "entregar_despiece"}]
    response = recorder.create_response(
        input_items=request, tools=tools, previous_response_id=None, timeout_s=3,
    )
    draft = recorder.finalize({"selected_scenario_id": "scenario-1"})

    assert response.id == "response-live-1" and live.calls == 1
    assert draft.response_ids == ("response-live-1",)
    assert draft.provider_model == "model-test"
    assert draft.response_count == 1
    assert draft.transcript_bytes == len(draft.transcript_json.encode("utf-8"))
    assert "TOPSECRETBASE64" not in draft.transcript_json
    assert "image_url" not in draft.transcript_json
    payload = json.loads(draft.transcript_json)
    assert payload[0]["request_sha256"]
    assert payload[0]["response"]["tool_calls"][0]["name"] == "entregar_despiece"
    assert payload[0]["response"]["model"] == "model-test"


def test_replay_rejects_recalculated_request_or_final_output_mismatch() -> None:
    from backend.app.agente.replay import RecordingProvider, ReplayProvider

    request = [{"role": "user", "content": "ledger-v1"}]
    tools = [{"type": "function", "name": "entregar_despiece"}]
    recorder = RecordingProvider(_LiveProvider())
    recorder.create_response(input_items=request, tools=tools, previous_response_id=None, timeout_s=3)
    draft = recorder.finalize({"selected_scenario_id": "scenario-1"})

    replay = ReplayProvider(draft.transcript_json, draft.transcript_sha256, draft.output_sha256)
    replay.create_response(input_items=request, tools=tools, previous_response_id=None, timeout_s=3)
    replay.assert_complete({"selected_scenario_id": "scenario-1"})

    tampered_request = ReplayProvider(draft.transcript_json, draft.transcript_sha256, draft.output_sha256)
    with pytest.raises(RuntimeError, match="recording_request_mismatch"):
        tampered_request.create_response(
            input_items=[{"role": "user", "content": "ledger-v2"}],
            tools=tools,
            previous_response_id=None,
            timeout_s=3,
        )

    tampered_output = ReplayProvider(draft.transcript_json, draft.transcript_sha256, draft.output_sha256)
    tampered_output.create_response(input_items=request, tools=tools, previous_response_id=None, timeout_s=3)
    with pytest.raises(RuntimeError, match="recording_output_mismatch"):
        tampered_output.assert_complete({"selected_scenario_id": "scenario-2"})


def test_replay_rejects_tampered_record_before_use() -> None:
    from backend.app.agente.replay import RecordingProvider, ReplayProvider

    recorder = RecordingProvider(_LiveProvider())
    recorder.create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=3)
    draft = recorder.finalize({"selected_scenario_id": "scenario-1"})
    tampered = draft.transcript_json.replace("response-live-1", "response-live-x")
    with pytest.raises(RuntimeError, match="recording_transcript_hash_mismatch"):
        ReplayProvider(tampered, draft.transcript_sha256, draft.output_sha256)
