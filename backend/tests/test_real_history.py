from __future__ import annotations

import json
import sqlite3
import shutil

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from backend.app.api.history import create_history_router
from backend.app.main import create_app
from backend.app.historico.models import (
    HistoricalImport,
    HistoricalTarget,
    ProvisionalDimension,
    ProvisionalQuantity,
    ProvisionalScenarioRequest,
    ProvisionalScenarioRow,
    ProvisionalScenarioSnapshot,
    ProvisionalText,
)
from backend.app.historico.real_service import HistoricalStore
from backend.app.semantic.embeddings import EmbeddingResult
from backend.app.semantic.embeddings import EMBEDDINGGEMMA2_TEXT_PREPROCESSING, EmbeddingSpaceIdentity


def _record(
    record_id: str = "job-001",
    *,
    project_id: str = "project-001",
    revision: str = "r1",
    origin: str = "actual",
    material: str = "oak veneer",
    finish: str = "clear lacquer",
    area_mm2: float = 2_000_000,
    quantity: int = 2,
    cost: float = 300,
    hours: float = 10,
) -> dict:
    return {
        "record_id": record_id,
        "project_id": project_id,
        "revision": revision,
        "family": "rectangular_table",
        "width_mm": 1000,
        "depth_mm": 500,
        "height_mm": 750,
        "area_mm2": area_mm2,
        "quantity": quantity,
        "material": material,
        "finish": finish,
        "currency": "EUR",
        "actual_cost": cost,
        "cost_basis": "actual",
        "manufacturing_hours": hours,
        "origin": origin,
        "provenance": {
            "source": "ERP work order WO-42" if origin == "actual" else "demo fixture",
            "source_date": "2026-10-31",
        },
        "included_scope": ["material", "labor"],
        "cost_scope": ["material", "labor"],
        "hours_scope": ["material", "labor"],
        "concepts": [
            {
                "concept_id": "material",
                "kind": "material",
                "driver": "area",
                "cost": 200,
                "hours": 2,
                "material": material,
            },
            {
                "concept_id": "assembly",
                "kind": "labor",
                "driver": "item",
                "cost": 100,
                "hours": 8,
            },
        ],
    }


def _target(**updates) -> HistoricalTarget:
    values = {
        "family": "rectangular_table",
        "width_mm": 1200,
        "depth_mm": 500,
        "height_mm": 750,
        "area_mm2": 3_000_000,
        "quantity": 3,
        "material": "oak veneer",
        "finish": "clear lacquer",
        "currency": "EUR",
        "basis_revision": "run-7:r3",
        "required_cost_scope": ("material", "labor"),
        "required_hours_scope": ("material", "labor"),
    }
    values.update(updates)
    return HistoricalTarget(**values)


def _published_item_hours_record(
    record_id: str = "published-hours",
    *,
    driver: str = "item",
) -> dict:
    return {
        "record_id": record_id,
        "project_id": record_id,
        "revision": "published-2026-09-20",
        "family": "living room furniture",
        "quantity": 1,
        "manufacturing_hours": 1.94,
        "origin": "published",
        "provenance": {
            "source": "https://doi.org/10.3390/su18189636; Table 3 / Table A6",
            "source_date": "2026-09-20",
            "notes": "Published per-unit production-time coefficient; not labor or ERP actual.",
        },
        "concepts": [
            {
                "concept_id": "production_time",
                "kind": "production_time",
                "driver": driver,
                "hours": 1.94,
            }
        ],
        "included_scope": ["production_time"],
        "cost_scope": [],
        "hours_scope": ["production_time"],
    }


def _unknown_provisional_dimension() -> ProvisionalDimension:
    return ProvisionalDimension(
        value_mm=None,
        state="unknown",
        review_status="abstained",
    )


def _provisional_snapshot(*, rows=None) -> ProvisionalScenarioSnapshot:
    def accepted_dimension(value, name):
        return ProvisionalDimension(
            value_mm=value,
            state="hypothesis",
            review_status="accepted",
            check_ids=(f"{name}-check",),
            dependency_refs=(f"binding:{name}",),
        )

    default_row = ProvisionalScenarioRow(
        component_id="panel-1",
        occurrence_status="provisional",
        scenario_occurrence_ids=("occ-1", "occ-2", "occ-3"),
        quantity=ProvisionalQuantity(
            value=3,
            state="hypothesis",
            review_status="accepted",
            check_ids=("quantity-check", "duplicate-check"),
            check_kinds=("quantity_basis", "duplicate_scan"),
            premise_refs=("premise:three-panels",),
            source_refs=("visual:page-1",),
        ),
        length=accepted_dimension(1000, "length"),
        width=accepted_dimension(1000, "width"),
        thickness=accepted_dimension(20, "thickness"),
        material=ProvisionalText(
            value="oak veneer",
            state="hypothesis",
            review_status="accepted",
            check_ids=("material-check",),
            dependency_refs=("premise:oak",),
        ),
        finish=ProvisionalText(
            value="clear lacquer",
            state="hypothesis",
            review_status="accepted",
            check_ids=("finish-check",),
            dependency_refs=("premise:clear",),
        ),
        source_refs=("visual:page-1", "dimension:length", "dimension:width"),
    )
    return ProvisionalScenarioSnapshot(
        run_id="run-7",
        proposal_revision=2,
        review_revision=1,
        auto_review_status="accepted",
        rows=tuple(rows or (default_row,)),
    )


def test_import_requires_real_provenance_and_rejects_inconsistent_totals() -> None:
    missing_source = _record()
    missing_source["provenance"] = {"source": " ", "source_date": "2026-10-31"}
    with pytest.raises(ValidationError, match="source"):
        HistoricalImport(records=(missing_source,))

    inconsistent = _record()
    inconsistent["actual_cost"] = 999
    with pytest.raises(ValidationError, match="concept costs"):
        HistoricalImport(records=(inconsistent,))

    quote = _record("quote-1")
    quote["cost_basis"] = "quote"
    parsed = HistoricalImport(records=(quote,)).records[0]
    assert parsed.cost_basis == "quote"
    assert parsed.origin == "actual"


def test_record_preserves_component_summary_and_included_scope() -> None:
    row = _record()
    row["included_scope"] = ["material", "labor"]
    row["components"] = [
        {
            "component_id": "top",
            "kind": "panel",
            "quantity": 1,
            "length_mm": 1000,
            "width_mm": 500,
            "area_mm2": 500000,
            "material": "oak veneer",
            "finish": "clear lacquer",
        }
    ]

    parsed = HistoricalImport(records=(row,)).records[0]

    assert parsed.included_scope == ("material", "labor")
    assert parsed.components[0].component_id == "top"


def test_json_import_is_idempotent_and_persists_across_store_instances(tmp_path) -> None:
    db = tmp_path / "history.sqlite3"
    store = HistoricalStore(db)
    payload = HistoricalImport(records=(_record(),))

    first = store.import_records(payload, dry_run=False)
    second = store.import_records(payload, dry_run=False)

    assert (first.accepted, first.unchanged, first.rejected) == (1, 0, 0)
    assert (second.accepted, second.unchanged, second.rejected) == (0, 1, 0)
    reopened = HistoricalStore(db)
    page = reopened.list_records(limit=10, offset=0)
    assert page.total == 1
    assert page.items[0].provenance.source == "ERP work order WO-42"
    assert page.items[0].origin == "actual"


def test_store_quota_rejects_new_records_without_overwriting_existing(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3", max_records=1)

    result = store.import_records(
        HistoricalImport(
            records=(
                _record("first"),
                _record("second", project_id="p2"),
            )
        ),
        dry_run=False,
    )

    assert (result.accepted, result.rejected) == (1, 1)
    assert result.errors[0].error == "history_capacity_exceeded"
    assert store.list_records(limit=10, offset=0).total == 1


def test_csv_import_validates_rows_independently_and_never_promotes_demo(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    csv_text = "\n".join(
        (
            "record_id,project_id,revision,family,width_mm,depth_mm,height_mm,area_mm2,quantity,material,finish,currency,actual_cost,cost_basis,manufacturing_hours,included_scope,cost_scope,hours_scope,origin,source,source_date",
            "real-1,p1,r1,table,1000,500,750,2000000,2,oak,clear,EUR,300,actual,10,material|labor,material|labor,material|labor,actual,ERP WO-1,2026-10-31",
            "demo-1,p2,r1,table,1000,500,750,2000000,2,oak,clear,EUR,300,budget,10,material|labor,material|labor,material|labor,synthetic,demo fixture,2026-10-31",
            "bad,p3,r1,table,-1,500,750,2000000,2,oak,clear,EUR,300,actual,10,material|labor,material|labor,material|labor,actual,ERP WO-3,2026-10-31",
        )
    )

    result = store.import_csv(csv_text, dry_run=False)

    assert (result.accepted, result.rejected) == (2, 1)
    assert result.errors[0].row == 4
    assert store.list_records(origin="actual", limit=10, offset=0).total == 1
    assert store.list_records(origin="synthetic", limit=10, offset=0).items[0].origin == "synthetic"
    mismatch = store.estimate(
        _target(material="steel", finish="painted"),
        comparable_ids=("real-1",),
    )
    assert mismatch.cost_subtotal is None
    assert mismatch.manufacturing_hours is None
    assert set(mismatch.missing_data) >= {
        "material_rate_or_compatible_history",
        "finish_rate_or_compatible_history",
    }


def test_attribute_retrieval_excludes_same_project_and_synthetic_by_default(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    records = (
        _record("same-project", project_id="target-project"),
        _record("actual-close", project_id="other-project"),
        _record("published-source", project_id="published", origin="published"),
        _record("demo-perfect", project_id="demo", origin="synthetic"),
        _record("material-mismatch", project_id="third", material="steel"),
    )
    store.import_records(HistoricalImport(records=records), dry_run=False)

    response = store.find_comparables(
        _target(exclude_project_id="target-project"), limit=5
    )

    assert response.retrieval_method == "attribute"
    assert [item.record.record_id for item in response.items] == [
        "actual-close",
        "published-source",
        "material-mismatch",
    ]
    assert response.items[0].score > response.items[2].score
    assert any("material" in value for value in response.items[2].differences)
    assert {item.record.origin for item in response.items} == {"actual", "published"}


def test_retrieval_deduplicates_project_revisions_to_latest_source_date(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    older = _record("old", project_id="same", revision="r9")
    newer = _record("new", project_id="same", revision="r2")
    newer["provenance"]["source_date"] = "2026-11-01"
    other = _record("other", project_id="other")
    store.import_records(HistoricalImport(records=(older, newer, other)), dry_run=False)

    response = store.find_comparables(_target(), limit=10)

    assert {item.record.record_id for item in response.items} == {"new", "other"}


def test_explicit_estimate_rejects_self_project_and_excluded_record_ids(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    store.import_records(HistoricalImport(records=(_record(),)), dry_run=False)

    with pytest.raises(ValueError, match="excluded_historical_record"):
        store.estimate(
            _target(exclude_project_id="project-001"),
            comparable_ids=("job-001",),
        )
    with pytest.raises(ValueError, match="excluded_historical_record"):
        store.estimate(
            _target(exclude_record_ids=("job-001",)),
            comparable_ids=("job-001",),
        )


def test_cost_and_hours_scale_by_declared_drivers_with_explicit_formula(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    store.import_records(HistoricalImport(records=(_record(),)), dry_run=False)

    estimate = store.estimate(_target(), comparable_ids=("job-001",))

    by_id = {item.concept_id: item for item in estimate.contributors}
    assert by_id["material"].quantity_factor == 1.5
    assert by_id["material"].consumption_factor == 1.0
    assert by_id["material"].unit_rate_factor == 1.0
    assert by_id["material"].estimated_cost == 300
    assert by_id["material"].estimated_hours == 3
    assert by_id["assembly"].estimated_cost == 150
    assert by_id["assembly"].estimated_hours == 12
    assert estimate.cost_subtotal == 450
    assert estimate.manufacturing_hours == 15
    assert estimate.currency == "EUR"
    assert estimate.basis_revision == "run-7:r3"
    assert estimate.result_provenance[0].source == "ERP work order WO-42"
    assert estimate.result_provenance[0].cost_basis == "actual"
    assert "target_area_per_item" in by_id["material"].formula


def test_incompatible_currency_and_finish_abstain_instead_of_inventing(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    store.import_records(HistoricalImport(records=(_record(),)), dry_run=False)

    currency = store.estimate(
        _target(currency="USD"), comparable_ids=("job-001",)
    )
    finish = store.estimate(
        _target(finish="painted"), comparable_ids=("job-001",)
    )

    assert currency.cost_subtotal is None
    assert "currency_compatible_comparable" in currency.missing_data
    assert finish.cost_subtotal == 450
    assert "finish_rate_or_compatible_history" not in finish.missing_data
    assert next(item for item in finish.contributors if item.kind == "material").estimated_cost == 300
    assert next(item for item in finish.contributors if item.kind == "labor").estimated_cost == 150


def test_cost_and_hours_completeness_are_orthogonal(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    row = _record(cost=100, hours=5)
    row["concepts"] = [
        {"concept_id": "material", "kind": "material", "driver": "item", "cost": 100, "material": "oak veneer"},
        {"concept_id": "labor", "kind": "labor", "driver": "item", "hours": 5},
    ]
    row["cost_scope"] = ["material"]
    row["hours_scope"] = ["labor"]
    store.import_records(HistoricalImport(records=(row,)), dry_run=False)

    estimate = store.estimate(
        _target(
            quantity=4,
            required_cost_scope=("material",),
            required_hours_scope=("labor",),
        ),
        comparable_ids=("job-001",),
    )

    assert estimate.cost_subtotal == 200
    assert estimate.manufacturing_hours == 10


def test_concept_specific_compatibility_preserves_fixed_and_labor(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    row = _record(cost=350, hours=11)
    row["concepts"] = [
        {"concept_id": "material", "kind": "material", "driver": "area", "cost": 200, "hours": 2, "material": "walnut"},
        {"concept_id": "labor", "kind": "labor", "driver": "item", "cost": 100, "hours": 8},
        {"concept_id": "setup", "kind": "fixed", "driver": "fixed", "cost": 50, "hours": 1},
    ]
    row["included_scope"] = ["material", "labor", "fixed"]
    row["cost_scope"] = ["material", "labor", "fixed"]
    row["hours_scope"] = ["material", "labor", "fixed"]
    store.import_records(HistoricalImport(records=(row,)), dry_run=False)

    estimate = store.estimate(
        _target(
            required_cost_scope=("material", "labor", "fixed"),
            required_hours_scope=("material", "labor", "fixed"),
        ),
        comparable_ids=("job-001",),
    )
    by_id = {item.concept_id: item for item in estimate.contributors}

    assert by_id["material"].estimated_cost is None
    assert by_id["labor"].estimated_cost == 150
    assert by_id["setup"].estimated_cost == 50
    assert estimate.cost_subtotal is None
    assert estimate.manufacturing_hours is None


def test_global_analogy_requires_record_material_and_finish_compatibility(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    row = _record()
    row["concepts"] = []
    store.import_records(HistoricalImport(records=(row,)), dry_run=False)

    estimate = store.estimate(
        _target(material="steel", finish="painted"),
        comparable_ids=("job-001",),
    )

    assert estimate.cost_subtotal is None
    assert estimate.manufacturing_hours is None
    assert "material_rate_or_compatible_history" in estimate.missing_data
    assert "finish_rate_or_compatible_history" in estimate.missing_data
    assert estimate.contributors[0].estimated_cost is None
    assert estimate.contributors[0].estimated_hours is None


def test_length_and_volume_drivers_scale_declared_consumption(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    row = _record(cost=300, hours=10)
    row.update({"length_mm": 4000, "volume_mm3": 20_000_000})
    row["concepts"] = [
        {"concept_id": "edge", "kind": "finish", "driver": "length", "cost": 100, "hours": 2, "finish": "clear lacquer"},
        {"concept_id": "solid", "kind": "material", "driver": "volume", "cost": 200, "hours": 8, "material": "oak veneer"},
    ]
    row["included_scope"] = ["material", "finish"]
    row["cost_scope"] = ["material", "finish"]
    row["hours_scope"] = ["material", "finish"]
    store.import_records(HistoricalImport(records=(row,)), dry_run=False)

    estimate = store.estimate(
        _target(
            length_mm=8000,
            volume_mm3=40_000_000,
            required_cost_scope=("material", "finish"),
            required_hours_scope=("material", "finish"),
        ),
        comparable_ids=("job-001",),
    )
    by_id = {item.concept_id: item for item in estimate.contributors}

    assert by_id["edge"].estimated_cost == 200
    assert by_id["solid"].estimated_cost == 400


def test_total_consumption_scales_without_inventing_finished_item_quantity(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    store.import_records(HistoricalImport(records=(_record(),)), dry_run=False)

    estimate = store.estimate(
        _target(quantity=None, area_mm2=3_000_000),
        comparable_ids=("job-001",),
    )
    material = next(item for item in estimate.contributors if item.kind == "material")
    labor = next(item for item in estimate.contributors if item.kind == "labor")

    assert material.estimated_cost == 300
    assert material.formula == "base * target_total_area / historical_total_area"
    assert labor.estimated_cost is None
    assert "quantity_for_scaling" in labor.missing_data


def test_fixed_cost_is_not_scaled_and_comparables_are_weighted_not_summed(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    first = _record("a", cost=350, hours=11)
    first["concepts"].append(
        {"concept_id": "setup", "kind": "fixed", "driver": "fixed", "cost": 50, "hours": 1}
    )
    first["included_scope"] = ["material", "labor", "fixed"]
    first["cost_scope"] = ["material", "labor", "fixed"]
    first["hours_scope"] = ["material", "labor", "fixed"]
    second = _record("b", project_id="p2", cost=450, hours=13)
    second["concepts"][0]["cost"] = 300
    second["concepts"][0]["hours"] = 3
    second["concepts"].append(
        {"concept_id": "setup", "kind": "fixed", "driver": "fixed", "cost": 50, "hours": 2}
    )
    second["included_scope"] = ["material", "labor", "fixed"]
    second["cost_scope"] = ["material", "labor", "fixed"]
    second["hours_scope"] = ["material", "labor", "fixed"]
    store.import_records(HistoricalImport(records=(first, second)), dry_run=False)

    estimate = store.estimate(
        _target(
            required_cost_scope=("material", "labor", "fixed"),
            required_hours_scope=("material", "labor", "fixed"),
        ),
        comparable_ids=("a", "b"),
    )
    setup = next(item for item in estimate.contributors if item.concept_id == "setup")

    assert setup.quantity_factor == 1
    assert setup.consumption_factor == 1
    assert setup.estimated_cost == 50
    assert estimate.cost_subtotal < 800  # alternatives are averaged, never added together


def test_different_concept_ids_in_alternative_records_do_not_double_count(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    first = _record("a")
    first["concepts"][0]["concept_id"] = "material-m1"
    second = _record("b", project_id="p2", cost=320)
    second["concepts"][0].update({"concept_id": "material-m2", "cost": 220})
    store.import_records(HistoricalImport(records=(first, second)), dry_run=False)

    estimate = store.estimate(_target(), comparable_ids=("a", "b"))

    assert len(estimate.scenarios) == 2
    assert estimate.scenarios[0].cost_total == 450
    assert estimate.scenarios[1].cost_total == 480
    assert 450 <= estimate.cost_subtotal <= 480
    assert estimate.cost_range == (450, 480)


def test_different_economic_scopes_are_not_averaged_without_target_scope(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    full = _record("full")
    material_only = _record("material-only", project_id="p2", cost=200, hours=2)
    material_only["concepts"] = [
        {
            "concept_id": "material",
            "kind": "material",
            "driver": "area",
            "cost": 200,
            "hours": 2,
            "material": "oak veneer",
        }
    ]
    material_only["included_scope"] = ["material"]
    material_only["cost_scope"] = ["material"]
    material_only["hours_scope"] = ["material"]
    store.import_records(
        HistoricalImport(records=(full, material_only)), dry_run=False
    )

    estimate = store.estimate(
        _target(required_cost_scope=(), required_hours_scope=()),
        comparable_ids=("full", "material-only")
    )

    assert estimate.cost_subtotal is None
    assert estimate.manufacturing_hours is None
    assert "required_cost_scope" in estimate.missing_data
    assert "required_hours_scope" in estimate.missing_data
    assert len(estimate.scenarios) == 2
    assert estimate.cost_range is None
    assert estimate.hours_range is None
    assert all(item.estimated_cost is None for item in estimate.contributors)
    assert all(item.estimated_hours is None for item in estimate.contributors)
    assert all(item.cost_total is None for item in estimate.scenarios)
    assert all(item.hours_total is None for item in estimate.scenarios)


def test_explicit_comparable_must_cover_requested_cost_and_hours_scope(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    material_only = _record("material-only", cost=200, hours=2)
    material_only["concepts"] = [
        {
            "concept_id": "material",
            "kind": "material",
            "driver": "area",
            "cost": 200,
            "hours": 2,
            "material": "oak veneer",
        }
    ]
    material_only["included_scope"] = ["material"]
    material_only["cost_scope"] = ["material"]
    material_only["hours_scope"] = ["material"]
    store.import_records(HistoricalImport(records=(material_only,)), dry_run=False)

    with pytest.raises(ValueError, match="incompatible_historical_scope"):
        store.estimate(
            _target(
                required_cost_scope=("material", "labor"),
                required_hours_scope=("material", "labor"),
            ),
            comparable_ids=("material-only",),
        )


def test_automatic_retrieval_filters_better_scoring_incompatible_scope(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    incompatible = _record("incompatible")
    incompatible["concepts"] = [
        {
            "concept_id": "material",
            "kind": "material",
            "driver": "area",
            "cost": 300,
            "hours": 10,
            "material": "oak veneer",
        }
    ]
    incompatible["actual_cost"] = 300
    incompatible["manufacturing_hours"] = 10
    incompatible["included_scope"] = ["material"]
    incompatible["cost_scope"] = ["material"]
    incompatible["hours_scope"] = ["material"]
    compatible = _record("compatible", project_id="p2")
    compatible["width_mm"] = 900
    store.import_records(
        HistoricalImport(records=(incompatible, compatible)), dry_run=False
    )

    target = _target()
    response = store.find_comparables(target, limit=5)
    estimate = store.estimate(target)

    assert [item.record.record_id for item in response.items] == ["compatible"]
    assert estimate.comparable_ids == ("compatible",)
    assert estimate.cost_subtotal is not None
    assert estimate.manufacturing_hours is not None


def test_cost_only_and_hours_only_records_combine_by_metric_scope(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    cost_only = _record("cost-only", cost=300, hours=10)
    cost_only["manufacturing_hours"] = None
    cost_only["hours_scope"] = []
    for concept in cost_only["concepts"]:
        concept["hours"] = None
    hours_only = _record("hours-only", project_id="p2", cost=300, hours=10)
    hours_only["actual_cost"] = None
    hours_only["cost_basis"] = None
    hours_only["cost_scope"] = []
    for concept in hours_only["concepts"]:
        concept["cost"] = None
    store.import_records(
        HistoricalImport(records=(cost_only, hours_only)), dry_run=False
    )

    response = store.find_comparables(_target(), limit=5)
    estimate = store.estimate(_target())

    assert {item.record.record_id for item in response.items} == {
        "cost-only",
        "hours-only",
    }
    assert estimate.cost_subtotal is not None
    assert estimate.manufacturing_hours is not None
    scenarios = {item.record_id: item for item in estimate.scenarios}
    assert scenarios["cost-only"].cost_total is not None
    assert scenarios["cost-only"].hours_total is None
    assert scenarios["hours-only"].cost_total is None
    assert scenarios["hours-only"].hours_total is not None
    provenance = {item.record_id: item for item in estimate.result_provenance}
    assert provenance["cost-only"].contributes_cost is True
    assert provenance["cost-only"].contributes_hours is False
    assert provenance["hours-only"].contributes_cost is False
    assert provenance["hours-only"].contributes_hours is True
    assert provenance["cost-only"].cost_scope == ("material", "labor")
    assert provenance["hours-only"].hours_scope == ("material", "labor")
    assert estimate.cost_uncertainty == "medium"
    assert estimate.hours_uncertainty == "medium"


def test_non_finite_numbers_are_rejected() -> None:
    row = _record()
    row["actual_cost"] = float("inf")
    with pytest.raises(ValidationError, match="finite"):
        HistoricalImport(records=(row,))


class _FakeEmbeddings:
    model = "test-embedding"
    dimensions = 2

    def embed(self, text: str) -> EmbeddingResult:
        self.calls = getattr(self, "calls", 0) + 1
        vector = [1.0, 0.0] if "oak veneer" in text else [0.0, 1.0]
        return EmbeddingResult(vector=tuple(vector), model=self.model, dimensions=2)


def test_history_cache_separates_model_revisions(tmp_path) -> None:
    class RevisionEmbeddings(_FakeEmbeddings):
        model = "google/embeddinggemma-2"
        dimensions = 768

        def __init__(self, revision: str) -> None:
            self.identity = EmbeddingSpaceIdentity.embeddinggemma2_text(revision)

        def embed(self, text: str) -> EmbeddingResult:
            return EmbeddingResult(
                vector=tuple([1.0] + [0.0] * 767),
                model=self.model,
                dimensions=self.dimensions,
            )

    db = tmp_path / "history.sqlite3"
    first = HistoricalStore(db, embedding_provider=RevisionEmbeddings("revision-a"))
    first.import_records(HistoricalImport(records=(_record(),)), dry_run=False)
    first.find_comparables(_target(), limit=1, retrieval_method="semantic")
    second = HistoricalStore(db, embedding_provider=RevisionEmbeddings("revision-b"))
    second.find_comparables(_target(), limit=1, retrieval_method="semantic")

    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            "SELECT space_id FROM historical_embeddings ORDER BY space_id"
        ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] != rows[1][0]


def test_history_reports_complete_embedding_space_identity(tmp_path) -> None:
    class RevisionEmbeddings(_FakeEmbeddings):
        model = "google/embeddinggemma-2"
        dimensions = 768
        identity = EmbeddingSpaceIdentity.embeddinggemma2_text("revision-a")

        def embed(self, text: str) -> EmbeddingResult:
            return EmbeddingResult(vector=tuple([1.0] + [0.0] * 767), model=self.model, dimensions=768)

    store = HistoricalStore(tmp_path / "history.sqlite3", embedding_provider=RevisionEmbeddings())
    store.import_records(HistoricalImport(records=(_record(),)), dry_run=False)
    response = store.find_comparables(_target(), limit=1, retrieval_method="semantic")

    assert response.embedding_space.model_dump() == {
        "provider": "embeddinggemma2",
        "model": "google/embeddinggemma-2",
        "model_revision": "revision-a",
        "modality": "text",
        "dimensions": 768,
        "normalization": "l2",
        "preprocessing_version": EMBEDDINGGEMMA2_TEXT_PREPROCESSING,
    }


def test_semantic_retrieval_is_explicit_and_reports_embedding_space(tmp_path) -> None:
    provider = _FakeEmbeddings()
    store = HistoricalStore(tmp_path / "history.sqlite3", embedding_provider=provider)
    store.import_records(
        HistoricalImport(
            records=(
                _record("oak", material="oak veneer"),
                _record("steel", project_id="p2", material="steel"),
            )
        ),
        dry_run=False,
    )

    response = store.find_comparables(
        _target(), limit=2, retrieval_method="semantic"
    )

    assert response.retrieval_method == "semantic"
    assert response.embedding_space.model == "test-embedding"
    assert [item.record.record_id for item in response.items] == ["oak", "steel"]
    assert response.items[0].score == 1.0

    store.find_comparables(_target(), limit=2, retrieval_method="semantic")
    # Two query embeddings plus one cached embedding for each historical record.
    assert provider.calls == 4


def test_corrupt_persisted_embedding_is_recomputed_not_trusted(tmp_path) -> None:
    db = tmp_path / "history.sqlite3"
    provider = _FakeEmbeddings()
    store = HistoricalStore(db, embedding_provider=provider)
    store.import_records(HistoricalImport(records=(_record(),)), dry_run=False)
    store.find_comparables(_target(), limit=1, retrieval_method="semantic")
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE historical_embeddings SET vector=?", ('[1,"not-a-number"]',)
        )

    response = store.find_comparables(_target(), limit=1, retrieval_method="semantic")

    assert response.items[0].score == 1
    assert provider.calls == 4  # target twice, record once plus cache repair


def test_router_supports_json_csv_list_comparables_and_estimate(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    app = FastAPI()
    app.include_router(create_history_router(store))
    client = TestClient(app)

    imported = client.post(
        "/api/v1/history/import/json",
        json={"records": [_record()]},
    )
    listed = client.get("/api/v1/history/records")
    compared = client.post(
        "/api/v1/history/comparables",
        json={"target": _target().model_dump(mode="json"), "limit": 3},
    )
    estimated = client.post(
        "/api/v1/history/estimate",
        json={
            "target": _target().model_dump(mode="json"),
            "comparable_ids": ["job-001"],
        },
    )
    csv_imported = client.post(
        "/api/v1/history/import/csv?dry_run=true",
        files={"file": ("history.csv", "record_id,project_id\n", "text/csv")},
    )
    excluded = client.post(
        "/api/v1/history/estimate",
        json={
            "target": _target(
                exclude_record_ids=("job-001",)
            ).model_dump(mode="json"),
            "comparable_ids": ["job-001"],
        },
    )
    incompatible_scope = client.post(
        "/api/v1/history/estimate",
        json={
            "target": _target(
                required_cost_scope=("material", "labor", "finish")
            ).model_dump(mode="json"),
            "comparable_ids": ["job-001"],
        },
    )

    assert imported.status_code == 200 and imported.json()["data"]["accepted"] == 1
    assert imported.json()["schema_version"] == "1.0.0"
    assert listed.status_code == 200 and listed.json()["data"]["total"] == 1
    assert compared.status_code == 200 and compared.json()["data"]["items"][0]["record"]["record_id"] == "job-001"
    assert estimated.status_code == 200 and estimated.json()["data"]["cost_subtotal"] == 450
    assert csv_imported.status_code == 200 and csv_imported.json()["data"]["dry_run"] is True
    assert excluded.status_code == 422
    assert excluded.json()["error"]["code"] == "excluded_historical_record:job-001"
    assert incompatible_scope.status_code == 422
    assert incompatible_scope.json()["error"]["code"] == "incompatible_historical_scope:job-001:cost"


def test_router_actor_is_authoritative_and_frontend_aliases_are_available(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    app = FastAPI()

    class ActorMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.actor = "authenticated-user"
            return await call_next(request)

    app.add_middleware(ActorMiddleware)
    app.include_router(create_history_router(store))
    client = TestClient(app)
    row = _record()
    row["provenance"]["imported_by"] = "client-claim"

    imported = client.post("/api/v1/history/import/json", json={"records": [row]})
    listed = client.get("/api/v1/history")
    alias_import = client.post(
        "/api/v1/history/imports?dry_run=true",
        files={"file": ("history.csv", "record_id,project_id\n", "text/csv")},
    )

    assert imported.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["data"]["items"][0]["provenance"]["imported_by"] == "authenticated-user"
    assert alias_import.status_code == 200


def test_csv_upload_is_bounded_before_decoding(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    app = FastAPI()
    app.include_router(create_history_router(store, max_csv_bytes=32))
    client = TestClient(app)

    response = client.post(
        "/api/v1/history/imports",
        files={"file": ("history.csv", "x" * 33, "text/csv")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "history_import_too_large"


def test_store_calls_release_sqlite_handles(tmp_path) -> None:
    folder = tmp_path / "removable"
    store = HistoricalStore(folder / "history.sqlite3")
    store.import_records(HistoricalImport(records=(_record(),)), dry_run=False)
    store.list_records(limit=10, offset=0)
    store.find_comparables(_target(), limit=1)
    store.estimate(_target(), comparable_ids=("job-001",))

    shutil.rmtree(folder)

    assert not folder.exists()


def test_import_rejects_unknown_json_fields() -> None:
    row = _record()
    row["unreviewed_guess"] = 42
    with pytest.raises(ValidationError, match="Extra inputs"):
        HistoricalImport.model_validate_json(json.dumps({"records": [row]}))


def test_http_actual_and_synthetic_import_estimate_and_restart_persistence(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("VEXPLORER_ENV", "local")
    data_dir = tmp_path / "data"
    client = TestClient(create_app(data_dir=data_dir, frontend_dir=tmp_path / "none"))
    actual = _record()
    synthetic = _record("demo", project_id="demo", origin="synthetic")

    assert client.post(
        "/api/v1/history/import/json", json={"records": [actual, synthetic]}
    ).status_code == 200
    compared = client.post(
        "/api/v1/history/comparables",
        json={"target": _target().model_dump(mode="json"), "limit": 5},
    )
    estimated = client.post(
        "/api/v1/history/estimate",
        json={
            "target": _target().model_dump(mode="json"),
            "comparable_ids": ["job-001"],
        },
    )

    assert compared.status_code == 200
    assert [item["record"]["record_id"] for item in compared.json()["data"]["items"]] == ["job-001"]
    assert estimated.status_code == 200
    assert estimated.json()["data"]["cost_subtotal"] == 450
    assert estimated.json()["data"]["manufacturing_hours"] == 15

    restarted = TestClient(
        create_app(data_dir=data_dir, frontend_dir=tmp_path / "none")
    )
    listed = restarted.get("/api/v1/history")
    assert listed.status_code == 200
    assert {item["origin"] for item in listed.json()["data"]["items"]} == {
        "actual",
        "synthetic",
    }


def test_provisional_scenarios_keep_each_comparable_conditional_and_separate(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    eur = _record("eur-reference")
    usd = _record("usd-reference", project_id="usd-project")
    usd["currency"] = "USD"
    synthetic = _record("synthetic", project_id="synthetic-project", origin="synthetic")
    store.import_records(
        HistoricalImport(records=(eur, usd, synthetic)), dry_run=False
    )

    response = store.provisional_scenarios(
        _provisional_snapshot(), limit=3, retrieval_method="attribute"
    )

    assert response.status == "provisional"
    assert len(response.scenarios) == 2
    assert {item.comparable_id for item in response.scenarios} == {
        "eur-reference",
        "usd-reference",
    }
    assert {item.currency for item in response.scenarios} == {"EUR", "USD"}
    assert all(item.label == "conditional_provisional_not_quote" for item in response.scenarios)
    assert all(item.condition.furniture_quantity == 1 for item in response.scenarios)
    assert all(item.condition.family == "rectangular_table" for item in response.scenarios)
    assert all(item.condition.material == "oak veneer" for item in response.scenarios)
    assert all(item.condition.finish == "clear lacquer" for item in response.scenarios)
    assert all(item.cost_subtotal is not None for item in response.scenarios)
    assert all(item.manufacturing_hours is not None for item in response.scenarios)
    assert all(item.cost_range is None for item in response.scenarios)
    assert all(item.hours_range is None for item in response.scenarios)
    assert all(item.scaling_basis.area_mm2 == 3_000_000 for item in response.scenarios)
    assert all(len(item.result_provenance) == 1 for item in response.scenarios)
    assert all(item.result_provenance[0].contributes_cost for item in response.scenarios)
    assert all(item.result_provenance[0].contributes_hours for item in response.scenarios)
    assert all(
        {assumption.code for assumption in item.assumptions}
        >= {"one_finished_item", "reference_family"}
        for item in response.scenarios
    )
    assert {item.result_provenance[0].origin for item in response.scenarios} == {"actual"}
    assert {item.result_provenance[0].cost_basis for item in response.scenarios} == {"actual"}
    assert {item.source_effective_date.isoformat() for item in response.scenarios} == {
        "2026-10-31"
    }


@pytest.mark.parametrize("driver", ("item", "fixed"))
def test_provisional_scenarios_allow_published_hours_without_geometry_or_material(
    tmp_path, driver
) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    store.import_records(
        HistoricalImport(records=(_published_item_hours_record(driver=driver),)),
        dry_run=False,
    )
    base = _provisional_snapshot().rows[0]
    unknown_text = ProvisionalText(
        value=None, state="unknown", review_status="abstained"
    )
    row = base.model_copy(
        update={
            "length": _unknown_provisional_dimension(),
            "width": _unknown_provisional_dimension(),
            "thickness": _unknown_provisional_dimension(),
            "material": unknown_text,
            "finish": unknown_text,
        }
    )

    response = store.provisional_scenarios(
        _provisional_snapshot(rows=(row,)), limit=3, retrieval_method="attribute"
    )

    assert response.status == "provisional"
    assert len(response.scenarios) == 1
    scenario = response.scenarios[0]
    assert scenario.condition.family == "living room furniture"
    assert scenario.condition.material is None
    assert scenario.condition.finish is None
    assert scenario.condition.currency is None
    assert scenario.condition.cost_scope == ()
    assert scenario.condition.hours_scope == ("production_time",)
    assert scenario.scaling_basis.length_mm is None
    assert scenario.scaling_basis.area_mm2 is None
    assert scenario.scaling_basis.volume_mm3 is None
    assert scenario.cost_subtotal is None
    assert scenario.cost_range is None
    assert scenario.manufacturing_hours == 1.94
    assert scenario.hours_range is None
    assert scenario.hours_uncertainty in {"medium", "high"}
    assert "required_cost_scope" not in scenario.missing_data
    assert {item.code for item in scenario.assumptions} >= {
        "reference_material_unreported",
        "reference_finish_unreported",
    }
    provenance = scenario.result_provenance[0]
    assert provenance.origin == "published"
    assert provenance.source_date.isoformat() == "2026-09-20"
    assert provenance.cost_basis is None
    assert provenance.contributes_cost is False
    assert provenance.contributes_hours is True
    assert provenance.hours_scope == ("production_time",)


def test_provisional_item_hours_never_sum_partial_geometry(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    store.import_records(
        HistoricalImport(records=(_published_item_hours_record(),)), dry_run=False
    )
    first = _provisional_snapshot().rows[0]
    unknown_text = ProvisionalText(
        value=None, state="unknown", review_status="abstained"
    )
    second = first.model_copy(
        update={
            "component_id": "panel-unknown",
            "scenario_occurrence_ids": ("unknown-occurrence",),
            "quantity": first.quantity.model_copy(update={"value": 1}),
            "length": _unknown_provisional_dimension(),
            "width": _unknown_provisional_dimension(),
            "thickness": _unknown_provisional_dimension(),
            "material": unknown_text,
            "finish": unknown_text,
        }
    )

    response = store.provisional_scenarios(
        _provisional_snapshot(rows=(first, second)),
        limit=3,
        retrieval_method="attribute",
    )

    scenario = response.scenarios[0]
    assert scenario.manufacturing_hours == 1.94
    assert scenario.scaling_basis.length_mm is None
    assert scenario.scaling_basis.area_mm2 is None
    assert scenario.scaling_basis.volume_mm3 is None


def test_provisional_area_hours_require_complete_accepted_area(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    area_record = _published_item_hours_record(driver="area")
    area_record["area_mm2"] = 2_000_000
    store.import_records(HistoricalImport(records=(area_record,)), dry_run=False)
    base = _provisional_snapshot().rows[0]
    row = base.model_copy(
        update={
            "length": _unknown_provisional_dimension(),
            "width": _unknown_provisional_dimension(),
            "thickness": _unknown_provisional_dimension(),
        }
    )

    response = store.provisional_scenarios(
        _provisional_snapshot(rows=(row,)), limit=3, retrieval_method="attribute"
    )

    assert response.status == "not_estimable"
    assert response.scenarios == ()
    assert "compatible_non_synthetic_reference" in response.missing_data


def test_known_material_conflict_blocks_cost_but_not_unconstrained_production_time(
    tmp_path,
) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    steel = _record("steel-cost", material="steel")
    hours = _published_item_hours_record()
    store.import_records(HistoricalImport(records=(steel, hours)), dry_run=False)

    response = store.provisional_scenarios(
        _provisional_snapshot(), limit=3, retrieval_method="attribute"
    )

    assert [item.comparable_id for item in response.scenarios] == ["published-hours"]
    scenario = response.scenarios[0]
    assert scenario.cost_subtotal is None
    assert scenario.manufacturing_hours == 1.94
    assert scenario.condition.material is None
    assert "reference_material_unreported" in {
        item.code for item in scenario.assumptions
    }
    assert scenario.condition.hours_scope == ("production_time",)


def test_heterogeneous_bom_blocks_cost_but_allows_unconstrained_item_hours(
    tmp_path,
) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    store.import_records(
        HistoricalImport(
            records=(_record("cost-reference"), _published_item_hours_record())
        ),
        dry_run=False,
    )
    first = _provisional_snapshot().rows[0]
    second = first.model_copy(
        update={
            "component_id": "steel-panel",
            "scenario_occurrence_ids": ("steel-occurrence",),
            "quantity": first.quantity.model_copy(update={"value": 1}),
            "material": first.material.model_copy(update={"value": "steel"}),
        }
    )

    response = store.provisional_scenarios(
        _provisional_snapshot(rows=(first, second)),
        limit=3,
        retrieval_method="attribute",
    )

    assert [item.comparable_id for item in response.scenarios] == ["published-hours"]
    scenario = response.scenarios[0]
    assert scenario.cost_subtotal is None
    assert scenario.manufacturing_hours == 1.94
    assert scenario.condition.material is None


def test_provisional_candidate_limit_preserves_cost_and_hours_metrics(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    cost_records = []
    for index in range(3):
        row = _record(f"cost-{index}", project_id=f"cost-project-{index}")
        row["manufacturing_hours"] = None
        row["hours_scope"] = []
        for concept in row["concepts"]:
            concept["hours"] = None
        cost_records.append(row)
    store.import_records(
        HistoricalImport(
            records=(*cost_records, _published_item_hours_record())
        ),
        dry_run=False,
    )

    response = store.provisional_scenarios(
        _provisional_snapshot(), limit=2, retrieval_method="attribute"
    )

    assert len(response.scenarios) == 2
    assert any(item.cost_subtotal is not None for item in response.scenarios)
    assert any(
        item.condition.hours_scope == ("production_time",)
        and item.manufacturing_hours == 1.94
        for item in response.scenarios
    )


def test_nullable_reference_attributes_never_weaken_cost_eligibility(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    cost_without_context = {
        "record_id": "labor-cost-without-context",
        "project_id": "labor-cost-without-context",
        "revision": "r1",
        "family": "table",
        "quantity": 1,
        "currency": "EUR",
        "actual_cost": 100,
        "cost_basis": "actual",
        "origin": "actual",
        "provenance": {"source": "ERP WO-9", "source_date": "2026-10-31"},
        "concepts": [
            {
                "concept_id": "labor",
                "kind": "labor",
                "driver": "item",
                "cost": 100,
            }
        ],
        "included_scope": ["labor"],
        "cost_scope": ["labor"],
        "hours_scope": [],
    }
    store.import_records(
        HistoricalImport(
            records=(cost_without_context, _published_item_hours_record())
        ),
        dry_run=False,
    )

    response = store.provisional_scenarios(
        _provisional_snapshot(), limit=3, retrieval_method="attribute"
    )

    assert [item.comparable_id for item in response.scenarios] == ["published-hours"]
    assert response.scenarios[0].cost_subtotal is None
    assert response.scenarios[0].manufacturing_hours == 1.94


def test_provisional_snapshot_contract_fails_closed_on_incoherent_mapper_output() -> None:
    row = _provisional_snapshot().rows[0]
    with pytest.raises(ValidationError, match="duplicate provisional component_id"):
        ProvisionalScenarioSnapshot(
            run_id="run-7",
            proposal_revision=2,
            review_revision=1,
            auto_review_status="accepted",
            rows=(row, row),
        )
    with pytest.raises(ValidationError, match="scenario occurrence count"):
        ProvisionalScenarioRow(
            **(
                row.model_dump(mode="python")
                | {"scenario_occurrence_ids": ("only-one",)}
            )
        )
    with pytest.raises(ValidationError, match="quantity evidence"):
        ProvisionalQuantity(
            value=2,
            state="hypothesis",
            review_status="accepted",
            check_ids=("quantity",),
            check_kinds=("quantity_basis",),
            premise_refs=(),
            source_refs=(),
        )
    with pytest.raises(ValidationError, match="unknown or conflict"):
        ProvisionalText(
            value="oak",
            state="conflict",
            review_status="conflict",
        )

    repeated_kind = ProvisionalQuantity(
        value=2,
        state="hypothesis",
        review_status="accepted",
        check_ids=("quantity", "duplicate-front", "duplicate-side"),
        check_kinds=("quantity_basis", "duplicate_scan"),
        premise_refs=("premise:two",),
        source_refs=("visual:front", "visual:side"),
    )
    assert repeated_kind.value == 2


def test_provisional_scenarios_inherit_unknown_material_finish_as_visible_conditions(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    store.import_records(HistoricalImport(records=(_record(),)), dry_run=False)
    row = _provisional_snapshot().rows[0]
    unknown = row.model_copy(
        update={
            "material": ProvisionalText(
                value=None, state="unknown", review_status="abstained"
            ),
            "finish": ProvisionalText(
                value=None, state="unknown", review_status="abstained"
            ),
        }
    )

    response = store.provisional_scenarios(
        _provisional_snapshot(rows=(unknown,)), limit=3, retrieval_method="attribute"
    )

    assert len(response.scenarios) == 1
    scenario = response.scenarios[0]
    assert scenario.condition.material == "oak veneer"
    assert scenario.condition.finish == "clear lacquer"
    assert {item.code for item in scenario.assumptions} >= {
        "reference_material",
        "reference_finish",
    }


def test_provisional_scenarios_keep_cost_only_and_hours_only_sources_separate(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    cost_only = _record("cost-only")
    cost_only["manufacturing_hours"] = None
    cost_only["hours_scope"] = []
    for concept in cost_only["concepts"]:
        concept["hours"] = None
    hours_only = _record("hours-only", project_id="hours-project")
    hours_only["actual_cost"] = None
    hours_only["cost_basis"] = None
    hours_only["cost_scope"] = []
    for concept in hours_only["concepts"]:
        concept["cost"] = None
    store.import_records(
        HistoricalImport(records=(cost_only, hours_only)), dry_run=False
    )

    response = store.provisional_scenarios(
        _provisional_snapshot(), limit=3, retrieval_method="attribute"
    )

    scenarios = {item.comparable_id: item for item in response.scenarios}
    assert scenarios["cost-only"].cost_subtotal is not None
    assert scenarios["cost-only"].manufacturing_hours is None
    assert scenarios["cost-only"].result_provenance[0].contributes_cost is True
    assert scenarios["cost-only"].result_provenance[0].contributes_hours is False
    assert scenarios["hours-only"].cost_subtotal is None
    assert scenarios["hours-only"].manufacturing_hours is not None
    assert scenarios["hours-only"].result_provenance[0].contributes_cost is False
    assert scenarios["hours-only"].result_provenance[0].contributes_hours is True


@pytest.mark.parametrize("status", ("conflict", "abstained"))
def test_provisional_scenarios_reject_conflicted_or_abstained_snapshot(tmp_path, status) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    store.import_records(HistoricalImport(records=(_record(),)), dry_run=False)
    snapshot = _provisional_snapshot().model_copy(
        update={"auto_review_status": status}
    )

    response = store.provisional_scenarios(
        snapshot, limit=3, retrieval_method="attribute"
    )

    assert response.status == "not_estimable"
    assert response.scenarios == ()
    assert "auto_review_status" in response.missing_data


def test_provisional_scenarios_abstain_for_heterogeneous_material_finish(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    store.import_records(HistoricalImport(records=(_record(),)), dry_run=False)
    first = _provisional_snapshot().rows[0]
    second = first.model_copy(
        update={
            "component_id": "panel-2",
            "scenario_occurrence_ids": ("other-1",),
            "quantity": first.quantity.model_copy(update={"value": 1}),
            "material": first.material.model_copy(update={"value": "steel"}),
        }
    )

    response = store.provisional_scenarios(
        _provisional_snapshot(rows=(first, second)),
        limit=3,
        retrieval_method="attribute",
    )

    assert response.status == "not_estimable"
    assert response.scenarios == ()
    assert "heterogeneous_material_finish" in response.missing_data


def test_provisional_semantic_candidates_filter_material_before_ranking_limit(tmp_path) -> None:
    class AdversarialEmbeddings:
        model = "adversarial"
        dimensions = 2

        def embed(self, text: str) -> EmbeddingResult:
            if "scope=" not in text or "material=steel" in text:
                vector = (1.0, 0.0)
            else:
                vector = (0.0, 1.0)
            return EmbeddingResult(
                vector=vector, model=self.model, dimensions=self.dimensions
            )

    store = HistoricalStore(
        tmp_path / "history.sqlite3",
        embedding_provider=AdversarialEmbeddings(),
        semantic_candidate_limit=50,
    )
    incompatible = tuple(
        _record(
            f"steel-{index:02d}",
            project_id=f"steel-project-{index:02d}",
            material="steel",
            finish="painted",
            area_mm2=3_000_000,
            quantity=1,
        )
        | {"length_mm": 3_000, "volume_mm3": 60_000_000}
        for index in range(51)
    )
    compatible = _record("oak-compatible", project_id="oak-project")
    compatible.update(
        {
            "area_mm2": 3_000_000_000,
            "length_mm": 3_000_000,
            "volume_mm3": 60_000_000_000,
            "quantity": 1000,
        }
    )
    store.import_records(
        HistoricalImport(records=(*incompatible, compatible)), dry_run=False
    )

    response = store.provisional_scenarios(
        _provisional_snapshot(), limit=1, retrieval_method="semantic"
    )

    assert [item.comparable_id for item in response.scenarios] == ["oak-compatible"]


def test_provisional_scenarios_require_accepted_quantity_checks_and_geometry(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    store.import_records(HistoricalImport(records=(_record(),)), dry_run=False)
    row = _provisional_snapshot().rows[0]
    invalid = row.model_copy(
        update={
            "quantity": row.quantity.model_copy(
                update={"check_kinds": ("quantity_basis",)}
            )
        }
    )

    response = store.provisional_scenarios(
        _provisional_snapshot(rows=(invalid,)),
        limit=3,
        retrieval_method="attribute",
    )

    assert response.status == "not_estimable"
    assert response.scenarios == ()
    assert "provisional_quantity_evidence" in response.missing_data


def test_scenarios_route_loads_exact_server_snapshot_and_never_accepts_payload(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    store.import_records(HistoricalImport(records=(_record(),)), dry_run=False)
    calls = []

    def loader(run_id: str, proposal_revision: int, review_revision: int):
        calls.append((run_id, proposal_revision, review_revision))
        return _provisional_snapshot()

    app = FastAPI()
    app.include_router(create_history_router(store, scenario_snapshot_loader=loader))
    client = TestClient(app)

    response = client.post(
        "/api/v1/history/scenarios",
        json=ProvisionalScenarioRequest(
            run_id="run-7",
            proposal_revision=2,
            review_revision=1,
        ).model_dump(mode="json"),
    )
    forged = client.post(
        "/api/v1/history/scenarios",
        json={
            "run_id": "run-7",
            "proposal_revision": 2,
            "review_revision": 1,
            "snapshot": _provisional_snapshot().model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "provisional"
    assert calls == [("run-7", 2, 1)]
    assert forged.status_code == 422


def test_scenarios_route_reports_unavailable_loader_and_exact_revision_errors(tmp_path) -> None:
    store = HistoricalStore(tmp_path / "history.sqlite3")
    unavailable = FastAPI()
    unavailable.include_router(create_history_router(store))
    unavailable_client = TestClient(unavailable)

    missing = FastAPI()

    def missing_loader(run_id: str, proposal_revision: int, review_revision: int):
        raise KeyError(run_id)

    missing.include_router(
        create_history_router(store, scenario_snapshot_loader=missing_loader)
    )
    missing_client = TestClient(missing)
    body = {
        "run_id": "missing",
        "proposal_revision": 2,
        "review_revision": 1,
    }

    no_loader = unavailable_client.post("/api/v1/history/scenarios", json=body)
    not_found = missing_client.post("/api/v1/history/scenarios", json=body)

    assert no_loader.status_code == 503
    assert no_loader.json()["error"]["code"] == "scenario_snapshot_loader_unavailable"
    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "general_scenario_snapshot_not_found"
