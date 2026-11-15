from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

from backend.app.agente.provider import ProviderError
from tools.codex_test_bridge import CodexAgentRelayProvider


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "/x8AAusB9Y9Z4x8AAAAASUVORK5CYII="
)


def _provider(tmp_path: Path, **overrides) -> CodexAgentRelayProvider:
    values = {
        "relay_dir": tmp_path,
        "case_id": "dev-case-01",
        "role": "proposer",
        "instructions": "Use only the supplied tool schema.",
        "model": "gpt-6.1-sol",
        "poll_interval_s": 0.005,
    }
    values.update(overrides)
    return CodexAgentRelayProvider(**values)


def _answer_once(tmp_path: Path) -> None:
    request_path = tmp_path / "dev-case-01" / "proposer" / "call-0001" / "request.json"
    deadline = time.monotonic() + 1
    while not request_path.is_file():
        assert time.monotonic() < deadline
        time.sleep(0.002)
    response_path = request_path.with_name("response.json")
    temporary = response_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "id": "codex-response-1",
                "tool_calls": [
                    {
                        "call_id": "call-proposal-1",
                        "name": "proponer_mueble_general",
                        "arguments": {"proposal": "ok"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    temporary.replace(response_path)


def test_relays_request_png_and_returns_real_provider_response(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    responder = threading.Thread(target=_answer_once, args=(tmp_path,))
    responder.start()

    response = provider.create_response(
        input_items=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Inspect the drawing."},
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64," + base64.b64encode(PNG_1X1).decode("ascii"),
                    },
                ],
            }
        ],
        tools=[
            {
                "type": "function",
                "name": "proponer_mueble_general",
                "parameters": {"type": "object"},
            }
        ],
        previous_response_id="previous-1",
        timeout_s=1,
    )
    responder.join(timeout=1)

    call_dir = tmp_path / "dev-case-01" / "proposer" / "call-0001"
    request = json.loads((call_dir / "request.json").read_text(encoding="utf-8"))
    image = request["input_items"][0]["content"][1]
    assert request["instructions"] == "Use only the supplied tool schema."
    assert request["previous_response_id"] == "previous-1"
    assert request["tools"][0]["name"] == "proponer_mueble_general"
    assert request["response_write_contract"]["publish"] == "atomic_rename"
    assert "os.replace" in request["instructions_for_responder"]
    assert image == {"type": "input_image", "image_path": "images/image-0001.png"}
    assert (call_dir / image["image_path"]).read_bytes() == PNG_1X1
    assert (tmp_path / "queue" / "dev-case-01--proposer--call-0001.ready.json").is_file()
    assert response.id == "codex-response-1"
    assert response.model == "gpt-6.1-sol"
    assert response.input_tokens is None
    assert response.output_tokens is None
    assert response.total_tokens is None
    assert response.tool_calls[0].arguments == {"proposal": "ok"}
    completed = json.loads(
        (
            tmp_path
            / "queue"
            / "dev-case-01--proposer--call-0001.completed.json"
        ).read_text(encoding="utf-8")
    )
    assert completed["response_sha256"] == hashlib.sha256(
        (call_dir / "response.json").read_bytes()
    ).hexdigest()


def test_timeout_is_bounded_and_preserves_pending_request(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    started = time.monotonic()

    with pytest.raises(ProviderError, match="provider_request_timeout"):
        provider.create_response(
            input_items=[],
            tools=[],
            previous_response_id=None,
            timeout_s=0.04,
        )

    assert time.monotonic() - started < 0.25
    call_dir = tmp_path / "dev-case-01" / "proposer" / "call-0001"
    assert (call_dir / "request.json").is_file()
    assert not (call_dir / "response.json").exists()


def test_response_validation_finishing_after_deadline_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _provider(tmp_path)
    original_read = provider._read_response

    def delayed_read(*args, **kwargs):
        time.sleep(0.04)
        return original_read(*args, **kwargs)

    monkeypatch.setattr(provider, "_read_response", delayed_read)
    responder = threading.Thread(target=_answer_once, args=(tmp_path,))
    responder.start()

    with pytest.raises(ProviderError, match="provider_request_timeout"):
        provider.create_response(
            input_items=[],
            tools=[
                {
                    "type": "function",
                    "name": "proponer_mueble_general",
                    "parameters": {"type": "object"},
                }
            ],
            previous_response_id=None,
            timeout_s=0.02,
        )
    responder.join(timeout=1)

    call_dir = tmp_path / "dev-case-01" / "proposer" / "call-0001"
    assert (call_dir / "response.json").is_file()
    assert (tmp_path / "queue" / "dev-case-01--proposer--call-0001.timeout.json").is_file()


@pytest.mark.parametrize(
    "image_item",
    [
        {"type": "input_image", "image_path": "../../secret.png"},
        {"type": "input_image", "image_url": "file:///private/secret.png"},
        {"type": "input_image", "image_url": "data:image/jpeg;base64,AA=="},
    ],
)
def test_rejects_non_relay_image_sources(tmp_path: Path, image_item: dict) -> None:
    provider = _provider(tmp_path)

    with pytest.raises(ProviderError, match="provider_invalid_request"):
        provider.create_response(
            input_items=[{"role": "user", "content": [image_item]}],
            tools=[],
            previous_response_id=None,
            timeout_s=1,
        )

    assert not (tmp_path / "dev-case-01").exists()


def test_rejects_input_over_cap_before_writing_files(tmp_path: Path) -> None:
    provider = _provider(tmp_path, max_request_bytes=128)

    with pytest.raises(ProviderError, match="provider_request_too_large"):
        provider.create_response(
            input_items=[{"role": "user", "content": [{"type": "input_text", "text": "x" * 200}]}],
            tools=[],
            previous_response_id=None,
            timeout_s=1,
        )

    assert not (tmp_path / "dev-case-01").exists()


def test_rejects_undeclared_tool_in_human_response(tmp_path: Path) -> None:
    provider = _provider(tmp_path)

    def answer_invalid() -> None:
        request_path = tmp_path / "dev-case-01" / "proposer" / "call-0001" / "request.json"
        while not request_path.is_file():
            time.sleep(0.002)
        request_path.with_name("response.json").write_text(
            json.dumps(
                {
                    "id": "codex-response-1",
                    "tool_calls": [
                        {"call_id": "call-1", "name": "unknown_tool", "arguments": {}}
                    ],
                }
            ),
            encoding="utf-8",
        )

    responder = threading.Thread(target=answer_invalid)
    responder.start()
    with pytest.raises(ProviderError, match="provider_invalid_response"):
        provider.create_response(
            input_items=[],
            tools=[{"type": "function", "name": "allowed_tool", "parameters": {}}],
            previous_response_id=None,
            timeout_s=1,
        )
    responder.join(timeout=1)
