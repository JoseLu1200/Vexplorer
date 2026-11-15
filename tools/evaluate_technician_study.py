"""CLI for aggregate evaluation of a frozen technician-study collection."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from evaluation.technician_study import StudyInputError, evaluate_study_file


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate a frozen manual/assisted technician-study collection."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output.resolve()
    if output == args.input.resolve():
        raise SystemExit("evaluation input error: output must differ from input")
    try:
        report = evaluate_study_file(args.input)
    except StudyInputError as exc:
        raise SystemExit(f"evaluation input error: {exc}") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
