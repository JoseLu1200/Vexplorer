from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import numpy as np
import pytest
import tools.calibrate_similarity as calibrator

from backend.app.contratos.modelos import (
    DescriptorDimensions,
    EmbeddingMetadata,
    FurnitureDescriptorV2,
    FurnitureDescriptorV3,
    LibraryItem,
    RoleQuantity,
    TableDescriptorComponentFeature,
)
from backend.app.similarity.thresholds import resolve_group_threshold, resolve_near_duplicate_threshold, resolve_similarity_threshold
from tools.calibrate_similarity import (
    calibrate_database,
    compute_distribution_stats,
    compute_separation,
    main,
    pairwise_cosine_scores,
    suggest_thresholds,
)


def _make_v2_item(
    run_id: str,
    *,
    width_mm: float,
    depth_mm: float,
    height_mm: float,
    thickness_mm: float,
    family: str = "rectangular_shelving",
    cache_key: str | None = None,
) -> LibraryItem:
    embedding = None
    if cache_key is not None:
        embedding = EmbeddingMetadata(
            model="text-embedding-3-small",
            dimensions=4,
            descriptor_version="furniture-v2",
            cache_key=cache_key,
            status="cache",
        )
    return LibraryItem(
        id=f"lib-{run_id}",
        run_id=run_id,
        result_revision=1,
        label=f"Item {run_id}",
        descriptor=FurnitureDescriptorV2(
            family=family,  # type: ignore[arg-type]
            dimensions=DescriptorDimensions(
                width_mm=width_mm,
                depth_mm=depth_mm,
                height_mm=height_mm,
            ),
            roles=(
                RoleQuantity(role="side", quantity=2),
                RoleQuantity(role="shelf", quantity=3),
            ),
            structure="top_base_between_sides",
            thicknesses_mm=(thickness_mm,),
            classification_status="confirmed",
            unknown_fields=(),
        ),
        descriptor_fingerprint="a" * 64,
        created_at="2026-01-01T00:00:00Z",
        embedding=embedding,
    )


def _make_v3_item(
    run_id: str,
    *,
    width_mm: float,
    depth_mm: float,
    height_mm: float,
    thickness_mm: float,
) -> LibraryItem:
    return LibraryItem(
        id=f"lib-{run_id}",
        run_id=run_id,
        result_revision=1,
        label=f"Table {run_id}",
        descriptor=FurnitureDescriptorV3(
            dimensions=DescriptorDimensions(
                width_mm=width_mm,
                depth_mm=depth_mm,
                height_mm=height_mm,
            ),
            structure="side_support_table",
            components=(
                TableDescriptorComponentFeature(
                    role="tabletop",
                    quantity=1,
                    length_mm=width_mm,
                    width_mm=depth_mm,
                    thickness_mm=thickness_mm,
                    field_states={
                        "quantity": "confirmed",
                        "length_mm": "confirmed",
                        "width_mm": "confirmed",
                        "thickness_mm": "confirmed",
                    },
                ),
            ),
        ),
        descriptor_fingerprint="b" * 64,
        created_at="2026-01-01T00:00:00Z",
    )


def _create_synthetic_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE library_items (
                run_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE embedding_cache (
                cache_key TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                descriptor_version TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE historical_records (
                record_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                revision TEXT NOT NULL,
                origin TEXT NOT NULL,
                payload TEXT NOT NULL,
                payload_hash TEXT NOT NULL
            );
            CREATE TABLE historical_embeddings (
                record_id TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                model TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                vector TEXT NOT NULL,
                PRIMARY KEY (record_id, payload_hash, model, dimensions)
            );
            """
        )
        v2_items = [
            _make_v2_item("r1", width_mm=800, depth_mm=400, height_mm=1800, thickness_mm=19, cache_key="ck1"),
            _make_v2_item("r2", width_mm=800, depth_mm=400, height_mm=1800, thickness_mm=19, cache_key="ck2"),
            _make_v2_item("r3", width_mm=1600, depth_mm=400, height_mm=900, thickness_mm=25, family="unknown", cache_key="ck3"),
        ]
        v3_items = [
            _make_v3_item("t1", width_mm=1200, depth_mm=800, height_mm=750, thickness_mm=30),
            _make_v3_item("t2", width_mm=1400, depth_mm=800, height_mm=750, thickness_mm=30),
        ]
        for item in [*v2_items, *v3_items]:
            db.execute(
                "INSERT INTO library_items (run_id, payload) VALUES (?, ?)",
                (item.run_id, item.model_dump_json()),
            )

        cache_rows = [
            ("ck1", "text-embedding-3-small", 4, "furniture-v2", [1.0, 0.0, 0.0, 0.0]),
            ("ck2", "text-embedding-3-small", 4, "furniture-v2", [0.9, 0.43589, 0.0, 0.0]),
            ("ck3", "text-embedding-3-small", 4, "furniture-v2", [0.0, 0.0, 1.0, 0.0]),
        ]
        for ck, model, dim, dv, vec in cache_rows:
            db.execute(
                "INSERT INTO embedding_cache VALUES (?, ?, ?, ?, ?, ?)",
                (ck, model, dim, dv, json.dumps(vec), "2026-01-01T00:00:00Z"),
            )

        hist_records = [
            ("h1", "shelving", [1.0, 0.0, 0.0]),
            ("h2", "shelving", [0.8, 0.6, 0.0]),
            ("h3", "table", [0.0, 0.0, 1.0]),
            ("h4", "table", [0.0, 0.1, 0.994987]),
        ]
        for rec_id, fam, vec in hist_records:
            payload = json.dumps({"record_id": rec_id, "family": fam})
            db.execute(
                "INSERT INTO historical_records VALUES (?, ?, ?, ?, ?, ?)",
                (rec_id, "proj-1", "rev-1", "synthetic", payload, f"hash-{rec_id}"),
            )
            db.execute(
                "INSERT INTO historical_embeddings VALUES (?, ?, ?, ?, ?)",
                (rec_id, f"hash-{rec_id}", "text-embedding-3-large", 3, json.dumps(vec)),
            )


def test_compute_distribution_stats_empty_and_known_values() -> None:
    empty = compute_distribution_stats(np.empty(0, dtype=np.float64))
    assert empty["count"] == 0
    assert empty["min"] is None
    assert empty["percentiles"]["p50"] is None

    scores = np.array([0.1, 0.2, 0.3, 0.4, 0.5], dtype=np.float64)
    stats = compute_distribution_stats(scores)
    assert stats["count"] == 5
    assert stats["min"] == pytest.approx(0.1)
    assert stats["max"] == pytest.approx(0.5)
    assert stats["mean"] == pytest.approx(0.3)
    assert stats["std"] == pytest.approx(float(np.std(scores)), abs=1e-6)
    assert stats["percentiles"]["p50"] == pytest.approx(0.3)
    assert stats["percentiles"]["p10"] == pytest.approx(0.14)
    assert stats["percentiles"]["p90"] == pytest.approx(0.46)


def test_compute_separation_and_roc_auc() -> None:
    same = np.array([0.8, 0.9], dtype=np.float64)
    diff = np.array([0.1, 0.2], dtype=np.float64)
    sep = compute_separation(same, diff)
    assert sep["same_type_count"] == 2
    assert sep["different_type_count"] == 2
    assert sep["mean_gap"] == pytest.approx(0.7)
    assert sep["median_gap"] == pytest.approx(0.7)
    assert sep["p10_same_minus_p90_diff"] > 0.0
    assert sep["roc_auc"] == pytest.approx(1.0)

    tied = compute_separation(np.array([0.5, 0.5]), np.array([0.5, 0.5]))
    assert tied["roc_auc"] == pytest.approx(0.5)

    missing = compute_separation(np.array([0.5]), np.empty(0))
    assert missing["mean_gap"] is None
    assert missing["roc_auc"] is None


def test_pairwise_cosine_scores_splits_known_and_unknown_families() -> None:
    vectors = [
        [1.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    families = ["shelving", "shelving", "table", "table", "unknown"]
    all_scores, same_scores, diff_scores = pairwise_cosine_scores(vectors, families)

    assert all_scores.size == 10
    assert same_scores.size == 2
    assert diff_scores.size == 4
    assert np.allclose(same_scores, [1.0, 1.0])
    assert np.allclose(diff_scores, [0.0, 0.0, 0.0, 0.0])

    with pytest.raises(ValueError, match="zero-norm"):
        pairwise_cosine_scores([[0.0, 0.0], [1.0, 0.0]], ["a", "b"])


def test_pairwise_cosine_scores_is_stable_for_large_finite_vectors() -> None:
    all_scores, same_scores, diff_scores = pairwise_cosine_scores([[1e200, 1e200], [1e200, 1e200]], ["shelving", "shelving"])
    assert all_scores == pytest.approx([1.0])
    assert same_scores == pytest.approx([1.0])
    assert diff_scores.size == 0


def test_suggest_thresholds_modes() -> None:
    overall = compute_distribution_stats(np.array([0.0, 0.1, 0.8, 0.9]))
    same = compute_distribution_stats(np.array([0.8, 0.9]))
    diff = compute_distribution_stats(np.array([0.0, 0.1]))
    both = suggest_thresholds(overall, same, diff)
    assert both["basis"] == "same_vs_different_type"
    assert 0.0 <= both["similarity_threshold"] <= both["near_duplicate_threshold"] <= 1.0

    empty_diff = compute_distribution_stats(np.empty(0))
    only_same = suggest_thresholds(same, same, empty_diff)
    assert only_same["basis"] == "overall_percentiles"
    assert only_same["similarity_threshold"] == same["percentiles"]["p50"]
    assert only_same["near_duplicate_threshold"] == same["percentiles"]["p90"]

    empty = compute_distribution_stats(np.empty(0))
    none_res = suggest_thresholds(empty, empty, empty)
    assert none_res == {
        "similarity_threshold": None,
        "group_threshold": None,
        "near_duplicate_threshold": None,
        "basis": "insufficient_pairs",
    }


def test_calibrate_database_on_synthetic_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "synthetic.sqlite3"
    _create_synthetic_db(db_path)

    report = calibrate_database(db_path)
    assert report["counts"] == {
        "library_items": 5,
        "embedding_cache": 3,
        "historical_embeddings": 4,
    }

    assert len(report["semantic"]) == 1
    sem = report["semantic"][0]
    assert sem["model"] == "text-embedding-3-small"
    assert sem["dimensions"] == 4
    assert sem["descriptor_version"] == "furniture-v2"
    assert sem["overall"]["count"] == 3
    assert sem["same_type"]["count"] == 1
    assert sem["same_type"]["min"] == pytest.approx(0.9, abs=1e-5)
    assert sem["different_type"]["count"] == 0

    assert len(report["historical_semantic"]) == 1
    hist = report["historical_semantic"][0]
    assert hist["model"] == "text-embedding-3-large"
    assert hist["dimensions"] == 3
    assert hist["overall"]["count"] == 6
    assert hist["same_type"]["count"] == 2
    assert hist["different_type"]["count"] == 4
    assert hist["separation"]["roc_auc"] == pytest.approx(1.0)
    assert hist["separation"]["mean_gap"] > 0.7
    assert hist["suggested_thresholds"]["basis"] == "same_vs_different_type"

    geom_by_ver = {entry["descriptor_version"]: entry for entry in report["geometric"]}
    assert set(geom_by_ver) == {"furniture-v2", "furniture-v3"}
    assert geom_by_ver["furniture-v2"]["overall"]["count"] == 3
    assert geom_by_ver["furniture-v2"]["same_type"]["count"] == 1
    assert geom_by_ver["furniture-v2"]["same_type"]["max"] == pytest.approx(1.0)
    assert geom_by_ver["furniture-v3"]["overall"]["count"] == 1
    assert geom_by_ver["furniture-v3"]["same_type"]["count"] == 1


def test_runtime_threshold_export_round_trips_through_resolver(tmp_path: Path) -> None:
    db_path = tmp_path / "synthetic.sqlite3"
    config_path = tmp_path / "thresholds.json"
    _create_synthetic_db(db_path)

    config = calibrator.build_runtime_threshold_config(calibrate_database(db_path))
    config_path.write_text(json.dumps(config), encoding="utf-8")

    semantic = next(iter(config["similarity"].values()))
    assert resolve_similarity_threshold("semantic", "furniture-v2", "text-embedding-3-small", config_path=config_path) == semantic
    assert resolve_group_threshold("semantic", "furniture-v2", "text-embedding-3-small", config_path=config_path) == next(iter(config["group"].values()))
    assert resolve_near_duplicate_threshold("semantic", "furniture-v2", "text-embedding-3-small", config_path=config_path) == next(iter(config["near_duplicate"].values()))


def test_cli_json_and_human_output_and_missing_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "cli.sqlite3"
    thresholds_path = tmp_path / "thresholds.json"
    _create_synthetic_db(db_path)

    proc = subprocess.run(
        [sys.executable, "-m", "tools.calibrate_similarity", "--db", str(db_path), "--json"],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    parsed = json.loads(proc.stdout)
    assert parsed["counts"]["library_items"] == 5
    assert len(parsed["historical_semantic"]) == 1

    assert main(["--db", str(db_path), "--thresholds-output", str(thresholds_path)]) == 0
    exported = json.loads(thresholds_path.read_text(encoding="utf-8"))
    assert set(exported) == {"similarity", "group", "near_duplicate"}
    assert exported["similarity"]["semantic:furniture-v2:text-embedding-3-small"] > 0

    assert main(["--db", str(db_path)]) == 0
    captured = capsys.readouterr()
    assert "Semantic (embedding_cache)" in captured.out
    assert "Geometric (library_items)" in captured.out

    assert main(["--db", str(tmp_path / "missing.sqlite3")]) == 1
    err_captured = capsys.readouterr()
    assert "Database not found" in err_captured.err
