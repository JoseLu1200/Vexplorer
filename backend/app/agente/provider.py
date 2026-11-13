from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from backend.app.agente.config import ProviderSettings
from backend.app.agente.prompts import SYSTEM_PROMPT


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ProviderResponse:
    id: str
    tool_calls: tuple[ToolCall, ...]


class OpenAIResponsesProvider:
    def __init__(self, settings: ProviderSettings, client: httpx.Client | None = None) -> None:
        if not settings.available:
            raise ValueError(settings.unavailable_reason)
        self.settings = settings
        self.client = client or httpx.Client()

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "instructions": SYSTEM_PROMPT,
            "input": input_items,
            "tools": tools,
            "tool_choice": "required",
            "parallel_tool_calls": False,
            "max_output_tokens": 1200,
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        response = self.client.post(
            f"{self.settings.base_url}/responses",
            headers={"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout_s,
        )
        response.raise_for_status()
        body = response.json()
        calls = []
        for item in body.get("output", []):
            if item.get("type") != "function_call":
                continue
            calls.append(ToolCall(call_id=item["call_id"], name=item["name"], arguments=json.loads(item["arguments"])))
        return ProviderResponse(id=body["id"], tool_calls=tuple(calls))
