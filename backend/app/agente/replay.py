"""Verified transcripts for replaying successful live agent executions.

Only request fingerprints and structured provider tool calls are retained. Raw prompts,
images, provider bodies and hidden reasoning are never part of a recording.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from backend.app.agente.provider import MAX_PROVIDER_RESPONSE_BYTES, ProviderResponse, ToolCall
from backend.app.contratos.modelos import ReplaySource


RECORDING_VERSION = 1
MAX_RECORDED_RESPONSES = 15  # Same bound as the supported AgentLimits model-call budget.
MAX_RECORDED_TRANSCRIPT_BYTES = MAX_PROVIDER_RESPONSE_BYTES
DEFAULT_RECORDING_MAX_COUNT = 1000
DEFAULT_RECORDING_MAX_BYTES = 256 * 1024 * 1024


def _canonical_json(value: Any) -> str:
    def ready(item: Any) -> Any:
        if is_dataclass(item):
            return ready(asdict(item))
        if hasattr(item, "model_dump"):
            return ready(item.model_dump(mode="json"))
        if isinstance(item, dict):
            return {key: ready(nested) for key, nested in item.items()}
        if isinstance(item, (list, tuple)):
            return [ready(nested) for nested in item]
        return item

    return json.dumps(ready(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def recording_fingerprint(material: dict[str, Any]) -> str:
    return _sha256({"recording_version": RECORDING_VERSION, **material})


def _request_hash(input_items: Any, tools: Any, previous_response_id: str | None) -> str:
    return _sha256({
        "input_items": input_items,
        "tools": tools,
        "previous_response_id": previous_response_id,
    })


def _call_payload(call: ToolCall) -> dict[str, Any]:
    arguments_json = call.arguments_json
    if arguments_json is None:
        arguments_json = _canonical_json(call.arguments)
    return {
        "call_id": call.call_id,
        "name": call.name,
        "arguments_json": arguments_json,
    }


def _response_payload(response: ProviderResponse) -> dict[str, Any]:
    return {
        "id": response.id,
        "model": response.model,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "total_tokens": response.total_tokens,
        "duration_ms": response.duration_ms,
        "tool_calls": [_call_payload(call) for call in response.tool_calls],
    }


def _provider_response(payload: dict[str, Any]) -> ProviderResponse:
    return ProviderResponse(
        id=payload["id"],
        model=payload.get("model"),
        input_tokens=payload.get("input_tokens"),
        output_tokens=payload.get("output_tokens"),
        total_tokens=payload.get("total_tokens"),
        duration_ms=payload.get("duration_ms"),
        tool_calls=tuple(
            ToolCall(
                call_id=call["call_id"],
                name=call["name"],
                arguments_json=call["arguments_json"],
            )
            for call in payload["tool_calls"]
        ),
    )


@dataclass(frozen=True)
class RecordingDraft:
    transcript_json: str
    transcript_sha256: str
    output_sha256: str
    response_ids: tuple[str, ...]
    provider_model: str
    response_count: int
    transcript_bytes: int


@dataclass(frozen=True)
class StoredRecording:
    recording_id: str
    fingerprint: str
    source_live_run_id: str
    source_result_revision: int
    source_actor: str
    provider_model: str
    response_ids: tuple[str, ...]
    transcript_json: str
    transcript_sha256: str
    output_sha256: str
    recorded_at: str
    response_count: int
    transcript_bytes: int

    def replay_source(self) -> ReplaySource:
        return ReplaySource(
            recording_id=self.recording_id,
            source_live_run_id=self.source_live_run_id,
            source_result_revision=self.source_result_revision,
            source_actor=self.source_actor,
            provider_model=self.provider_model,
            provider_response_ids=self.response_ids,
            transcript_sha256=self.transcript_sha256,
            fingerprint=self.fingerprint,
            recorded_at=self.recorded_at,
        )


class RecordingProvider:
    def __init__(self, inner: Any, *, provider_model: str | None = None) -> None:
        self.inner = inner
        self.provider_model = provider_model
        self._turns: list[dict[str, Any]] = []

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        if len(self._turns) >= MAX_RECORDED_RESPONSES:
            raise RuntimeError("recording_response_limit_exceeded")
        response = self.inner.create_response(
            input_items=input_items,
            tools=tools,
            previous_response_id=previous_response_id,
            timeout_s=timeout_s,
        )
        turn = {
            "request_sha256": _request_hash(input_items, tools, previous_response_id),
            "response": _response_payload(response),
        }
        candidate = _canonical_json([*self._turns, turn])
        if len(candidate.encode("utf-8")) > MAX_RECORDED_TRANSCRIPT_BYTES:
            raise RuntimeError("recording_byte_limit_exceeded")
        self._turns.append(turn)
        return response

    def finalize(self, output: Any) -> RecordingDraft:
        if not self._turns:
            raise RuntimeError("recording_empty")
        transcript_json = _canonical_json(self._turns)
        response_ids = tuple(turn["response"]["id"] for turn in self._turns)
        if len(response_ids) != len(set(response_ids)):
            raise RuntimeError("recording_duplicate_response_id")
        model = self.provider_model or next(
            (turn["response"].get("model") for turn in self._turns if turn["response"].get("model")),
            None,
        )
        if not isinstance(model, str) or not model or len(model) > 128:
            raise RuntimeError("recording_model_missing")
        return RecordingDraft(
            transcript_json=transcript_json,
            transcript_sha256=hashlib.sha256(transcript_json.encode("utf-8")).hexdigest(),
            output_sha256=_sha256(output),
            response_ids=response_ids,
            provider_model=model,
            response_count=len(self._turns),
            transcript_bytes=len(transcript_json.encode("utf-8")),
        )


class ReplayProvider:
    def __init__(self, transcript_json: str, transcript_sha256: str, output_sha256: str) -> None:
        if len(transcript_json.encode("utf-8")) > MAX_RECORDED_TRANSCRIPT_BYTES:
            raise RuntimeError("recording_byte_limit_exceeded")
        if hashlib.sha256(transcript_json.encode("utf-8")).hexdigest() != transcript_sha256:
            raise RuntimeError("recording_transcript_hash_mismatch")
        try:
            turns = json.loads(transcript_json)
        except (TypeError, ValueError):
            raise RuntimeError("recording_invalid_transcript") from None
        if not isinstance(turns, list) or not 1 <= len(turns) <= MAX_RECORDED_RESPONSES:
            raise RuntimeError("recording_response_limit_exceeded")
        self._turns = turns
        self._index = 0
        self._output_sha256 = output_sha256

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        if self._index >= len(self._turns):
            raise RuntimeError("recording_exhausted")
        turn = self._turns[self._index]
        if turn.get("request_sha256") != _request_hash(input_items, tools, previous_response_id):
            raise RuntimeError("recording_request_mismatch")
        self._index += 1
        try:
            return _provider_response(turn["response"])
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("recording_invalid_transcript") from None

    def assert_complete(self, output: Any) -> None:
        if self._index != len(self._turns):
            raise RuntimeError("recording_not_exhausted")
        if _sha256(output) != self._output_sha256:
            raise RuntimeError("recording_output_mismatch")
