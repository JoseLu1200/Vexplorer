from __future__ import annotations

import json

import pytest

from backend.app.contratos.modelos import TableCostCatalog, TableCostExclusion, TableCostScope
from backend.app.estimacion.table_costs import estimate_table_costs, get_table_cost_catalog
from backend.tests.test_table_costs import _evaluated


def _real_catalog_payload() -> dict:
    tariffs = (
        ("board-real", "Tablero", "material_area", "material", 50.005, "EUR/m2"),
        ("solid-real", "Macizo", "material_volume", "material", 1000, "EUR/m3"),
        ("edge-real", "Canto", "edge", "edge", 3, "EUR/m"),
        ("cut-real", "Mecanizado", "operation", "operation", 40, "EUR/h"),
        ("labor-real", "Mano de obra", "labor", "labor", 30, "EUR/h"),
        ("finish-real", "Acabado", "finish", "finishing", 10, "EUR/m2"),
        ("setup-real", "Preparación", "fixed", "preparation", 20, "EUR/unit"),
    )
    return {
        "schema_version": "0.6.0",
        "catalog_version": "erp-2026-11",
        "source": "Exportación ERP aprobada por compras",
        "effective_date": "2026-11-01",
        "synthetic": False,
        "tariffs": [
            {
                "id": tariff_id,
                "label": label,
                "concept_type": concept,
                "scope": scope,
                "rate_eur_per_unit": rate,
                "rate_unit": unit,
                "synthetic": False,
            }
            for tariff_id, label, concept, scope, rate, unit in tariffs
        ],
    }


def _real_scope(*, margin: float | None = 20) -> TableCostScope:
    return TableCostScope(
        material_tariff_id="board-real",
        component_material_tariff_ids={"supports": "solid-real"},
        edge_scope="all_exposed",
        edge_tariff_id="edge-real",
        operation_tariff_ids=("cut-real",),
        operation_hours_by_tariff={"cut-real": 2.5},
        labor_tariff_id="labor-real",
        labor_hours=3,
        finish_tariff_id="finish-real",
        finish_quantity_m2=1.5,
        provisional_margin_percent=margin,
    )


def test_configured_real_catalog_loads_without_demo_fallback(tmp_path, monkeypatch) -> None:
    path = tmp_path / "real-costs.json"
    path.write_text(json.dumps(_real_catalog_payload()), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(path))

    catalog = get_table_cost_catalog()

    assert catalog.catalog_version == "erp-2026-11"
    assert catalog.source == "Exportación ERP aprobada por compras"
    assert catalog.effective_date == "2026-11-01"
    assert catalog.synthetic is False
    assert {item.id for item in catalog.tariffs} == {
        "board-real", "solid-real", "edge-real", "cut-real",
        "labor-real", "finish-real", "setup-real",
    }


def test_invalid_configured_catalog_fails_instead_of_falling_back(tmp_path, monkeypatch) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"catalog_version": "broken", "tariffs": [}', encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(path))

    with pytest.raises(ValueError, match="invalid cost catalog"):
        get_table_cost_catalog()


def test_complete_real_estimate_has_snapshot_hours_margin_and_cost_contributor() -> None:
    catalog = TableCostCatalog.model_validate(_real_catalog_payload())

    estimate = estimate_table_costs(
        _evaluated(),
        result_revision=3,
        scope=_real_scope(),
        catalog=catalog,
    )

    assert estimate.catalog_snapshot == catalog
    assert estimate.synthetic is False
    assert estimate.total_state == "complete"
    assert estimate.known_subtotal_eur == 355.92
    assert estimate.grand_total_eur == 355.92
    assert estimate.total_hours == 5.5
    assert estimate.principal_cost_contributor_id == "operation:cut-real"
    assert estimate.provisional_margin_percent == 20
    assert estimate.provisional_sale_price_eur == 444.90
    by_id = {item.id: item for item in estimate.concepts}
    assert by_id["material:top"].tariff_id == "board-real"
    assert by_id["material:supports"].tariff_id == "solid-real"
    assert by_id["operation:cut-real"].tariff_id == "cut-real"


def test_estimate_identity_is_reproducible_and_changes_with_scope() -> None:
    catalog = TableCostCatalog.model_validate(_real_catalog_payload())
    first = estimate_table_costs(_evaluated(), result_revision=3, scope=_real_scope(), catalog=catalog)
    repeated = estimate_table_costs(_evaluated(), result_revision=3, scope=_real_scope(), catalog=catalog)
    changed = estimate_table_costs(
        _evaluated(),
        result_revision=3,
        scope=_real_scope().model_copy(update={"provisional_margin_percent": 25}),
        catalog=catalog,
    )

    assert first.estimate_id == repeated.estimate_id
    assert first.estimate_id != changed.estimate_id


def test_money_uses_decimal_half_up_at_the_concept_boundary() -> None:
    payload = _real_catalog_payload()
    setup = next(item for item in payload["tariffs"] if item["id"] == "setup-real")
    setup["rate_eur_per_unit"] = 2.675
    catalog = TableCostCatalog.model_validate(payload)

    estimate = estimate_table_costs(
        _evaluated(), result_revision=3, scope=_real_scope(margin=None), catalog=catalog
    )

    setup_concept = next(item for item in estimate.concepts if item.id == "fixed:preparation")
    assert setup_concept.amount_eur == 2.68


def test_incomplete_scope_remains_partial_and_never_publishes_price() -> None:
    catalog = TableCostCatalog.model_validate(_real_catalog_payload())
    scope = _real_scope().model_copy(
        update={"finish_tariff_id": None, "finish_quantity_m2": None}
    )

    estimate = estimate_table_costs(
        _evaluated(), result_revision=3, scope=scope, catalog=catalog
    )

    assert estimate.total_state == "partial"
    assert estimate.grand_total_eur is None
    assert estimate.provisional_sale_price_eur is None
    assert estimate.total_hours == 5.5
    assert any(item.id == "finish:unbased" and item.state == "unknown" for item in estimate.concepts)


def test_real_catalog_requires_explicit_edge_and_operation_scope() -> None:
    catalog = TableCostCatalog.model_validate(_real_catalog_payload())
    scope = TableCostScope(
        material_tariff_id="board-real",
        labor_tariff_id="labor-real",
        labor_hours=1,
        finish_tariff_id="finish-real",
        finish_quantity_m2=1,
        provisional_margin_percent=20,
    )

    estimate = estimate_table_costs(
        _evaluated(), result_revision=3, scope=scope, catalog=catalog
    )

    unknown_required = {
        item.id
        for item in estimate.concepts
        if item.state == "unknown" and item.required
    }
    assert {"edge:unscoped", "operation:unscoped"} <= unknown_required
    assert estimate.total_state == "partial"
    assert estimate.grand_total_eur is None
    assert estimate.provisional_sale_price_eur is None
    assert estimate.total_hours is None


def test_motivated_exclusions_can_complete_non_material_scope() -> None:
    catalog = TableCostCatalog.model_validate(_real_catalog_payload())
    scope = TableCostScope(
        material_tariff_id="board-real",
        edge_scope="none",
        exclusions=(
            TableCostExclusion(scope="edge", reason="No se aplica canto a esta pieza maciza."),
            TableCostExclusion(scope="operation", reason="Operaciones incluidas en material comprado."),
            TableCostExclusion(scope="labor", reason="Mano de obra fuera del encargo."),
            TableCostExclusion(scope="finishing", reason="Se entrega sin acabado."),
        ),
    )

    estimate = estimate_table_costs(
        _evaluated(), result_revision=3, scope=scope, catalog=catalog
    )

    assert estimate.total_state == "complete"
    assert estimate.total_hours == 0
    assert estimate.grand_total_eur == 112.41
    assert estimate.provisional_sale_price_eur is None
