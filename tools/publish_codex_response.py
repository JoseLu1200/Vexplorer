"""Validate and atomically publish one native-Codex relay response."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import NoSuchResource, Unresolvable


MAX_REQUEST_BYTES = 32 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_SAFE_TOOL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]{0,127}\Z")


def _reject_external_schema(uri: str):
    raise NoSuchResource(ref=uri)


_OFFLINE_SCHEMA_REGISTRY = Registry(retrieve=_reject_external_schema)


class PublishError(ValueError):
    """A local candidate cannot be published to the relay."""


def _read_json(path: Path, *, limit: int, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise PublishError(f"{label}_must_be_regular_file")
    size = path.stat().st_size
    if size <= 0 or size > limit:
        raise PublishError(f"{label}_size_invalid")
    raw = path.read_bytes()
    if len(raw) != size:
        raise PublishError(f"{label}_changed_while_reading")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise PublishError(f"{label}_invalid_utf8_json") from None
    if not isinstance(value, dict):
        raise PublishError(f"{label}_must_be_json_object")
    return value, raw


def _declared_tools(request: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_tools = request.get("tools")
    if not isinstance(raw_tools, list) or not raw_tools:
        raise PublishError("request_tools_missing")
    tools: dict[str, dict[str, Any]] = {}
    for index, tool in enumerate(raw_tools):
        if not isinstance(tool, dict):
            raise PublishError(f"request_tools/{index}: must be an object")
        name = tool.get("name")
        parameters = tool.get("parameters")
        if (
            not isinstance(name, str)
            or _SAFE_TOOL_NAME.fullmatch(name) is None
            or not isinstance(parameters, dict)
        ):
            raise PublishError(f"request_tools/{index}: invalid name or parameters")
        if name in tools:
            raise PublishError(f"duplicate_declared_tool:{name}")
        try:
            Draft202012Validator.check_schema(parameters)
        except SchemaError as error:
            raise PublishError(f"invalid_declared_tool_schema:{name}: {error.message}") from None
        tools[name] = parameters
    return tools


def _validate_candidate(
    candidate: dict[str, Any], tools: dict[str, dict[str, Any]]
) -> None:
    if set(candidate) != {"id", "tool_calls"}:
        raise PublishError("candidate_envelope_must_contain_only_id_and_tool_calls")
    response_id = candidate["id"]
    calls = candidate["tool_calls"]
    if not isinstance(response_id, str) or _SAFE_ID.fullmatch(response_id) is None:
        raise PublishError("candidate_response_id_invalid")
    if not isinstance(calls, list) or not calls:
        raise PublishError("candidate_tool_calls_must_be_non_empty_array")
    seen_call_ids: set[str] = set()
    schema_errors: list[str] = []
    for index, call in enumerate(calls):
        prefix = f"tool_calls/{index}"
        if not isinstance(call, dict) or set(call) != {"call_id", "name", "arguments"}:
            raise PublishError(f"{prefix}: must contain only call_id, name and arguments")
        call_id = call["call_id"]
        name = call["name"]
        arguments = call["arguments"]
        if (
            not isinstance(call_id, str)
            or _SAFE_ID.fullmatch(call_id) is None
            or call_id in seen_call_ids
        ):
            raise PublishError(f"{prefix}/call_id: invalid or duplicate")
        seen_call_ids.add(call_id)
        if not isinstance(name, str) or _SAFE_TOOL_NAME.fullmatch(name) is None:
            raise PublishError(f"{prefix}/name: invalid")
        if name not in tools:
            raise PublishError(f"undeclared_tool:{name}")
        if not isinstance(arguments, dict):
            raise PublishError(f"{prefix}/arguments: must be an object")
        validator = Draft202012Validator(
            tools[name],
            format_checker=FormatChecker(),
            registry=_OFFLINE_SCHEMA_REGISTRY,
        )
        try:
            errors = sorted(
                validator.iter_errors(arguments),
                key=lambda item: list(item.absolute_path),
            )
        except Unresolvable as error:
            raise PublishError(
                f"unresolvable_schema_reference:{name}:{error}"
            ) from None
        for error in errors:
            path = "/".join(str(part) for part in error.absolute_path)
            location = f"{prefix}/arguments" + (f"/{path}" if path else "")
            schema_errors.append(f"{location}: {error.message}")
    if schema_errors:
        raise PublishError("candidate_schema_invalid:\n" + "\n".join(schema_errors))


def _publish_no_replace(response: Path, raw: bytes) -> None:
    temporary = response.with_name(
        f".{response.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, response)
        except FileExistsError:
            raise PublishError("response_already_exists") from None
        except OSError as error:
            raise PublishError(f"atomic_publish_failed:{error.__class__.__name__}") from None
    finally:
        if temporary.exists():
            temporary.unlink()


def publish_response(request_path: Path, candidate_path: Path) -> Path:
    request_path = Path(request_path)
    candidate_path = Path(candidate_path)
    if request_path.name != "request.json":
        raise PublishError("request_filename_must_be_request_json")
    response_path = request_path.parent / "response.json"
    if response_path.exists():
        raise PublishError("response_already_exists")
    request, _ = _read_json(
        request_path, limit=MAX_REQUEST_BYTES, label="request"
    )
    candidate, raw_candidate = _read_json(
        candidate_path, limit=MAX_RESPONSE_BYTES, label="candidate"
    )
    tools = _declared_tools(request)
    _validate_candidate(candidate, tools)
    _publish_no_replace(response_path, raw_candidate)
    return response_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        response_path = publish_response(args.request, args.candidate)
    except PublishError as error:
        print(f"publish_codex_response: error: {error}", file=sys.stderr)
        return 2
    payload = response_path.read_bytes()
    print(
        json.dumps(
            {
                "published": str(response_path.resolve()),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
