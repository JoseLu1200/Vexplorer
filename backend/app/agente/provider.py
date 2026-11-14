from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from backend.app.agente.config import ProviderSettings
from backend.app.agente.prompts import SYSTEM_PROMPT, VISION_SYSTEM_PROMPT


MAX_PROVIDER_RESPONSE_BYTES = 4 * 1024 * 1024
_PROVIDER_RESPONSE_CHUNK_BYTES = 64 * 1024
_MAX_PROVIDER_ERROR_BYTES = 64 * 1024


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any] | None = None
    arguments_json: str | None = None


@dataclass(frozen=True)
class ProviderResponse:
    id: str
    tool_calls: tuple[ToolCall, ...]
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: int | None = None


class ProviderError(RuntimeError):
    """Provider failure with allowlisted operational metadata only."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        provider_code: str | None = None,
        request_id: str | None = None,
        response_id: str | None = None,
        incomplete_reason: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.provider_code = provider_code
        self.request_id = request_id
        self.response_id = response_id
        self.incomplete_reason = incomplete_reason


def _bounded_text(value: Any, *, limit: int = 128) -> str | None:
    if not isinstance(value, str) or not value or len(value) > limit:
        return None
    return value


def _bounded_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000_000:
        return None
    return value


def _bounded_operational_text(value: Any, *, limit: int = 128) -> str | None:
    value = _bounded_text(value, limit=limit)
    if value is None or not all(
        character.isalnum() or character in "._:-" for character in value
    ):
        return None
    return value


def _request_id(headers: httpx.Headers) -> str | None:
    return _bounded_operational_text(
        headers.get("x-request-id") or headers.get("request-id"), limit=256
    )


def _http_error_code(response: httpx.Response, *, deadline: float) -> str | None:
    raw_body = bytearray()
    try:
        for chunk in response.iter_bytes(chunk_size=_PROVIDER_RESPONSE_CHUNK_BYTES):
            if (
                time.monotonic() >= deadline
                or len(raw_body) + len(chunk) > _MAX_PROVIDER_ERROR_BYTES
            ):
                return None
            raw_body.extend(chunk)
        body = json.loads(raw_body)
    except (httpx.HTTPError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    error = body.get("error") if isinstance(body, dict) else None
    return (
        _bounded_operational_text(error.get("code"))
        if isinstance(error, dict)
        else None
    )


class OpenAIResponsesProvider:
    def __init__(self, settings: ProviderSettings, client: httpx.Client | None = None, instructions: str | None = None) -> None:
        if not settings.available:
            raise ValueError(settings.unavailable_reason)
        self.settings = settings
        self.client = client or httpx.Client()
        self.instructions = instructions

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "instructions": self.instructions or (VISION_SYSTEM_PROMPT if self.settings.vision_enabled else SYSTEM_PROMPT),
            "input": input_items,
            "tools": tools,
            "tool_choice": "required",
            "parallel_tool_calls": False,
            "max_output_tokens": self.settings.max_output_tokens,
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        started = time.monotonic()
        deadline = started + timeout_s
        try:
            with self.client.stream(
                "POST",
                f"{self.settings.base_url}/responses",
                headers={"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout_s,
            ) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError:
                    raise ProviderError(
                        "provider_request_failed",
                        status_code=response.status_code,
                        provider_code=_http_error_code(response, deadline=deadline),
                        request_id=_request_id(response.headers),
                    ) from None
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        if int(content_length) > MAX_PROVIDER_RESPONSE_BYTES:
                            raise ProviderError("provider_response_too_large")
                    except ValueError:
                        pass
                raw_body = bytearray()
                for chunk in response.iter_bytes(chunk_size=_PROVIDER_RESPONSE_CHUNK_BYTES):
                    if time.monotonic() >= deadline:
                        raise ProviderError("provider_request_timeout")
                    if len(raw_body) + len(chunk) > MAX_PROVIDER_RESPONSE_BYTES:
                        raise ProviderError("provider_response_too_large")
                    raw_body.extend(chunk)
                if time.monotonic() >= deadline:
                    raise ProviderError("provider_request_timeout")
        except httpx.TimeoutException:
            raise ProviderError("provider_request_timeout") from None
        except ProviderError:
            raise
        except httpx.HTTPError:
            raise ProviderError("provider_request_failed") from None
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        try:
            body = json.loads(raw_body)
            if not isinstance(body, dict):
                raise TypeError("provider response must be an object")
            if body.get("status") in ("failed", "incomplete"):
                incomplete = body.get("incomplete_details")
                raise ProviderError(
                    f"provider_response_{body['status']}",
                    status_code=response.status_code,
                    request_id=_request_id(response.headers),
                    response_id=_bounded_operational_text(body.get("id")),
                    incomplete_reason=(
                        _bounded_operational_text(incomplete.get("reason"))
                        if isinstance(incomplete, dict)
                        else None
                    ),
                )
            response_id = _bounded_text(body.get("id"))
            if response_id is None:
                raise ValueError("invalid response id")
            calls = []
            output = body.get("output", [])
            if not isinstance(output, list):
                raise TypeError("provider output must be a list")
            for item in output:
                if not isinstance(item, dict) or item.get("type") != "function_call":
                    continue
                call_id = _bounded_text(item.get("call_id"), limit=256)
                name = _bounded_text(item.get("name"), limit=128)
                arguments = item.get("arguments")
                if call_id is None or name is None or not isinstance(arguments, str):
                    raise ValueError("invalid function call")
                calls.append(ToolCall(call_id=call_id, name=name, arguments_json=arguments))
            usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
            return ProviderResponse(
                id=response_id,
                tool_calls=tuple(calls),
                model=_bounded_text(body.get("model")),
                input_tokens=_bounded_count(usage.get("input_tokens")),
                output_tokens=_bounded_count(usage.get("output_tokens")),
                total_tokens=_bounded_count(usage.get("total_tokens")),
                duration_ms=duration_ms,
            )
        except ProviderError:
            raise
        except (TypeError, ValueError, KeyError):
            raise ProviderError("provider_invalid_response") from None
