from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from backend.app.contratos.modelos import (
    EvaluatedTableComponent,
    EvaluatedTableProgram,
    TableCostCatalog,
    TableCostConcept,
    TableCostEstimate,
    TableCostScope,
    TableCostTariff,
)


CATALOG_VERSION = "synthetic-table-costs-2026-11-14"
CATALOG_SOURCE = "synthetic development rates; not a supplier quotation"
CATALOG_DATE = "2026-11-14"
CURRENCY = "EUR"


@dataclass(frozen=True)
class _Tariff:
    id: str
    concept_type: str
    rate: float
    rate_unit: str


_MATERIAL_TARIFFS = {
    "demo_board_area_v1": _Tariff("demo_board_area_v1", "material_area", 42.0, "EUR/m2"),
    "demo_solid_volume_v1": _Tariff("demo_solid_volume_v1", "material_volume", 900.0, "EUR/m3"),
}
_EDGE_TARIFF = _Tariff("demo_edge_exposed_v1", "edge", 2.5, "EUR/m")
_OPERATION_TARIFFS = {
    "demo_machining_hour_v1": _Tariff("demo_machining_hour_v1", "operation", 36.0, "EUR/h"),
}
_SETUP_RATE_EUR = 25.0


def get_table_cost_catalog() -> TableCostCatalog:
    """Return the synthetic, versioned tariffs accepted by the estimator scope."""
    return TableCostCatalog(
        catalog_version=CATALOG_VERSION,
        tariffs=(
            TableCostTariff(
                id="demo_board_area_v1",
                label="Tablero sintético por superficie",
                concept_type="material_area",
                scope="material",
                rate_eur_per_unit=42.0,
                rate_unit="EUR/m2",
            ),
            TableCostTariff(
                id="demo_solid_volume_v1",
                label="Material sintético por volumen",
                concept_type="material_volume",
                scope="material",
                rate_eur_per_unit=900.0,
                rate_unit="EUR/m3",
            ),
            TableCostTariff(
                id="demo_edge_exposed_v1",
                label="Canto expuesto sintético",
                concept_type="edge",
                scope="edge",
                rate_eur_per_unit=2.5,
                rate_unit="EUR/m",
            ),
            TableCostTariff(
                id="demo_machining_hour_v1",
                label="Mecanizado sintético por hora",
                concept_type="operation",
                scope="operation",
                rate_eur_per_unit=36.0,
                rate_unit="EUR/h",
            ),
        ),
    )


def _money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _quantity(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.000000001")))


def _catalog_refs(tariff_id: str) -> tuple[str, ...]:
    return (
        f"tariff:{tariff_id}",
        f"catalog:{CATALOG_VERSION}",
        f"source:{CATALOG_SOURCE}",
        f"date:{CATALOG_DATE}",
    )


def _occurrences_by_component(evaluated: EvaluatedTableProgram) -> dict[str, tuple[str, ...]]:
    component_ids = {component.id for component in evaluated.components}
    occurrence_ids: set[str] = set()
    grouped: dict[str, list[str]] = {component_id: [] for component_id in component_ids}
    for occurrence in evaluated.occurrences:
        if occurrence.id in occurrence_ids:
            raise ValueError(f"duplicate occurrence id: {occurrence.id}")
        if occurrence.component_id not in component_ids:
            raise ValueError(f"occurrence references unknown component: {occurrence.component_id}")
        occurrence_ids.add(occurrence.id)
        grouped[occurrence.component_id].append(occurrence.id)

    result = {component_id: tuple(ids) for component_id, ids in grouped.items()}
    for component in evaluated.components:
        if component.quantity is not None and component.quantity != len(result[component.id]):
            raise ValueError(
                "occurrence quantity mismatch for "
                f"{component.id}: declared {component.quantity}, found {len(result[component.id])}"
            )
    return result


def _material_concept(
    component: EvaluatedTableComponent,
    occurrence_ids: tuple[str, ...],
    tariff: _Tariff | None,
    requested_tariff_id: str | None,
) -> TableCostConcept:
    is_volume = tariff is not None and tariff.concept_type == "material_volume"
    concept_type = "material_volume" if is_volume else "material_area"
    quantity_unit = "m3" if is_volume else "m2"
    rate_unit = "EUR/m3" if is_volume else "EUR/m2"
    dimensions = (component.length.value_mm, component.width.value_mm)
    if is_volume:
        dimensions += (component.thickness.value_mm,)
    has_dimensions = all(value is not None for value in dimensions)

    quantity = None
    if has_dimensions:
        divisor = 1_000_000_000 if is_volume else 1_000_000
        product = 1.0
        for value in dimensions:
            product *= float(value)
        quantity = _quantity(product * len(occurrence_ids) / divisor)

    resolved = component.accepted and tariff is not None and quantity is not None
    rate = tariff.rate if tariff is not None else None
    amount = _money(quantity * rate) if resolved and quantity is not None and rate is not None else None
    tariff_ref = requested_tariff_id or "material_tariff_unselected"
    dependency_refs = (
        f"component:{component.id}",
        f"field:{component.id}.length_mm",
        f"field:{component.id}.width_mm",
    )
    if is_volume:
        dependency_refs += (f"field:{component.id}.thickness_mm",)
    dependency_refs += _catalog_refs(tariff_ref)
    formula_dimensions = "length_mm * width_mm * thickness_mm" if is_volume else "length_mm * width_mm"

    return TableCostConcept(
        id=f"material:{component.id}",
        label=f"Material de {component.id}",
        concept_type=concept_type,
        component_id=component.id,
        occurrence_ids=occurrence_ids,
        formula=f"({formula_dimensions}) * occurrence_count -> {quantity_unit}",
        quantity=quantity,
        quantity_unit=quantity_unit,
        rate_eur_per_unit=rate,
        rate_unit=rate_unit,
        amount_eur=amount,
        state="resolved" if resolved else "unknown",
        required=True,
        dependency_refs=dependency_refs,
    )


def _edge_concept(
    component: EvaluatedTableComponent,
    occurrence_ids: tuple[str, ...],
    scope: TableCostScope,
) -> TableCostConcept:
    dependency_refs = (
        f"component:{component.id}",
        f"field:{component.id}.length_mm",
        f"field:{component.id}.width_mm",
        *_catalog_refs(_EDGE_TARIFF.id),
    )
    if scope.edge_scope == "none":
        return TableCostConcept(
            id=f"edge:{component.id}", label=f"Canto de {component.id}", concept_type="edge",
            component_id=component.id, occurrence_ids=occurrence_ids, formula="edge_scope=none",
            quantity=None, quantity_unit="m", rate_eur_per_unit=None, rate_unit="EUR/m",
            amount_eur=None, state="not_applicable", required=False, dependency_refs=dependency_refs,
        )

    length = component.length.value_mm
    width = component.width.value_mm
    quantity = None
    if length is not None and width is not None:
        quantity = _quantity(2.0 * (length + width) * len(occurrence_ids) / 1_000)
    resolved = component.accepted and quantity is not None
    amount = _money(quantity * _EDGE_TARIFF.rate) if resolved and quantity is not None else None
    return TableCostConcept(
        id=f"edge:{component.id}", label=f"Canto expuesto de {component.id}", concept_type="edge",
        component_id=component.id, occurrence_ids=occurrence_ids,
        formula="2 * (length_mm + width_mm) * occurrence_count -> m", quantity=quantity,
        quantity_unit="m", rate_eur_per_unit=_EDGE_TARIFF.rate, rate_unit="EUR/m",
        amount_eur=amount, state="resolved" if resolved else "unknown", required=True,
        dependency_refs=dependency_refs,
    )


def _pending_concept(
    *,
    concept_id: str,
    label: str,
    concept_type: str,
    quantity_unit: str,
    rate_unit: str,
    tariff: _Tariff | None = None,
) -> TableCostConcept:
    return TableCostConcept(
        id=concept_id, label=label, concept_type=concept_type,
        formula="pending: no validated quantity basis in evaluated table program",
        quantity=None, quantity_unit=quantity_unit,
        rate_eur_per_unit=tariff.rate if tariff is not None else None, rate_unit=rate_unit,
        amount_eur=None, state="unknown", required=True,
        dependency_refs=_catalog_refs(tariff.id if tariff is not None else concept_id),
    )


def estimate_table_costs(
    evaluated: EvaluatedTableProgram,
    *,
    result_revision: int,
    scope: TableCostScope,
) -> TableCostEstimate:
    occurrences = _occurrences_by_component(evaluated)
    material_tariff = _MATERIAL_TARIFFS.get(scope.material_tariff_id or "")
    concepts: list[TableCostConcept] = [
        TableCostConcept(
            id="fixed:preparation", label="Preparación fija", concept_type="fixed",
            formula="1 setup per estimate", quantity=1.0, quantity_unit="unit",
            rate_eur_per_unit=_SETUP_RATE_EUR, rate_unit="EUR/unit",
            amount_eur=_SETUP_RATE_EUR, state="resolved", required=True,
            dependency_refs=_catalog_refs("demo_preparation_fixed_v1"),
        )
    ]
    for component in evaluated.components:
        component_occurrences = occurrences[component.id]
        concepts.append(
            _material_concept(component, component_occurrences, material_tariff, scope.material_tariff_id)
        )
        concepts.append(_edge_concept(component, component_occurrences, scope))

    for tariff_id in dict.fromkeys(scope.operation_tariff_ids):
        tariff = _OPERATION_TARIFFS.get(tariff_id)
        concepts.append(
            _pending_concept(
                concept_id=f"operation:{tariff_id}", label=f"Operación {tariff_id}",
                concept_type="operation", quantity_unit="h", rate_unit="EUR/h", tariff=tariff,
            )
        )
    concepts.extend((
        _pending_concept(
            concept_id="labor:unbased", label="Mano de obra pendiente de base horaria",
            concept_type="labor", quantity_unit="h", rate_unit="EUR/h",
        ),
        _pending_concept(
            concept_id="finish:unbased", label="Acabado pendiente de alcance",
            concept_type="finish", quantity_unit="m2", rate_unit="EUR/m2",
        ),
    ))

    known_subtotal = _money(sum(item.amount_eur or 0.0 for item in concepts))
    required_unknown = any(item.required and item.state == "unknown" for item in concepts)
    return TableCostEstimate(
        result_revision=result_revision,
        program_hash=evaluated.program_hash,
        catalog_version=CATALOG_VERSION,
        currency=CURRENCY,
        scope=scope,
        concepts=tuple(concepts),
        known_subtotal_eur=known_subtotal,
        grand_total_eur=None if required_unknown else known_subtotal,
        total_state="partial" if required_unknown else "complete",
        warnings=(
            "Tarifas sintéticas versionadas; no son una cotización de proveedor.",
            "El subtotal conocido es provisional y no representa precio de venta.",
        ),
    )
