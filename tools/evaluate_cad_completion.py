"""Evaluate one frozen CAD-completion outcome against a separate control reference."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from evaluation.cad_completion import evaluate_cad_completion


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid_{label}_json") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}_must_be_an_object")
    return value


def _write_atomic(path: Path, value: dict[str, Any]) -> None:
    encoded = (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--outcome", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    reference = args.reference.resolve()
    outcome = args.outcome.resolve()
    output = args.output.resolve()
    if output in {reference, outcome}:
        parser.error("output must differ from both inputs")
    report = evaluate_cad_completion(
        _read_json(reference, "reference"),
        _read_json(outcome, "outcome"),
    )
    _write_atomic(output, report)
    print(json.dumps({"case_id": report["case_id"], "utility_pass": report["utility_pass"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
