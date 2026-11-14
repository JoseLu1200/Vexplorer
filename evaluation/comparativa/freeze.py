"""Write-once method outputs and the freeze record that gates private references.

Outputs are written with exclusive creation, hashed, and listed in
``freeze.json``.  A ``FreezeToken`` can only be obtained from ``verify_freeze``
which re-hashes every output; readers of private references demand one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import ComparisonError, ReferenceNotFrozen, canonical_json

FREEZE_FILE = "freeze.json"
OUTPUT_DIR = "outputs"
FREEZE_SCHEMA = "comparativa-freeze-1"
OUTPUT_SCHEMA = "comparativa-output-1"

_SEAL = object()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def output_relative_path(variant: str, case_id: str, repetition: int) -> str:
    return f"{OUTPUT_DIR}/{variant}/{case_id}.rep{repetition}.json"


def write_output(run_dir: Path, output: dict[str, Any]) -> tuple[str, str]:
    """Create one output file (never overwrite).  Returns (relative path, sha256)."""

    if (run_dir / FREEZE_FILE).exists():
        raise ComparisonError("run is already frozen; outputs are immutable")
    relative = output_relative_path(output["variant"], output["case_id"], output["repetition"])
    target = run_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical_json(output)
    with target.open("xb") as handle:
        handle.write(encoded)
    return relative, sha256_bytes(encoded)


def _outputs_digest(entries: list[dict[str, Any]]) -> str:
    return sha256_bytes(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def freeze_run(
    run_dir: Path,
    *,
    entries: list[dict[str, Any]],
    metadata: dict[str, Any],
    frozen_at: str,
) -> dict[str, Any]:
    """Seal the run.  ``entries`` are {variant, case_id, repetition, path, sha256}."""

    ordered = sorted(entries, key=lambda item: (item["variant"], item["case_id"], item["repetition"]))
    record = {
        "schema": FREEZE_SCHEMA,
        "status": "frozen",
        "frozen_at": frozen_at,
        "outputs": ordered,
        "outputs_digest": _outputs_digest(ordered),
        **metadata,
    }
    with (run_dir / FREEZE_FILE).open("xb") as handle:
        handle.write(canonical_json(record))
    return record


@dataclass(frozen=True)
class FreezeToken:
    """Proof that ``run_dir`` was verified as frozen.  Build via ``verify_freeze``."""

    run_dir: Path
    outputs_digest: str
    seal: object = field(default=None, repr=False, compare=False)

    def is_genuine(self) -> bool:
        return self.seal is _SEAL


def verify_freeze(run_dir: Path) -> FreezeToken:
    """Re-hash every output and return a token, or raise ``ReferenceNotFrozen``."""

    run_dir = Path(run_dir)
    freeze_path = run_dir / FREEZE_FILE
    if not freeze_path.is_file() or freeze_path.is_symlink():
        raise ReferenceNotFrozen("no freeze record: outputs are not frozen")
    try:
        record = json.loads(freeze_path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReferenceNotFrozen(f"unreadable freeze record: {exc}") from exc
    if not isinstance(record, dict) or record.get("schema") != FREEZE_SCHEMA or record.get("status") != "frozen":
        raise ReferenceNotFrozen("freeze record is not a frozen comparison run")
    entries = record.get("outputs")
    if not isinstance(entries, list) or not entries:
        raise ReferenceNotFrozen("freeze record lists no outputs")
    if record.get("outputs_digest") != _outputs_digest(entries):
        raise ReferenceNotFrozen("freeze record digest mismatch")
    expected_root = (run_dir.resolve() / OUTPUT_DIR).resolve()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ReferenceNotFrozen("freeze record entry is not a dict")
    if len({entry.get("path") for entry in entries}) != len(entries):
        raise ReferenceNotFrozen("duplicate output paths in freeze record")
    listed: set[str] = set()
    for entry in entries:
        rep = entry.get("repetition")
        if not isinstance(rep, int) or isinstance(rep, bool):
            raise ReferenceNotFrozen("freeze record repetition is not an integer")
        variant = str(entry.get("variant", ""))
        case_id = str(entry.get("case_id", ""))
        relative = entry.get("path")
        if not isinstance(relative, str):
            raise ReferenceNotFrozen("unsafe output path in freeze record")
        p = Path(relative)
        if p.is_absolute() or bool(p.drive) or bool(p.root) or ".." in p.parts:
            raise ReferenceNotFrozen("unsafe output path in freeze record")
        if relative != output_relative_path(variant, case_id, rep):
            raise ReferenceNotFrozen(f"output path mismatch: {relative}")
        if relative in listed:
            raise ReferenceNotFrozen(f"duplicate output path in freeze record: {relative}")
        listed.add(relative)

        cur = run_dir.resolve()
        for part in p.parts:
            cur = cur / part
            if cur.is_symlink():
                raise ReferenceNotFrozen(f"symlink in output path: {cur}")

        path = run_dir / relative
        if path.is_symlink():
            raise ReferenceNotFrozen(f"symlink in output path: {path}")

        try:
            resolved = path.resolve()
        except OSError as exc:
            raise ReferenceNotFrozen(f"cannot resolve output path: {exc}") from exc

        if not resolved.is_relative_to(expected_root):
            raise ReferenceNotFrozen(f"output path outside outputs directory: {relative}")

        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ReferenceNotFrozen(f"frozen output missing: {relative}") from exc
        if sha256_bytes(data) != entry.get("sha256"):
            raise ReferenceNotFrozen(f"frozen output changed after freezing: {relative}")

    outputs_dir = run_dir / OUTPUT_DIR
    if outputs_dir.exists():
        for item in outputs_dir.rglob("*"):
            if item.is_symlink():
                raise ReferenceNotFrozen("symlink detected in outputs directory")
    present = {
        path.relative_to(run_dir).as_posix()
        for path in outputs_dir.rglob("*")
        if path.is_file()
    }
    if present != listed:
        raise ReferenceNotFrozen("output files differ from the freeze record")
    return FreezeToken(run_dir, record["outputs_digest"], _SEAL)


def load_freeze_record(run_dir: Path) -> dict[str, Any]:
    return json.loads((Path(run_dir) / FREEZE_FILE).read_text(encoding="utf-8"))


def load_outputs(run_dir: Path, token: FreezeToken) -> list[dict[str, Any]]:
    """Read frozen outputs; requires a genuine token for the same run."""

    if not isinstance(token, FreezeToken) or not token.is_genuine():
        raise ReferenceNotFrozen("a verified freeze token is required")
    if Path(run_dir).resolve() != Path(token.run_dir).resolve():
        raise ReferenceNotFrozen("token run_dir mismatch")
    record = load_freeze_record(run_dir)
    if record.get("outputs_digest") != token.outputs_digest:
        raise ReferenceNotFrozen("outputs digest mismatch with token")
    outputs = []
    for entry in record.get("outputs", []):
        path = Path(run_dir) / entry["path"]
        raw = path.read_bytes()
        if sha256_bytes(raw) != entry.get("sha256"):
            raise ReferenceNotFrozen(f"frozen output changed or hash mismatch: {entry.get('path')}")
        outputs.append(json.loads(raw.decode("utf-8")))
    return outputs
