from __future__ import annotations

import builtins
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from tools.evaluate_retrieval import (
    build_demo_items,
    evaluate_demo_retrieval,
    evaluate_rankings,
    main,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = (ROOT / "evaluation" / "reference").resolve()
PAIRS_PATH = REFERENCE_DIR / "retrieval_pairs.json"
DEMO_DIR = ROOT / "data" / "planos_demo"


def _is_private_path(value: object) -> bool:
    try:
        candidate = Path(os.fspath(value)).resolve()
    except (TypeError, ValueError, OSError):
        return False
    return candidate == REFERENCE_DIR or REFERENCE_DIR in candidate.parents


@contextmanager
def _deny_reference_reads():
    original_open = builtins.open
    original_path_open = Path.open

    def guarded_open(file, *args, **kwargs):
        assert not _is_private_path(file), f"attempted forbidden private read: {file}"
        return original_open(file, *args, **kwargs)

    def guarded_path_open(path: Path, *args, **kwargs):
        assert not _is_private_path(path), f"attempted forbidden private read: {path}"
        return original_path_open(path, *args, **kwargs)

    with patch("builtins.open", guarded_open), patch.object(Path, "open", guarded_path_open):
        yield


def test_precision_at_k_exact_math_and_edge_cases() -> None:
    relevance = {"a": 3, "b": 1, "c": 0, "d": 2}
    ranking = ["a", "c", "b", "d"]

    assert precision_at_k(ranking, relevance, 1) == pytest.approx(1.0)
    assert precision_at_k(ranking, relevance, 2) == pytest.approx(0.5)
    assert precision_at_k(ranking, relevance, 3) == pytest.approx(2.0 / 3.0)
    # Always divides by k even when fewer than k items are ranked.
    assert precision_at_k(["a", "c"], relevance, 5) == pytest.approx(1.0 / 5.0)
    assert precision_at_k([], relevance, 3) == 0.0
    assert precision_at_k(ranking, {"a": 0, "c": 0}, 2) == 0.0
    assert precision_at_k(["unjudged"], relevance, 1) == 0.0

    for bad_k in (0, -1, -5, True, False):
        with pytest.raises(ValueError):
            precision_at_k(ranking, relevance, bad_k)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="duplicate"):
        precision_at_k(["a", "a"], relevance, 2)


def test_recall_at_k_exact_math_and_edge_cases() -> None:
    relevance = {"a": 3, "b": 2, "c": 1, "d": 0, "absent": 2}
    ranking = ["a", "d", "b", "c"]

    assert recall_at_k(ranking, relevance, 1) == pytest.approx(1.0 / 4.0)
    assert recall_at_k(ranking, relevance, 2) == pytest.approx(1.0 / 4.0)
    assert recall_at_k(ranking, relevance, 3) == pytest.approx(2.0 / 4.0)
    assert recall_at_k(ranking, relevance, 10) == pytest.approx(3.0 / 4.0)
    assert recall_at_k([], relevance, 3) == 0.0
    assert recall_at_k(ranking, {"a": 0, "d": 0}, 3) == 0.0
    assert recall_at_k(ranking, {}, 3) == 0.0

    for bad_k in (0, -2, False):
        with pytest.raises(ValueError):
            recall_at_k(ranking, relevance, bad_k)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="duplicate"):
        recall_at_k(["a", "b", "a"], relevance, 3)


def test_reciprocal_rank_exact_math_and_edge_cases() -> None:
    relevance = {"a": 2, "b": 1, "c": 0}

    assert reciprocal_rank(["a", "b", "c"], relevance) == pytest.approx(1.0)
    assert reciprocal_rank(["c", "x", "b", "a"], relevance) == pytest.approx(1.0 / 3.0)
    assert reciprocal_rank(["c", "x"], relevance) == 0.0
    assert reciprocal_rank([], relevance) == 0.0
    assert reciprocal_rank(["a", "b"], {"a": 0, "b": 0}) == 0.0

    with pytest.raises(ValueError, match="duplicate"):
        reciprocal_rank(["c", "c"], relevance)


def test_ndcg_at_k_ideal_reversed_and_edge_cases() -> None:
    relevance = {"a": 3, "b": 2, "c": 1, "d": 0}
    ideal = ["a", "b", "c", "d"]
    reversed_ranking = ["d", "c", "b", "a"]

    for k in (1, 2, 3, 4, 6):
        assert ndcg_at_k(ideal, relevance, k) == pytest.approx(1.0)

    expected_idcg_3 = (
        (2.0**3 - 1.0) / math.log2(2)
        + (2.0**2 - 1.0) / math.log2(3)
        + (2.0**1 - 1.0) / math.log2(4)
    )
    expected_dcg_3 = (
        0.0
        + (2.0**1 - 1.0) / math.log2(3)
        + (2.0**2 - 1.0) / math.log2(4)
    )
    assert ndcg_at_k(reversed_ranking, relevance, 1) == 0.0
    assert ndcg_at_k(reversed_ranking, relevance, 3) == pytest.approx(expected_dcg_3 / expected_idcg_3)

    # Floating-point relevance grades also work deterministically.
    float_rel = {"x": 2.5, "y": 1.0}
    assert ndcg_at_k(["x", "y"], float_rel, 2) == pytest.approx(1.0)
    assert ndcg_at_k(["y", "x"], float_rel, 2) < 1.0

    assert ndcg_at_k([], relevance, 3) == 0.0
    assert ndcg_at_k(ideal, {"a": 0, "b": 0}, 3) == 0.0
    assert ndcg_at_k(ideal, {}, 3) == 0.0

    for bad_k in (0, -1, True):
        with pytest.raises(ValueError):
            ndcg_at_k(ideal, relevance, bad_k)  # type: ignore[arg-type]


def test_evaluate_rankings_aggregates_ideal_vs_reversed_and_empty() -> None:
    queries = [
        {"query_id": "q1", "relevance_by_id": {"a": 3, "b": 2, "c": 1, "n": 0}},
        {"query_id": "q2", "relevance_by_id": {"x": 2, "y": 1, "n": 0}},
    ]
    ideal_report = evaluate_rankings(
        queries,
        {"q1": ["a", "b", "c", "n"], "q2": ["x", "y", "n"]},
        ks=(3, 1, 3),
    )
    assert ideal_report["ks"] == [1, 3]
    assert ideal_report["query_count"] == 2
    assert ideal_report["queries_with_relevant"] == 2
    assert ideal_report["queries_without_relevant"] == 0
    assert ideal_report["aggregate"]["mrr"] == pytest.approx(1.0)
    assert ideal_report["aggregate"]["precision_at_k"]["1"] == pytest.approx(1.0)
    assert ideal_report["aggregate"]["ndcg_at_k"]["1"] == pytest.approx(1.0)
    assert ideal_report["aggregate"]["ndcg_at_k"]["3"] == pytest.approx(1.0)
    assert ideal_report["aggregate"]["recall_at_k"]["3"] == pytest.approx(1.0)

    reversed_report = evaluate_rankings(
        queries,
        {"q1": ["n", "c", "b", "a"], "q2": ["n", "y", "x"]},
        ks=(1, 3),
    )
    assert reversed_report["aggregate"]["mrr"] == pytest.approx(0.5)
    assert reversed_report["aggregate"]["precision_at_k"]["1"] == pytest.approx(0.0)
    assert reversed_report["aggregate"]["ndcg_at_k"]["1"] == pytest.approx(0.0)
    assert reversed_report["aggregate"]["ndcg_at_k"]["3"] < ideal_report["aggregate"]["ndcg_at_k"]["3"]

    empty_report = evaluate_rankings([], {}, ks=(1, 3))
    assert empty_report["query_count"] == 0
    assert empty_report["aggregate"]["mrr"] == 0.0
    assert empty_report["aggregate"]["ndcg_at_k"] == {"1": 0.0, "3": 0.0}

    with pytest.raises(ValueError, match="must exclude the query itself"):
        evaluate_rankings(queries[:1], {"q1": ["q1", "a"]}, ks=(1,))


def test_retrieval_pairs_reference_is_curated_graded_and_symmetric() -> None:
    payload = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0.0"
    assert payload["evaluation_policy"]["runtime_must_not_read_this_file"] is True
    assert payload["evaluation_policy"]["descriptor_must_ignore_filenames_and_ids"] is True

    queries = {entry["query_id"]: entry["relevance_by_id"] for entry in payload["queries"]}
    assert {
        "estanteria_montada.dxf",
        "mueble_demo_004.dxf",
        "mueble_demo_002.dxf",
        "mueble_demo_003.dxf",
        "estanteria_incompleta.dxf",
    } <= set(queries)

    # Check graded anchor pairs required by the benchmark definition.
    assert queries["estanteria_montada.dxf"]["mueble_demo_004.dxf"] == 3
    assert queries["mueble_demo_004.dxf"]["estanteria_montada.dxf"] == 3
    assert queries["estanteria_montada.dxf"]["mueble_demo_002.dxf"] == 2
    assert queries["mueble_demo_002.dxf"]["estanteria_montada.dxf"] == 2
    assert queries["estanteria_montada.dxf"]["mueble_demo_003.dxf"] == 1
    assert queries["mueble_demo_003.dxf"]["estanteria_montada.dxf"] == 1
    assert queries["estanteria_montada.dxf"]["mueble_demo_unidades_desconocidas.dxf"] == 0
    assert queries["estanteria_montada.dxf"]["mueble_demo_trapecio.dxf"] == 0

    observed_grades = {
        grade
        for relevance in queries.values()
        for grade in relevance.values()
    }
    assert observed_grades == {0, 1, 2, 3}

    for query_id, relevance in queries.items():
        assert query_id not in relevance
        for candidate_id, grade in relevance.items():
            if candidate_id in queries:
                assert queries[candidate_id][query_id] == grade


def test_demo_descriptor_builder_and_geometric_evaluation() -> None:
    with _deny_reference_reads():
        items = build_demo_items(DEMO_DIR)

    assert len(items) == 7
    assert items["estanteria_montada.dxf"].descriptor == items["mueble_demo_004.dxf"].descriptor
    assert (
        items["estanteria_montada.dxf"].descriptor_fingerprint
        == items["mueble_demo_004.dxf"].descriptor_fingerprint
    )

    first = evaluate_demo_retrieval(pairs_path=PAIRS_PATH, demo_dir=DEMO_DIR, ks=(1, 3, 5))
    second = evaluate_demo_retrieval(pairs_path=PAIRS_PATH, demo_dir=DEMO_DIR, ks=(1, 3, 5))
    assert first == second
    assert first["method"] == "geometric"
    assert first["query_count"] == 5
    assert first["demo_item_count"] == 7

    agg = first["aggregate"]
    assert agg["mrr"] == pytest.approx(1.0)
    assert agg["precision_at_k"] == {"1": pytest.approx(1.0), "3": pytest.approx(1.0), "5": pytest.approx(0.8)}
    assert agg["recall_at_k"] == {"1": pytest.approx(0.25), "3": pytest.approx(0.75), "5": pytest.approx(1.0)}
    assert 0.0 < agg["ndcg_at_k"]["1"] < agg["ndcg_at_k"]["3"] <= agg["ndcg_at_k"]["5"] <= 1.0

    per_query = {entry["query_id"]: entry for entry in first["per_query"]}
    primary = per_query["estanteria_montada.dxf"]
    scores = {row["id"]: row["score"] for row in primary["candidate_scores"]}
    assert scores["mueble_demo_004.dxf"] == pytest.approx(1.0)
    assert scores["mueble_demo_002.dxf"] > scores["mueble_demo_003.dxf"]
    assert scores["mueble_demo_trapecio.dxf"] == 0.0
    assert scores["mueble_demo_unidades_desconocidas.dxf"] == 0.0
    assert primary["unjudged_in_ranking_count"] == 0
    assert primary["ndcg_at_k"]["1"] == pytest.approx(3.0 / 7.0)

    # Translated duplicate must reproduce the exact same metrics as primary.
    translated = per_query["mueble_demo_004.dxf"]
    assert translated["precision_at_k"] == primary["precision_at_k"]
    assert translated["recall_at_k"] == primary["recall_at_k"]
    assert translated["ndcg_at_k"] == primary["ndcg_at_k"]


def test_cli_json_human_and_invalid_args() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "tools.evaluate_retrieval", "--pairs", str(PAIRS_PATH), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    parsed = json.loads(proc.stdout)
    assert parsed["query_count"] == 5
    assert parsed["aggregate"]["mrr"] == pytest.approx(1.0)

    # Default --pairs path works without explicitly passing --pairs.
    default_proc = subprocess.run(
        [sys.executable, "-m", "tools.evaluate_retrieval", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert default_proc.returncode == 0, default_proc.stderr
    assert json.loads(default_proc.stdout) == parsed

    human_proc = subprocess.run(
        [sys.executable, "-m", "tools.evaluate_retrieval"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert human_proc.returncode == 0, human_proc.stderr
    assert "Aggregate MRR: 1.0000" in human_proc.stdout

    assert main(["--pairs", str(ROOT / "missing_pairs.json")]) == 1
    assert main(["--k", "0"]) == 1


def test_backend_app_never_imports_or_reads_retrieval_pairs() -> None:
    backend_app = ROOT / "backend" / "app"
    forbidden = (
        "retrieval_pairs.json",
        "evaluate_retrieval",
        "/".join(("evaluation", "reference")),
    )
    for py_file in backend_app.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8", errors="ignore").replace("\\", "/").casefold()
        for token in forbidden:
            assert token.casefold() not in content, f"{py_file} references {token!r}"
