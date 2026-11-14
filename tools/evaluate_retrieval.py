"""Offline retrieval evaluation metrics (P@k, Recall@k, MRR, nDCG@k) and geometric benchmark CLI."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path
import sys
from typing import Any

from backend.app.contratos.modelos import LibraryItem, Result
from backend.app.geometria import extract_drawing
from backend.app.semantic.descriptor import build_descriptor, descriptor_fingerprint
from backend.app.servicios.decomposition import derive_decomposition_scenarios
from backend.app.similarity.service import geometric_match


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_DIR = ROOT.joinpath("data", "planos_demo")
DEFAULT_PAIRS_PATH = ROOT.joinpath("evaluation", "reference", "retrieval_pairs.json")
_FIXED_TIMESTAMP = "2026-01-01T00:00:00+00:00"


def _validate_k(k: int) -> int:
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError(f"k must be a positive integer, got {k!r}")
    return k


def _validate_ranked_ids(ranked_ids: Sequence[str]) -> tuple[str, ...]:
    if isinstance(ranked_ids, (str, bytes)):
        raise TypeError("ranked_ids must be a sequence of ID strings, not a string")
    items = tuple(ranked_ids)
    for item_id in items:
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError(f"ranked_ids entries must be non-empty strings, got {item_id!r}")
    if len(items) != len(set(items)):
        raise ValueError("ranked_ids must not contain duplicate IDs")
    return items


def _validate_relevance(relevance_by_id: Mapping[str, int | float]) -> dict[str, float]:
    if not isinstance(relevance_by_id, Mapping):
        raise TypeError("relevance_by_id must be a mapping")
    normalized: dict[str, float] = {}
    for item_id, raw_grade in relevance_by_id.items():
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError(f"relevance_by_id keys must be non-empty strings, got {item_id!r}")
        if isinstance(raw_grade, bool) or not isinstance(raw_grade, (int, float)):
            raise ValueError(f"relevance grade for {item_id!r} must be numeric, got {raw_grade!r}")
        grade = float(raw_grade)
        if not math.isfinite(grade) or grade < 0.0:
            raise ValueError(f"relevance grade for {item_id!r} must be finite and >= 0, got {raw_grade!r}")
        normalized[item_id] = grade
    return normalized


def _dcg(grades: Sequence[float]) -> float:
    return sum(
        (2.0**grade - 1.0) / math.log2(position + 1)
        for position, grade in enumerate(grades, start=1)
        if grade > 0.0
    )


def precision_at_k(
    ranked_ids: Sequence[str],
    relevance_by_id: Mapping[str, int | float],
    k: int,
) -> float:
    """Compute Precision@k over binary relevance (grade > 0), dividing by k."""
    cutoff = _validate_k(k)
    ranked = _validate_ranked_ids(ranked_ids)
    relevance = _validate_relevance(relevance_by_id)
    hits = sum(1 for item_id in ranked[:cutoff] if relevance.get(item_id, 0.0) > 0.0)
    return hits / cutoff


def recall_at_k(
    ranked_ids: Sequence[str],
    relevance_by_id: Mapping[str, int | float],
    k: int,
) -> float:
    """Compute Recall@k over binary relevance (grade > 0); returns 0.0 if none are relevant."""
    cutoff = _validate_k(k)
    ranked = _validate_ranked_ids(ranked_ids)
    relevance = _validate_relevance(relevance_by_id)
    total_relevant = sum(1 for grade in relevance.values() if grade > 0.0)
    if total_relevant == 0:
        return 0.0
    hits = sum(1 for item_id in ranked[:cutoff] if relevance.get(item_id, 0.0) > 0.0)
    return hits / total_relevant


def reciprocal_rank(
    ranked_ids: Sequence[str],
    relevance_by_id: Mapping[str, int | float],
) -> float:
    """Compute reciprocal rank of the first relevant item (grade > 0), or 0.0 if absent."""
    ranked = _validate_ranked_ids(ranked_ids)
    relevance = _validate_relevance(relevance_by_id)
    for position, item_id in enumerate(ranked, start=1):
        if relevance.get(item_id, 0.0) > 0.0:
            return 1.0 / position
    return 0.0


def ndcg_at_k(
    ranked_ids: Sequence[str],
    relevance_by_id: Mapping[str, int | float],
    k: int,
) -> float:
    """Compute nDCG@k with exponential gain (2^rel - 1) and log2(rank + 1) discount."""
    cutoff = _validate_k(k)
    ranked = _validate_ranked_ids(ranked_ids)
    relevance = _validate_relevance(relevance_by_id)
    ideal_grades = sorted((grade for grade in relevance.values() if grade > 0.0), reverse=True)[:cutoff]
    idcg = _dcg(ideal_grades)
    if idcg <= 0.0:
        return 0.0
    dcg = _dcg([relevance.get(item_id, 0.0) for item_id in ranked[:cutoff]])
    return min(1.0, dcg / idcg)


def _normalize_ks(ks: Sequence[int]) -> tuple[int, ...]:
    if not ks:
        raise ValueError("ks must contain at least one positive integer")
    return tuple(sorted({_validate_k(k) for k in ks}))


def evaluate_rankings(
    queries: Sequence[Mapping[str, Any]],
    rankings_by_query: Mapping[str, Sequence[str]],
    ks: Sequence[int] = (1, 3, 5),
) -> dict[str, Any]:
    """Evaluate rankings across graded retrieval queries for P@k, Recall@k, MRR, and nDCG@k."""
    cutoffs = _normalize_ks(ks)
    if not isinstance(rankings_by_query, Mapping):
        raise TypeError("rankings_by_query must be a mapping")

    seen_query_ids: set[str] = set()
    per_query: list[dict[str, Any]] = []
    queries_with_relevant = 0

    for index, query in enumerate(queries):
        if not isinstance(query, Mapping):
            raise TypeError(f"queries[{index}] must be a mapping")
        query_id = query.get("query_id")
        if not isinstance(query_id, str) or not query_id.strip():
            raise ValueError(f"queries[{index}].query_id must be a non-empty string")
        if query_id in seen_query_ids:
            raise ValueError(f"duplicate query_id in queries: {query_id!r}")
        seen_query_ids.add(query_id)

        raw_relevance = query.get("relevance_by_id")
        if raw_relevance is None:
            raise ValueError(f"queries[{index}].relevance_by_id is required")
        relevance = _validate_relevance(raw_relevance)
        if query_id in relevance:
            raise ValueError(f"query {query_id!r} must not judge itself in relevance_by_id")

        ranked = _validate_ranked_ids(rankings_by_query.get(query_id, ()))
        if query_id in ranked:
            raise ValueError(f"ranking for {query_id!r} must exclude the query itself")

        relevant_count = sum(1 for grade in relevance.values() if grade > 0.0)
        if relevant_count > 0:
            queries_with_relevant += 1

        per_query.append(
            {
                "query_id": query_id,
                "ranked_ids": list(ranked),
                "relevant_count": relevant_count,
                "judged_candidate_count": len(relevance),
                "unjudged_in_ranking_count": sum(1 for item_id in ranked if item_id not in relevance),
                "reciprocal_rank": reciprocal_rank(ranked, relevance),
                "precision_at_k": {str(k): precision_at_k(ranked, relevance, k) for k in cutoffs},
                "recall_at_k": {str(k): recall_at_k(ranked, relevance, k) for k in cutoffs},
                "ndcg_at_k": {str(k): ndcg_at_k(ranked, relevance, k) for k in cutoffs},
            }
        )

    count = len(per_query)

    def _mean(values: Sequence[float]) -> float:
        return sum(values) / count if count else 0.0

    aggregate = {
        "mrr": _mean([item["reciprocal_rank"] for item in per_query]),
        "precision_at_k": {
            str(k): _mean([item["precision_at_k"][str(k)] for item in per_query])
            for k in cutoffs
        },
        "recall_at_k": {
            str(k): _mean([item["recall_at_k"][str(k)] for item in per_query])
            for k in cutoffs
        },
        "ndcg_at_k": {
            str(k): _mean([item["ndcg_at_k"][str(k)] for item in per_query])
            for k in cutoffs
        },
    }

    return {
        "ks": list(cutoffs),
        "query_count": count,
        "queries_with_relevant": queries_with_relevant,
        "queries_without_relevant": count - queries_with_relevant,
        "aggregate": aggregate,
        "per_query": per_query,
    }


def _discover_demo_filenames(demo_dir: Path) -> tuple[str, ...]:
    manifest_path = demo_dir / "fixture_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases = manifest.get("cases") if isinstance(manifest, dict) else None
        if not isinstance(cases, dict) or not cases:
            raise ValueError(f"invalid fixture manifest in {manifest_path}")
        return tuple(sorted(str(name) for name in cases))
    dxf_names = tuple(sorted(path.name for path in demo_dir.glob("*.dxf") if path.is_file()))
    if not dxf_names:
        raise FileNotFoundError(f"no DXF fixtures found in {demo_dir}")
    return dxf_names


def build_demo_items(demo_dir: Path = DEFAULT_DEMO_DIR) -> dict[str, LibraryItem]:
    """Build deterministic LibraryItem descriptors offline from public demo DXFs."""
    if not demo_dir.is_dir():
        raise FileNotFoundError(f"demo directory not found: {demo_dir}")

    items: dict[str, LibraryItem] = {}
    for filename in _discover_demo_filenames(demo_dir):
        dxf_path = demo_dir / filename
        if not dxf_path.is_file():
            raise FileNotFoundError(f"demo fixture not found: {dxf_path}")
        extraction = extract_drawing(dxf_path)
        scenarios = derive_decomposition_scenarios(extraction)
        result = Result(
            run_id=f"offline-{filename}",
            result_revision=1,
            state="needs_review",
            scenarios=scenarios,
            pieces=(),
            created_at=_FIXED_TIMESTAMP,
            input_semantics=extraction.input_kind,
        )
        descriptor = build_descriptor(result)
        items[filename] = LibraryItem(
            id=filename,
            run_id=result.run_id,
            result_revision=1,
            label=filename,
            descriptor=descriptor,
            descriptor_fingerprint=descriptor_fingerprint(descriptor),
            created_at=_FIXED_TIMESTAMP,
        )
    return items


def rank_geometric(
    queries: Sequence[Mapping[str, Any]],
    items_by_id: Mapping[str, LibraryItem],
) -> tuple[dict[str, list[str]], dict[str, list[dict[str, Any]]]]:
    """Rank compatible library items per query using deterministic geometric_match."""
    rankings: dict[str, list[str]] = {}
    scores: dict[str, list[dict[str, Any]]] = {}
    sorted_items = [item for _, item in sorted(items_by_id.items())]

    for query in queries:
        query_id = str(query["query_id"])
        query_item = items_by_id.get(query_id)
        if query_item is None:
            raise KeyError(f"query fixture not found in demo library: {query_id!r}")
        candidates = [
            item
            for item in sorted_items
            if item.id != query_item.id
            and item.run_id != query_item.run_id
            and item.descriptor.descriptor_version == query_item.descriptor.descriptor_version
        ]
        matches = sorted(
            (geometric_match(query_item.descriptor, candidate) for candidate in candidates),
            key=lambda match: (-match.score, match.library_item_id),
        )
        rankings[query_id] = [match.library_item_id for match in matches]
        scores[query_id] = [
            {"id": match.library_item_id, "score": match.score} for match in matches
        ]
    return rankings, scores


def load_retrieval_pairs(pairs_path: Path = DEFAULT_PAIRS_PATH) -> dict[str, Any]:
    """Load and validate a graded retrieval pairs JSON document."""
    if not pairs_path.is_file():
        raise FileNotFoundError(f"retrieval pairs file not found: {pairs_path}")
    payload = json.loads(pairs_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("retrieval pairs root must be a JSON object")
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("retrieval pairs 'queries' must be a non-empty array")
    return payload


def evaluate_demo_retrieval(
    pairs_path: Path = DEFAULT_PAIRS_PATH,
    demo_dir: Path = DEFAULT_DEMO_DIR,
    ks: Sequence[int] = (1, 3, 5),
) -> dict[str, Any]:
    """Evaluate offline geometric_match retrieval over demo fixtures against graded pairs."""
    payload = load_retrieval_pairs(pairs_path)
    queries = payload["queries"]
    items_by_id = build_demo_items(demo_dir)

    for index, query in enumerate(queries):
        if not isinstance(query, Mapping):
            raise TypeError(f"queries[{index}] must be an object")
        query_id = query.get("query_id")
        if not isinstance(query_id, str) or query_id not in items_by_id:
            raise ValueError(f"query_id {query_id!r} missing from demo library")
        relevance = query.get("relevance_by_id")
        if not isinstance(relevance, Mapping):
            raise ValueError(f"queries[{index}].relevance_by_id must be an object")
        missing_candidates = sorted(set(relevance) - set(items_by_id))
        if missing_candidates:
            raise ValueError(
                f"query {query_id!r} references missing demo items: {missing_candidates}"
            )

    rankings_by_query, scores_by_query = rank_geometric(queries, items_by_id)
    report = evaluate_rankings(queries, rankings_by_query, ks=ks)
    for entry in report["per_query"]:
        entry["candidate_scores"] = scores_by_query[entry["query_id"]]

    report["method"] = "geometric"
    report["schema_version"] = payload.get("schema_version")
    report["reference_version"] = payload.get("reference_version")
    report["demo_item_count"] = len(items_by_id)
    return report


def format_human_report(report: Mapping[str, Any]) -> str:
    """Render an evaluation report into a concise human-readable summary."""
    ks = report["ks"]
    aggregate = report["aggregate"]
    lines = [
        (
            f"Retrieval evaluation (method={report.get('method', 'unknown')}, "
            f"queries={report['query_count']}, demo_items={report.get('demo_item_count', 0)})"
        ),
        f"Aggregate MRR: {aggregate['mrr']:.4f}",
        "Aggregate by k: "
        + ", ".join(
            f"k={k} [P={aggregate['precision_at_k'][str(k)]:.4f}, "
            f"R={aggregate['recall_at_k'][str(k)]:.4f}, "
            f"nDCG={aggregate['ndcg_at_k'][str(k)]:.4f}]"
            for k in ks
        ),
    ]
    for entry in report["per_query"]:
        k_max = str(max(ks))
        lines.append(
            f"- {entry['query_id']}: MRR={entry['reciprocal_rank']:.4f} "
            f"P@{k_max}={entry['precision_at_k'][k_max]:.4f} "
            f"R@{k_max}={entry['recall_at_k'][k_max]:.4f} "
            f"nDCG@{k_max}={entry['ndcg_at_k'][k_max]:.4f} "
            f"top={entry['ranked_ids'][:3]}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for offline demo retrieval evaluation."""
    parser = argparse.ArgumentParser(
        description="Evaluate geometric retrieval on public demo fixtures against graded pairs."
    )
    parser.add_argument(
        "--pairs",
        type=Path,
        default=DEFAULT_PAIRS_PATH,
        help="Path to graded retrieval pairs JSON.",
    )
    parser.add_argument(
        "--demo-dir",
        type=Path,
        default=DEFAULT_DEMO_DIR,
        help=f"Directory containing demo DXF fixtures (default: {DEFAULT_DEMO_DIR}).",
    )
    parser.add_argument(
        "--k",
        type=int,
        nargs="+",
        default=[1, 3, 5],
        help="Cutoff values k for P@k, Recall@k, and nDCG@k (default: 1 3 5).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON.",
    )
    args = parser.parse_args(argv)

    try:
        report = evaluate_demo_retrieval(
            pairs_path=args.pairs,
            demo_dir=args.demo_dir,
            ks=args.k,
        )
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    else:
        print(format_human_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
