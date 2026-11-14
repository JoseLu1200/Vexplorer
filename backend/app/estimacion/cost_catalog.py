from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from backend.app.contratos.modelos import TableCostCatalog, TableCostTariff


COST_CATALOG_ENV = "VEXPLORER_COST_CATALOG"
DEMO_CATALOG_VERSION = "synthetic-table-costs-2026-11-14"
DEMO_CATALOG_SOURCE = "synthetic development rates; not a supplier quotation"
DEMO_CATALOG_DATE = "2026-11-14"


def demo_table_cost_catalog() -> TableCostCatalog:
    rows = (
        ("demo_board_area_v1", "Tablero sintético por superficie", "material_area", "material", 42.0, "EUR/m2"),
        ("demo_solid_volume_v1", "Material sintético por volumen", "material_volume", "material", 900.0, "EUR/m3"),
        ("demo_edge_exposed_v1", "Canto expuesto sintético", "edge", "edge", 2.5, "EUR/m"),
        ("demo_machining_hour_v1", "Mecanizado sintético por hora", "operation", "operation", 36.0, "EUR/h"),
        ("demo_preparation_fixed_v1", "Preparación fija sintética", "fixed", "preparation", 25.0, "EUR/unit"),
    )
    return TableCostCatalog(
        catalog_version=DEMO_CATALOG_VERSION,
        source=DEMO_CATALOG_SOURCE,
        effective_date=DEMO_CATALOG_DATE,
        synthetic=True,
        tariffs=tuple(
            TableCostTariff(
                id=tariff_id,
                label=label,
                concept_type=concept_type,
                scope=scope,
                rate_eur_per_unit=rate,
                rate_unit=rate_unit,
                synthetic=True,
            )
            for tariff_id, label, concept_type, scope, rate, rate_unit in rows
        ),
    )


def load_table_cost_catalog(path: Path) -> TableCostCatalog:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        catalog = TableCostCatalog.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"invalid cost catalog: {path}") from exc
    if not catalog.tariffs:
        raise ValueError(
            f"invalid cost catalog: {path} (at least one tariff required)"
        )
    return catalog


def get_configured_table_cost_catalog() -> TableCostCatalog:
    configured = os.environ.get(COST_CATALOG_ENV)
    if configured:
        return load_table_cost_catalog(Path(configured))
    return demo_table_cost_catalog()
