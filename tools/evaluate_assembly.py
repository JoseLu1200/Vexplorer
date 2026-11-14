"""Evaluate a frozen assembly scene against an evaluator-only reference."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from evaluation.assembly import AssemblyEvaluationError, evaluate_assembly_files


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tolerance-mm", type=float, default=1.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output.resolve()
    if output in {args.predictions.resolve(), args.references.resolve()}:
        raise SystemExit("assembly evaluation input error: output must differ from both inputs")
    try:
        report = evaluate_assembly_files(
            args.predictions,
            args.references,
            tolerance_mm=args.tolerance_mm,
        )
    except AssemblyEvaluationError as exc:
        raise SystemExit(f"assembly evaluation input error: {exc}") from exc

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
