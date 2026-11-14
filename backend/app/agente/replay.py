"""Record real agent runs and replay them as the demo's plan B (CLAUDE.md rule 5).

A recording holds only the provider's responses (tool calls). On replay the same calls go through the normal runner,
so every tool output is recomputed from the current ledger. A recording is keyed by a fingerprint of everything the
model saw (first message, system prompt, tool schemas): if the drawing, the pipeline, the catalog, the prompt or the
tools change, the recording no longer matches and is not used. Nothing here fabricates a recording.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.app.agente.prompts import system_prompt
from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.agente.runner import _initial_context
from backend.app.agente.tools import tool_schemas
from backend.app.contratos.modelos import DecompositionScenario, DrawingExtraction

RECORDING_VERSION = 1
MAX_RECORDED_RESPONSES = 64


def recording_fingerprint(extraction: DrawingExtraction, scenarios: tuple[DecompositionScenario, ...], vision: bool) -> str:
    material = {
        "version": RECORDING_VERSION,
        "initial_context": _initial_context(extraction, scenarios),
        "system_prompt": system_prompt(vision),
        "tools": tool_schemas(vision),
    }
    return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Recording:
    fingerprint: str
    drawing_id: str
    model: str | None
    recorded_at: str
    responses: tuple[ProviderResponse, ...]


def _response_payload(response: ProviderResponse) -> dict:
    return {"id": response.id, "tool_calls": [
        {"call_id": call.call_id, "name": call.name, "arguments_json": call.arguments_json if call.arguments_json is not None else json.dumps(call.arguments, ensure_ascii=False)}
        for call in response.tool_calls
    ]}


class RecordingProvider:
    """Wraps a live provider and keeps the responses it returned."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.responses: list[ProviderResponse] = []

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        response = self.inner.create_response(input_items=input_items, tools=tools, previous_response_id=previous_response_id, timeout_s=timeout_s)
        self.responses.append(response)
        return response


class ReplayProvider:
    """Returns recorded responses in order; running past the end means the replay diverged."""

    def __init__(self, responses: tuple[ProviderResponse, ...]) -> None:
        self.responses = list(responses)

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        if not self.responses:
            raise RuntimeError("recording_exhausted")
        return self.responses.pop(0)


def _file(directory: Path, fingerprint: str) -> Path:
    return directory / f"{fingerprint}.json"


def save_recording(directory: Path, fingerprint: str, drawing_id: str, model: str | None, responses: list[ProviderResponse]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = _file(directory, fingerprint)
    payload = {
        "version": RECORDING_VERSION, "fingerprint": fingerprint, "drawing_id": drawing_id, "model": model,
        "recorded_at": datetime.now(UTC).isoformat(), "responses": [_response_payload(item) for item in responses[:MAX_RECORDED_RESPONSES]],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load_recording(directory: Path, fingerprint: str) -> Recording | None:
    path = _file(directory, fingerprint)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != RECORDING_VERSION or payload.get("fingerprint") != fingerprint:
            return None
        responses = tuple(
            ProviderResponse(id=str(item["id"]), tool_calls=tuple(
                ToolCall(call_id=str(call["call_id"]), name=str(call["name"]), arguments_json=str(call["arguments_json"]))
                for call in item["tool_calls"]
            ))
            for item in payload["responses"][:MAX_RECORDED_RESPONSES]
        )
        return Recording(fingerprint, str(payload["drawing_id"]), payload.get("model"), str(payload["recorded_at"]), responses)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def has_recordings(directory: Path) -> bool:
    return directory.is_dir() and any(load_recording(directory, path.stem) for path in directory.glob("*.json"))
