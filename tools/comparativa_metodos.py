"""CLI for the A/B/C/D method comparison (protocol: docs/COMPARATIVA_METODOS.md).

``freeze``  runs the methods on the public side and seals their outputs.
``score``   verifies the seal, then (and only then) opens the private reference.
``run``     does both in order.

Variants B, C and D call a model.  They need ``--enable-model-variants`` and an
``--adapter module:factory`` supplied by the operator; this tool ships no
provider.  Variant A is offline and deterministic.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any

from evaluation.comparativa import (
    ComparisonError,
    DevelopmentManifestReader,
    ManifestReader,
    PlankAssemblyCorpusReader,
    PlankAssemblyManifestReader,
    PrecedentIndex,
    RunLimits,
    build_methods,
    execute_run,
    render_markdown,
    score_run,
)
from evaluation.comparativa.model import canonical_json

REPO = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("freeze", "score", "run"))
    parser.add_argument("--corpus", choices=("development", "plankassembly", "plankassembly-corpus"), default="development")
    parser.add_argument("--demo-dir", type=Path, default=REPO / "data" / "planos_demo")
    parser.add_argument("--reference-dir", type=Path, default=REPO / "evaluation" / "reference")
    parser.add_argument("--public-dir", type=Path)
    parser.add_argument("--private-dir", type=Path)
    parser.add_argument("--staging-dir", type=Path, help="where public bundles are unpacked (default: <run-dir>/inputs)")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--variants", default="A", help="comma separated subset of A,B,C,D (default A)")
    parser.add_argument("--enable-model-variants", action="store_true", help="allow B/C/D (may incur cost via the adapter)")
    parser.add_argument("--adapter", help="module:factory returning a callable(AdapterRequest) -> AdapterResponse")
    parser.add_argument("--precedent-index", type=Path, help="admitted, annotated index for variant D")
    parser.add_argument("--repetitions", type=int, default=3, help="repetitions for stochastic variants")
    parser.add_argument("--tolerance-mm", type=float, default=1.0)
    parser.add_argument("--match-tolerance-mm", type=float, default=5.0)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--report-md", type=Path)
    return parser


def _reader(args: argparse.Namespace) -> ManifestReader:
    if args.corpus == "development":
        return DevelopmentManifestReader(args.demo_dir, args.reference_dir, args.staging_dir or args.run_dir / "inputs")
    if args.public_dir is None or args.private_dir is None:
        raise ComparisonError(f"{args.corpus} corpus needs --public-dir and --private-dir")
    staging = args.staging_dir or args.run_dir / "inputs"
    reader_class = PlankAssemblyCorpusReader if args.corpus == "plankassembly-corpus" else PlankAssemblyManifestReader
    return reader_class(args.public_dir, args.private_dir, staging)


def _load_adapter(spec: str) -> Any:
    module_name, _, attribute = spec.partition(":")
    if not module_name or not attribute:
        raise ComparisonError("--adapter must look like module:factory")
    factory = getattr(importlib.import_module(module_name), attribute)
    return factory()


def _write_reports(args: argparse.Namespace, report: dict[str, Any]) -> None:
    json_path = args.report_json or args.run_dir / "report.json"
    md_path = args.report_md or args.run_dir / "report.md"
    json_path.write_bytes(canonical_json(report))
    md_path.write_text(render_markdown(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        reader = _reader(args)
        if args.command in {"freeze", "run"}:
            variants = tuple(item.strip().upper() for item in args.variants.split(",") if item.strip())
            adapter = _load_adapter(args.adapter) if args.adapter else None
            index = PrecedentIndex.from_file(args.precedent_index) if args.precedent_index else None
            methods = build_methods(
                variants, enable_model_variants=args.enable_model_variants,
                adapter=adapter, precedent_index=index,
            )
            record = execute_run(
                reader, methods, args.run_dir,
                limits=RunLimits(repetitions_stochastic=args.repetitions),
                requested_variants=variants,
            )
            # Record this digest outside the run directory to detect a rewritten freeze record.
            print(f"outputs_digest {record['outputs_digest']}")
        if args.command in {"score", "run"}:
            report = score_run(
                reader, args.run_dir,
                tolerance_mm=args.tolerance_mm, match_tolerance_mm=args.match_tolerance_mm,
            )
            _write_reports(args, report)
    except ComparisonError as exc:
        print(f"comparison error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
