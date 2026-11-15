"""Test-only file relay implementing the Responses provider boundary.

The relay never invokes a model or application tool.  A separate native-Codex
orchestrator reads ``request.json`` and atomically publishes ``response.json``.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.app.agente.provider import (
    MAX_PROVIDER_RESPONSE_BYTES,
    ProviderError,
    ProviderResponse,
    ToolCall,
)


DEFAULT_MAX_REQUEST_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_RELAY_IMAGES = 16
_PNG_DATA_PREFIX = "data:image/png;base64,"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_SAFE_TOOL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]{0,127}\Z")


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise ProviderError("provider_invalid_request") from None


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _declared_tool_names(tools: list[Any]) -> frozenset[str]:
    names: set[str] = set()
    for tool in tools:
        if not isinstance(tool, dict):
            raise ProviderError("provider_invalid_request")
        name = tool.get("name")
        if not isinstance(name, str) or _SAFE_TOOL_NAME.fullmatch(name) is None:
            raise ProviderError("provider_invalid_request")
        if name in names:
            raise ProviderError("provider_invalid_request")
        names.add(name)
    return frozenset(names)


class CodexAgentRelayProvider:
    """Synchronous provider backed only by an auditable local file handshake."""

    def __init__(
        self,
        *,
        relay_dir: Path,
        case_id: str,
        role: str,
        instructions: str,
        model: str,
        poll_interval_s: float = 0.1,
        max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
        max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
    ) -> None:
        for component in (case_id, role):
            if not isinstance(component, str) or _SAFE_COMPONENT.fullmatch(component) is None:
                raise ValueError("unsafe_relay_component")
        if not isinstance(instructions, str) or not instructions:
            raise ValueError("instructions_required")
        if not isinstance(model, str) or _SAFE_ID.fullmatch(model) is None:
            raise ValueError("invalid_model")
        if not math.isfinite(poll_interval_s) or poll_interval_s <= 0:
            raise ValueError("invalid_poll_interval")
        if max_request_bytes <= 0 or max_image_bytes <= 0:
            raise ValueError("invalid_relay_limit")
        self.relay_dir = Path(relay_dir).resolve()
        self.case_id = case_id
        self.role = role
        self.instructions = instructions
        self.model = model
        self.poll_interval_s = poll_interval_s
        self.max_request_bytes = max_request_bytes
        self.max_image_bytes = min(max_image_bytes, max_request_bytes)
        self._call_count = 0
        self._lock = threading.Lock()

    def _rewrite_images(self, input_items: list[Any]) -> tuple[list[Any], list[bytes]]:
        rewritten = copy.deepcopy(input_items)
        images: list[bytes] = []

        def visit(value: Any) -> None:
            if isinstance(value, list):
                for item in value:
                    visit(item)
                return
            if not isinstance(value, dict):
                return
            if value.get("type") == "input_image":
                if "image_path" in value:
                    raise ProviderError("provider_invalid_request")
                image_url = value.get("image_url")
                if not isinstance(image_url, str) or not image_url.startswith(_PNG_DATA_PREFIX):
                    raise ProviderError("provider_invalid_request")
                try:
                    image = base64.b64decode(
                        image_url[len(_PNG_DATA_PREFIX) :], validate=True
                    )
                except (binascii.Error, ValueError):
                    raise ProviderError("provider_invalid_request") from None
                if (
                    not image.startswith(_PNG_SIGNATURE)
                    or len(image) > self.max_image_bytes
                    or len(images) >= MAX_RELAY_IMAGES
                ):
                    raise ProviderError("provider_invalid_request")
                images.append(image)
                value.pop("image_url")
                value["image_path"] = f"images/image-{len(images):04d}.png"
                return
            for child in value.values():
                visit(child)

        visit(rewritten)
        return rewritten, images

    def _next_call(self) -> tuple[int, Path, str]:
        with self._lock:
            self._call_count += 1
            call_index = self._call_count
        call_name = f"call-{call_index:04d}"
        return (
            call_index,
            self.relay_dir / self.case_id / self.role / call_name,
            call_name,
        )

    def _queue_event(self, call_name: str, state: str, value: dict[str, Any]) -> None:
        filename = f"{self.case_id}--{self.role}--{call_name}.{state}.json"
        _atomic_write(self.relay_dir / "queue" / filename, _json_bytes(value))

    def _read_response(
        self, response_path: Path, declared_tools: frozenset[str], duration_ms: int
    ) -> tuple[ProviderResponse, str]:
        try:
            size = response_path.stat().st_size
            if size <= 0 or size > MAX_PROVIDER_RESPONSE_BYTES:
                raise ValueError("invalid response size")
            raw = response_path.read_bytes()
            if len(raw) != size:
                raise ValueError("response changed while reading")
            payload = json.loads(raw)
            if not isinstance(payload, dict) or set(payload) != {"id", "tool_calls"}:
                raise ValueError("invalid response object")
            response_id = payload["id"]
            if not isinstance(response_id, str) or _SAFE_ID.fullmatch(response_id) is None:
                raise ValueError("invalid response id")
            raw_calls = payload["tool_calls"]
            if not isinstance(raw_calls, list) or not raw_calls:
                raise ValueError("tool calls required")
            calls: list[ToolCall] = []
            seen_call_ids: set[str] = set()
            for raw_call in raw_calls:
                if not isinstance(raw_call, dict) or set(raw_call) != {
                    "call_id",
                    "name",
                    "arguments",
                }:
                    raise ValueError("invalid tool call")
                call_id = raw_call["call_id"]
                name = raw_call["name"]
                arguments = raw_call["arguments"]
                if (
                    not isinstance(call_id, str)
                    or _SAFE_ID.fullmatch(call_id) is None
                    or call_id in seen_call_ids
                    or not isinstance(name, str)
                    or _SAFE_TOOL_NAME.fullmatch(name) is None
                    or name not in declared_tools
                    or not isinstance(arguments, dict)
                ):
                    raise ValueError("invalid tool call fields")
                seen_call_ids.add(call_id)
                calls.append(ToolCall(call_id=call_id, name=name, arguments=arguments))
            return (
                ProviderResponse(
                    id=response_id,
                    tool_calls=tuple(calls),
                    model=self.model,
                    duration_ms=duration_ms,
                ),
                hashlib.sha256(raw).hexdigest(),
            )
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            raise ProviderError("provider_invalid_response") from None

    def create_response(
        self, *, input_items, tools, previous_response_id, timeout_s
    ) -> ProviderResponse:
        if (
            not isinstance(input_items, list)
            or not isinstance(tools, list)
            or isinstance(timeout_s, bool)
            or not isinstance(timeout_s, (int, float))
            or not math.isfinite(timeout_s)
            or timeout_s <= 0
            or (
                previous_response_id is not None
                and (
                    not isinstance(previous_response_id, str)
                    or _SAFE_ID.fullmatch(previous_response_id) is None
                )
            )
        ):
            raise ProviderError("provider_invalid_request")
        declared_tools = _declared_tool_names(tools)
        rewritten_items, images = self._rewrite_images(input_items)
        started_monotonic = time.monotonic()
        started_utc = datetime.now(timezone.utc)
        deadline_monotonic = started_monotonic + float(timeout_s)
        deadline_utc = started_utc + timedelta(seconds=float(timeout_s))
        request = {
            "protocol_version": "codex-agent-relay/1",
            "execution_transport": "codex_agent_relay",
            "case_id": self.case_id,
            "role": self.role,
            "instructions": self.instructions,
            "input_items": rewritten_items,
            "tools": tools,
            "previous_response_id": previous_response_id,
            "response_write_contract": {
                "path": "response.json",
                "publish": "atomic_rename",
                "schema": {
                    "id": "bounded operational string",
                    "tool_calls": [
                        {
                            "call_id": "bounded operational string",
                            "name": "one declared tool name",
                            "arguments": "JSON object",
                        }
                    ],
                },
            },
            "instructions_for_responder": (
                "Write only the declared response object to a temporary file in this "
                "call directory, flush and close it, then publish response.json with "
                "an atomic os.replace. Never write response.json incrementally."
            ),
            "created_at": _utc_text(started_utc),
            "deadline": _utc_text(deadline_utc),
        }
        request_bytes = _json_bytes(request)
        total_bytes = len(request_bytes) + sum(len(image) for image in images)
        if total_bytes > self.max_request_bytes:
            raise ProviderError("provider_request_too_large")

        call_index, call_dir, call_name = self._next_call()
        if call_dir.exists():
            raise ProviderError("provider_relay_collision")
        call_dir.mkdir(parents=True)
        for image_index, image in enumerate(images, start=1):
            _atomic_write(
                call_dir / "images" / f"image-{image_index:04d}.png", image
            )
        request_path = call_dir / "request.json"
        response_path = call_dir / "response.json"
        _atomic_write(request_path, request_bytes)
        self._queue_event(
            call_name,
            "ready",
            {
                "protocol_version": "codex-agent-relay/1",
                "execution_transport": "codex_agent_relay",
                "case_id": self.case_id,
                "role": self.role,
                "call_index": call_index,
                "request_path": str(request_path.relative_to(self.relay_dir).as_posix()),
                "deadline": request["deadline"],
                "state": "ready",
            },
        )
        print(
            json.dumps(
                {
                    "event": "codex_relay_request_ready",
                    "case_id": self.case_id,
                    "role": self.role,
                    "call_index": call_index,
                    "request_path": str(request_path),
                    "deadline": request["deadline"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stdout,
            flush=True,
        )

        def record_timeout() -> None:
            self._queue_event(
                call_name,
                "timeout",
                {
                    "case_id": self.case_id,
                    "role": self.role,
                    "call_index": call_index,
                    "state": "timeout",
                    "pending_request_preserved": True,
                },
            )

        while True:
            remaining = deadline_monotonic - time.monotonic()
            if remaining <= 0:
                record_timeout()
                raise ProviderError("provider_request_timeout")
            if response_path.is_file():
                duration_ms = max(0, round((time.monotonic() - started_monotonic) * 1000))
                response, response_sha256 = self._read_response(
                    response_path, declared_tools, duration_ms
                )
                if time.monotonic() >= deadline_monotonic:
                    record_timeout()
                    raise ProviderError("provider_request_timeout")
                self._queue_event(
                    call_name,
                    "completed",
                    {
                        "case_id": self.case_id,
                        "role": self.role,
                        "call_index": call_index,
                        "response_id": response.id,
                        "response_sha256": response_sha256,
                        "state": "completed",
                    },
                )
                return response
            time.sleep(min(self.poll_interval_s, remaining))
