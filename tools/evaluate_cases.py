"""CLI for the evaluator-only aggregate report."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from evaluation.metrics import EvaluationInputError, evaluate_files


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate frozen outputs against a private reference offline."
    )
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--references", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tolerance-mm", type=float, default=1.0)
    parser.add_argument("--retrieval-k", type=int, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output.resolve()
    if output in {args.predictions.resolve(), args.references.resolve()}:
        raise SystemExit("evaluation input error: output must differ from both inputs")
    try:
        report = evaluate_files(
            args.predictions,
            args.references,
            tolerance_mm=args.tolerance_mm,
            retrieval_k=args.retrieval_k,
        )
    except EvaluationInputError as exc:
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
