"""Deterministic similarity calibration tool for semantic embeddings and geometric descriptors."""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

import numpy as np

from backend.app.contratos.modelos import LibraryItem
from backend.app.similarity.service import geometric_match

DEFAULT_DB_PATH = Path(".vexplorer-data/vexplorer.sqlite3")
_PERCENTILES = (10, 25, 50, 75, 90, 95)


@dataclass(frozen=True)
class EmbeddingRecord:
    """Normalized embedding record loaded from SQLite."""

    record_id: str
    model: str
    dimensions: int
    descriptor_version: str
    vector: tuple[float, ...]
    family: str | None = None


def _normalize_family(family: str | None) -> str | None:
    if family is None:
        return None
    cleaned = family.strip()
    if not cleaned or cleaned == "unknown":
        return None
    return cleaned


def _round6(value: float) -> float:
    return round(float(value), 6)


def compute_distribution_stats(scores: np.ndarray) -> dict[str, Any]:
    """Compute count, extrema, mean, std, and percentiles for a 1D score array."""
    arr = np.asarray(scores, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError("scores must be a 1D array")
    if arr.size == 0:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
            "percentiles": {f"p{p}": None for p in _PERCENTILES},
        }
    pct_values = np.percentile(arr, _PERCENTILES)
    return {
        "count": int(arr.size),
        "min": _round6(np.min(arr)),
        "max": _round6(np.max(arr)),
        "mean": _round6(np.mean(arr)),
        "std": _round6(np.std(arr)),
        "percentiles": {
            f"p{p}": _round6(val) for p, val in zip(_PERCENTILES, pct_values, strict=True)
        },
    }


def compute_separation(same_scores: np.ndarray, diff_scores: np.ndarray) -> dict[str, Any]:
    """Compute separation metrics between same-type and different-type pair scores."""
    same = np.asarray(same_scores, dtype=np.float64)
    diff = np.asarray(diff_scores, dtype=np.float64)
    same_count = int(same.size)
    diff_count = int(diff.size)
    if same_count == 0 or diff_count == 0:
        return {
            "same_type_count": same_count,
            "different_type_count": diff_count,
            "mean_gap": None,
            "median_gap": None,
            "p10_same_minus_p90_diff": None,
            "roc_auc": None,
        }
    diff_sorted = np.sort(diff)
    less = np.searchsorted(diff_sorted, same, side="left")
    le = np.searchsorted(diff_sorted, same, side="right")
    ties = le - less
    auc = float(np.sum(less + 0.5 * ties) / (same_count * diff_count))
    return {
        "same_type_count": same_count,
        "different_type_count": diff_count,
        "mean_gap": _round6(np.mean(same) - np.mean(diff)),
        "median_gap": _round6(np.median(same) - np.median(diff)),
        "p10_same_minus_p90_diff": _round6(np.percentile(same, 10) - np.percentile(diff, 90)),
        "roc_auc": _round6(auc),
    }


def suggest_thresholds(
    overall_stats: dict[str, Any],
    same_stats: dict[str, Any],
    diff_stats: dict[str, Any],
) -> dict[str, Any]:
    """Derive deterministic similarity and near-duplicate thresholds from distributions."""
    if overall_stats["count"] == 0:
        return {
            "similarity_threshold": None,
            "near_duplicate_threshold": None,
            "basis": "insufficient_pairs",
        }
    if same_stats["count"] > 0 and diff_stats["count"] > 0:
        diff_p90 = float(diff_stats["percentiles"]["p90"])
        same_p25 = float(same_stats["percentiles"]["p25"])
        same_p90 = float(same_stats["percentiles"]["p90"])
        sim_thresh = _round6(np.clip(0.5 * (diff_p90 + same_p25), 0.0, 1.0))
        near_dup = _round6(np.clip(max(sim_thresh, same_p90), 0.0, 1.0))
        return {
            "similarity_threshold": sim_thresh,
            "near_duplicate_threshold": near_dup,
            "basis": "same_vs_different_type",
        }
    ref = same_stats if same_stats["count"] > 0 else overall_stats
    sim_thresh = _round6(np.clip(float(ref["percentiles"]["p50"]), 0.0, 1.0))
    near_dup = _round6(np.clip(max(sim_thresh, float(ref["percentiles"]["p90"])), 0.0, 1.0))
    return {
        "similarity_threshold": sim_thresh,
        "near_duplicate_threshold": near_dup,
        "basis": "overall_percentiles",
    }


def _split_pair_masks(families: Sequence[str | None], idx_i: np.ndarray, idx_j: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Build boolean masks for same-type and different-type pairs with known families."""
    same_mask = np.zeros(idx_i.shape[0], dtype=bool)
    diff_mask = np.zeros(idx_i.shape[0], dtype=bool)
    for k, (i, j) in enumerate(zip(idx_i.tolist(), idx_j.tolist(), strict=True)):
        fam_i = _normalize_family(families[i])
        fam_j = _normalize_family(families[j])
        if fam_i is None or fam_j is None:
            continue
        if fam_i == fam_j:
            same_mask[k] = True
        else:
            diff_mask[k] = True
    return same_mask, diff_mask


def pairwise_cosine_scores(
    vectors: Sequence[Sequence[float]],
    families: Sequence[str | None],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute pairwise cosine similarities and split by same-type vs different-type."""
    if len(vectors) != len(families):
        raise ValueError("vectors and families length mismatch")
    if len(vectors) < 2:
        empty = np.empty(0, dtype=np.float64)
        return empty, empty, empty
    mat = np.asarray(vectors, dtype=np.float64)
    if mat.ndim != 2 or mat.shape[1] == 0:
        raise ValueError("invalid embedding matrix")
    if not np.all(np.isfinite(mat)):
        raise ValueError("invalid_embedding: non-finite values")
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    if np.any(norms <= 0.0):
        raise ValueError("invalid_embedding: zero-norm vector")
    normed = mat / norms
    sim_matrix = np.clip(normed @ normed.T, -1.0, 1.0)
    idx_i, idx_j = np.triu_indices(mat.shape[0], k=1)
    all_scores = sim_matrix[idx_i, idx_j]
    same_mask, diff_mask = _split_pair_masks(families, idx_i, idx_j)
    return all_scores, all_scores[same_mask], all_scores[diff_mask]


def pairwise_geometric_scores(
    items: Sequence[LibraryItem],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute pairwise geometric similarity scores for items in the same descriptor space."""
    n = len(items)
    if n < 2:
        empty = np.empty(0, dtype=np.float64)
        return empty, empty, empty
    scores: list[float] = []
    idx_i_list: list[int] = []
    idx_j_list: list[int] = []
    for i in range(n):
        for j in range(i + 1, n):
            match = geometric_match(items[i].descriptor, items[j])
            scores.append(match.score)
            idx_i_list.append(i)
            idx_j_list.append(j)
    all_scores = np.asarray(scores, dtype=np.float64)
    families = [_normalize_family(item.descriptor.family) for item in items]
    same_mask, diff_mask = _split_pair_masks(
        families,
        np.asarray(idx_i_list, dtype=np.int64),
        np.asarray(idx_j_list, dtype=np.int64),
    )
    return all_scores, all_scores[same_mask], all_scores[diff_mask]


def _summarize_space(
    all_scores: np.ndarray,
    same_scores: np.ndarray,
    diff_scores: np.ndarray,
) -> dict[str, Any]:
    overall = compute_distribution_stats(all_scores)
    same = compute_distribution_stats(same_scores)
    diff = compute_distribution_stats(diff_scores)
    return {
        "overall": overall,
        "same_type": same,
        "different_type": diff,
        "separation": compute_separation(same_scores, diff_scores),
        "suggested_thresholds": suggest_thresholds(overall, same, diff),
    }


def _existing_tables(db: sqlite3.Connection) -> set[str]:
    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def _load_library_items(db: sqlite3.Connection, tables: set[str]) -> list[LibraryItem]:
    if "library_items" not in tables:
        return []
    rows = db.execute("SELECT payload FROM library_items ORDER BY run_id").fetchall()
    return [LibraryItem.model_validate_json(row[0]) for row in rows]


def _load_embedding_cache(
    db: sqlite3.Connection,
    tables: set[str],
    family_by_cache_key: dict[tuple[str, str, int, str], str | None],
) -> list[EmbeddingRecord]:
    if "embedding_cache" not in tables:
        return []
    rows = db.execute(
        "SELECT cache_key, model, dimensions, descriptor_version, vector_json "
        "FROM embedding_cache ORDER BY model, dimensions, descriptor_version, cache_key"
    ).fetchall()
    records: list[EmbeddingRecord] = []
    for cache_key, model, dimensions, descriptor_version, vector_json in rows:
        vec = tuple(float(x) for x in json.loads(vector_json))
        key = (str(cache_key), str(model), int(dimensions), str(descriptor_version))
        records.append(
            EmbeddingRecord(
                record_id=str(cache_key),
                model=str(model),
                dimensions=int(dimensions),
                descriptor_version=str(descriptor_version),
                vector=vec,
                family=family_by_cache_key.get(key),
            )
        )
    return records


def _load_historical_embeddings(
    db: sqlite3.Connection,
    tables: set[str],
) -> list[EmbeddingRecord]:
    if "historical_embeddings" not in tables:
        return []
    family_by_record_id: dict[str, str | None] = {}
    if "historical_records" in tables:
        rec_rows = db.execute("SELECT record_id, payload FROM historical_records").fetchall()
        for record_id, payload in rec_rows:
            data = json.loads(payload)
            family_by_record_id[str(record_id)] = _normalize_family(data.get("family"))
    rows = db.execute(
        "SELECT record_id, model, dimensions, vector "
        "FROM historical_embeddings ORDER BY model, dimensions, record_id"
    ).fetchall()
    return [
        EmbeddingRecord(
            record_id=str(record_id),
            model=str(model),
            dimensions=int(dimensions),
            descriptor_version="historical",
            vector=tuple(float(x) for x in json.loads(vector_json)),
            family=family_by_record_id.get(str(record_id)),
        )
        for record_id, model, dimensions, vector_json in rows
    ]


def _calibrate_semantic_records(records: Sequence[EmbeddingRecord]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, str], list[EmbeddingRecord]] = defaultdict(list)
    for rec in records:
        grouped[(rec.model, rec.dimensions, rec.descriptor_version)].append(rec)
    results: list[dict[str, Any]] = []
    for (model, dimensions, descriptor_version), group in sorted(grouped.items()):
        all_scores, same_scores, diff_scores = pairwise_cosine_scores(
            [rec.vector for rec in group],
            [rec.family for rec in group],
        )
        entry = {
            "model": model,
            "dimensions": dimensions,
            "descriptor_version": descriptor_version,
            "item_count": len(group),
        }
        entry.update(_summarize_space(all_scores, same_scores, diff_scores))
        results.append(entry)
    return results


def _calibrate_geometric_items(items: Sequence[LibraryItem]) -> list[dict[str, Any]]:
    grouped: dict[str, list[LibraryItem]] = defaultdict(list)
    for item in items:
        grouped[item.descriptor.descriptor_version].append(item)
    results: list[dict[str, Any]] = []
    for descriptor_version, group in sorted(grouped.items()):
        all_scores, same_scores, diff_scores = pairwise_geometric_scores(group)
        entry = {
            "descriptor_version": descriptor_version,
            "item_count": len(group),
        }
        entry.update(_summarize_space(all_scores, same_scores, diff_scores))
        results.append(entry)
    return results


def calibrate_database(
    db_path: Path,
    *,
    history_db_path: Path | None = None,
) -> dict[str, Any]:
    """Read SQLite tables and compute semantic and geometric similarity calibrations."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    if history_db_path is not None and not history_db_path.exists():
        raise FileNotFoundError(f"History database not found: {history_db_path}")

    with closing(sqlite3.connect(db_path)) as db:
        tables = _existing_tables(db)
        library_items = _load_library_items(db, tables)
        family_by_cache_key: dict[tuple[str, str, int, str], str | None] = {}
        conflicting_keys: set[tuple[str, str, int, str]] = set()
        for item in library_items:
            if item.embedding is None:
                continue
            key = (
                item.embedding.cache_key,
                item.embedding.model,
                item.embedding.dimensions,
                item.embedding.descriptor_version,
            )
            fam = _normalize_family(item.descriptor.family)
            if key in family_by_cache_key and family_by_cache_key[key] != fam:
                conflicting_keys.add(key)
            else:
                family_by_cache_key[key] = fam
        for key in conflicting_keys:
            family_by_cache_key[key] = None

        cache_records = _load_embedding_cache(db, tables, family_by_cache_key)
        historical_records = _load_historical_embeddings(db, tables)

    if history_db_path is not None:
        with closing(sqlite3.connect(history_db_path)) as hdb:
            htables = _existing_tables(hdb)
            historical_records.extend(_load_historical_embeddings(hdb, htables))

    return {
        "database": str(db_path),
        "history_database": str(history_db_path) if history_db_path is not None else None,
        "counts": {
            "library_items": len(library_items),
            "embedding_cache": len(cache_records),
            "historical_embeddings": len(historical_records),
        },
        "semantic": _calibrate_semantic_records(cache_records),
        "historical_semantic": _calibrate_semantic_records(historical_records),
        "geometric": _calibrate_geometric_items(library_items),
    }


def _format_stats_line(label: str, stats: dict[str, Any]) -> str:
    if stats["count"] == 0:
        return f"  {label}: count=0"
    pct = stats["percentiles"]
    return (
        f"  {label}: count={stats['count']} min={stats['min']:.4f} "
        f"p10={pct['p10']:.4f} p50={pct['p50']:.4f} p90={pct['p90']:.4f} "
        f"max={stats['max']:.4f} mean={stats['mean']:.4f}"
    )


def format_human_report(report: dict[str, Any]) -> str:
    """Format calibration report into a human-readable summary."""
    counts = report["counts"]
    lines = [
        f"Database: {report['database']}",
        (
            f"Counts: library_items={counts['library_items']} "
            f"embedding_cache={counts['embedding_cache']} "
            f"historical_embeddings={counts['historical_embeddings']}"
        ),
    ]
    for section, title in (
        ("semantic", "Semantic (embedding_cache)"),
        ("historical_semantic", "Semantic (historical_embeddings)"),
        ("geometric", "Geometric (library_items)"),
    ):
        entries = report[section]
        lines.append(f"\n[{title}] ({len(entries)} space(s))")
        for entry in entries:
            if "model" in entry:
                header = f"- {entry['model']} dim={entry['dimensions']} desc={entry['descriptor_version']} items={entry['item_count']}"
            else:
                header = f"- desc={entry['descriptor_version']} items={entry['item_count']}"
            lines.append(header)
            lines.append(_format_stats_line("overall", entry["overall"]))
            lines.append(_format_stats_line("same_type", entry["same_type"]))
            lines.append(_format_stats_line("different_type", entry["different_type"]))
            sep = entry["separation"]
            lines.append(
                f"  separation: mean_gap={sep['mean_gap']} median_gap={sep['median_gap']} roc_auc={sep['roc_auc']}"
            )
            thresh = entry["suggested_thresholds"]
            lines.append(
                f"  thresholds ({thresh['basis']}): similarity={thresh['similarity_threshold']} near_duplicate={thresh['near_duplicate_threshold']}"
            )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for similarity calibration."""
    parser = argparse.ArgumentParser(
        description="Calibrate semantic and geometric similarity distributions from SQLite."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--history-db",
        type=Path,
        default=None,
        help="Optional path to separate historical SQLite database",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )
    args = parser.parse_args(argv)
    try:
        report = calibrate_database(args.db, history_db_path=args.history_db)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_human_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
