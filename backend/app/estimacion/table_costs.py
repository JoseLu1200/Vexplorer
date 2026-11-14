from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json

from backend.app.contratos.modelos import (
    EvaluatedTableComponent,
    EvaluatedTableProgram,
    TableCostCatalog,
    TableCostConcept,
    TableCostEstimate,
    TableCostScope,
    TableCostTariff,
)
from backend.app.estimacion.cost_catalog import (
    DEMO_CATALOG_DATE,
    DEMO_CATALOG_SOURCE,
    DEMO_CATALOG_VERSION,
    get_configured_table_cost_catalog,
)


CATALOG_VERSION = DEMO_CATALOG_VERSION
CATALOG_SOURCE = DEMO_CATALOG_SOURCE
CATALOG_DATE = DEMO_CATALOG_DATE
CURRENCY = "EUR"


@dataclass(frozen=True)
class _Tariff:
    id: str
    concept_type: str
    rate: float
    rate_unit: str


_MATERIAL_TARIFFS = {
    "demo_board_area_v1": _Tariff(
        "demo_board_area_v1", "material_area", 42.0, "EUR/m2"
    ),
    "demo_solid_volume_v1": _Tariff(
        "demo_solid_volume_v1", "material_volume", 900.0, "EUR/m3"
    ),
}
_EDGE_TARIFF = _Tariff("demo_edge_exposed_v1", "edge", 2.5, "EUR/m")
_OPERATION_TARIFFS = {
    "demo_machining_hour_v1": _Tariff(
        "demo_machining_hour_v1", "operation", 36.0, "EUR/h"
    ),
}
_SETUP_TARIFF = _Tariff("demo_preparation_fixed_v1", "fixed", 25.0, "EUR/unit")


def get_table_cost_catalog() -> TableCostCatalog:
    """Load configured real tariffs, or the labeled demo catalog when unset."""
    return get_configured_table_cost_catalog()


def _money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _quantity(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.000000001")))


def _catalog_refs(tariff_id: str | None = None) -> tuple[str, ...]:
    tariff_refs = (f"tariff:{tariff_id}",) if tariff_id is not None else ()
    return tariff_refs + (
        f"catalog:{CATALOG_VERSION}",
        f"source:{CATALOG_SOURCE}",
        f"date:{CATALOG_DATE}",
    )


def _occurrences_by_component(
    evaluated: EvaluatedTableProgram,
) -> dict[str, tuple[str, ...]]:
    component_ids = {component.id for component in evaluated.components}
    occurrence_ids: set[str] = set()
    grouped: dict[str, list[str]] = {component_id: [] for component_id in component_ids}
    for occurrence in evaluated.occurrences:
        if occurrence.id in occurrence_ids:
            raise ValueError(f"duplicate occurrence id: {occurrence.id}")
        if occurrence.component_id not in component_ids:
            raise ValueError(
                f"occurrence references unknown component: {occurrence.component_id}"
            )
        occurrence_ids.add(occurrence.id)
        grouped[occurrence.component_id].append(occurrence.id)

    result = {component_id: tuple(ids) for component_id, ids in grouped.items()}
    for component in evaluated.components:
        if component.quantity is not None and component.quantity != len(
            result[component.id]
        ):
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
    amount = (
        _money(quantity * rate)
        if resolved and quantity is not None and rate is not None
        else None
    )
    dependency_refs = (
        f"component:{component.id}",
        f"field:{component.id}.length_mm",
        f"field:{component.id}.width_mm",
    )
    if is_volume:
        dependency_refs += (f"field:{component.id}.thickness_mm",)
    dependency_refs += _catalog_refs(tariff.id if tariff is not None else None)
    if requested_tariff_id is not None and tariff is None:
        dependency_refs += (f"requested_tariff:{requested_tariff_id}",)
    formula_dimensions = (
        "length_mm * width_mm * thickness_mm" if is_volume else "length_mm * width_mm"
    )

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
            id=f"edge:{component.id}",
            label=f"Canto de {component.id}",
            concept_type="edge",
            component_id=component.id,
            occurrence_ids=occurrence_ids,
            formula="edge_scope=none",
            quantity=None,
            quantity_unit="m",
            rate_eur_per_unit=None,
            rate_unit="EUR/m",
            amount_eur=None,
            state="not_applicable",
            required=False,
            dependency_refs=dependency_refs,
        )

    length = component.length.value_mm
    width = component.width.value_mm
    quantity = None
    if length is not None and width is not None:
        quantity = _quantity(2.0 * (length + width) * len(occurrence_ids) / 1_000)
    resolved = component.accepted and quantity is not None
    amount = (
        _money(quantity * _EDGE_TARIFF.rate)
        if resolved and quantity is not None
        else None
    )
    return TableCostConcept(
        id=f"edge:{component.id}",
        label=f"Canto expuesto de {component.id}",
        concept_type="edge",
        component_id=component.id,
        occurrence_ids=occurrence_ids,
        formula="2 * (length_mm + width_mm) * occurrence_count -> m",
        quantity=quantity,
        quantity_unit="m",
        rate_eur_per_unit=_EDGE_TARIFF.rate,
        rate_unit="EUR/m",
        amount_eur=amount,
        state="resolved" if resolved else "unknown",
        required=True,
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
    requested_tariff_id: str | None = None,
) -> TableCostConcept:
    return TableCostConcept(
        id=concept_id,
        label=label,
        concept_type=concept_type,
        formula="pending: no validated quantity basis in evaluated table program",
        quantity=None,
        quantity_unit=quantity_unit,
        rate_eur_per_unit=tariff.rate if tariff is not None else None,
        rate_unit=rate_unit,
        amount_eur=None,
        state="unknown",
        required=True,
        dependency_refs=(
            _catalog_refs(tariff.id if tariff is not None else None)
            + (
                (f"requested_tariff:{requested_tariff_id}",)
                if tariff is None and requested_tariff_id is not None
                else ()
            )
        ),
    )


def estimate_table_costs(
    evaluated: EvaluatedTableProgram,
    *,
    result_revision: int,
    scope: TableCostScope,
    catalog: TableCostCatalog | None = None,
) -> TableCostEstimate:
    catalog = catalog or get_table_cost_catalog()
    if not catalog.tariffs:
        raise ValueError("invalid cost catalog: at least one tariff required")
    tariffs = {item.id: item for item in catalog.tariffs}
    component_ids = {item.id for item in evaluated.components}
    unknown_override_ids = sorted(
        set(scope.component_material_tariff_ids) - component_ids
    )
    if unknown_override_ids:
        raise ValueError(
            "unknown component material override ids: "
            + ", ".join(unknown_override_ids)
        )
    occurrences = _occurrences_by_component(evaluated)
    exclusions = {item.scope: item.reason for item in scope.exclusions}

    def refs(tariff_id: str | None = None) -> tuple[str, ...]:
        result = (f"tariff:{tariff_id}",) if tariff_id else ()
        result += (f"catalog:{catalog.catalog_version}",)
        if catalog.source:
            result += (f"source:{catalog.source}",)
        if catalog.effective_date:
            result += (f"date:{catalog.effective_date}",)
        return result

    def unknown(
        concept_id: str,
        label: str,
        concept_type: str,
        quantity_unit: str,
        rate_unit: str,
        tariff: TableCostTariff | None = None,
        requested_id: str | None = None,
    ) -> TableCostConcept:
        dependencies = refs(tariff.id if tariff else None)
        if tariff is None and requested_id:
            dependencies += (f"requested_tariff:{requested_id}",)
        return TableCostConcept(
            id=concept_id, label=label, concept_type=concept_type,
            tariff_id=tariff.id if tariff else None,
            formula="pending: no validated quantity basis in economic scope",
            quantity=None, quantity_unit=quantity_unit,
            rate_eur_per_unit=tariff.rate_eur_per_unit if tariff else None,
            rate_unit=rate_unit, amount_eur=None, state="unknown", required=True,
            dependency_refs=dependencies,
        )

    def excluded(scope_name: str) -> TableCostConcept:
        concept_type = {"material": "material_area", "edge": "edge", "operation": "operation", "labor": "labor", "finishing": "finish"}[scope_name]
        quantity_unit = "m2" if scope_name in ("material", "finishing") else "m" if scope_name == "edge" else "h"
        rate_unit = "EUR/m2" if scope_name in ("material", "finishing") else "EUR/m" if scope_name == "edge" else "EUR/h"
        return TableCostConcept(
            id=f"{concept_type}:excluded", label=f"{scope_name} excluido",
            concept_type=concept_type,
            formula=f"excluded by human scope: {exclusions[scope_name]}",
            quantity=None, quantity_unit=quantity_unit, rate_eur_per_unit=None,
            rate_unit=rate_unit, amount_eur=None, state="not_applicable", required=False,
            dependency_refs=refs(),
        )

    setup = next((item for item in catalog.tariffs if item.scope == "preparation" and item.concept_type == "fixed"), None)
    concepts: list[TableCostConcept] = []
    if setup is None:
        concepts.append(unknown("fixed:preparation", "Preparación pendiente", "fixed", "unit", "EUR/unit"))
    else:
        concepts.append(TableCostConcept(
            id="fixed:preparation", label="Preparación fija", concept_type="fixed",
            tariff_id=setup.id,
            formula="1 setup per estimate", quantity=1, quantity_unit="unit",
            rate_eur_per_unit=setup.rate_eur_per_unit, rate_unit="EUR/unit",
            amount_eur=_money(setup.rate_eur_per_unit), state="resolved", required=True,
            dependency_refs=refs(setup.id),
        ))

    for component in evaluated.components:
        if "material" in exclusions:
            if component == evaluated.components[0]:
                concepts.append(excluded("material"))
            continue
        component_occurrences = occurrences[component.id]
        material_id = scope.component_material_tariff_ids.get(component.id, scope.material_tariff_id)
        material = tariffs.get(material_id or "")
        if material is not None and material.scope != "material":
            material = None
        is_volume = material is not None and material.concept_type == "material_volume"
        values = (component.length.value_mm, component.width.value_mm) + ((component.thickness.value_mm,) if is_volume else ())
        quantity = None
        if all(value is not None for value in values):
            product = 1.0
            for value in values:
                product *= float(value)
            quantity = _quantity(product * len(component_occurrences) / (1_000_000_000 if is_volume else 1_000_000))
        resolved = component.accepted and material is not None and quantity is not None
        concept_type = "material_volume" if is_volume else "material_area"
        quantity_unit = "m3" if is_volume else "m2"
        rate_unit = "EUR/m3" if is_volume else "EUR/m2"
        dependencies = (f"component:{component.id}", f"field:{component.id}.length_mm", f"field:{component.id}.width_mm")
        if is_volume:
            dependencies += (f"field:{component.id}.thickness_mm",)
        dependencies += refs(material.id if material else None)
        if material is None and material_id:
            dependencies += (f"requested_tariff:{material_id}",)
        concepts.append(TableCostConcept(
            id=f"material:{component.id}", label=f"Material de {component.id}",
            concept_type=concept_type, component_id=component.id, occurrence_ids=component_occurrences,
            tariff_id=material.id if material else None,
            formula=("length_mm * width_mm * thickness_mm" if is_volume else "length_mm * width_mm") + f" * occurrence_count -> {quantity_unit}",
            quantity=quantity, quantity_unit=quantity_unit,
            rate_eur_per_unit=material.rate_eur_per_unit if material else None,
            rate_unit=rate_unit,
            amount_eur=_money(quantity * material.rate_eur_per_unit) if resolved and quantity is not None and material else None,
            state="resolved" if resolved else "unknown", required=True,
            dependency_refs=dependencies,
        ))

    edge_id = scope.edge_tariff_id or ("demo_edge_exposed_v1" if catalog.synthetic else None)
    edge_tariff = tariffs.get(edge_id or "")
    if "edge" in exclusions:
        concepts.append(excluded("edge"))
    elif scope.edge_scope == "all_exposed" and edge_tariff is not None and edge_tariff.scope == "edge":
        for component in evaluated.components:
            component_occurrences = occurrences[component.id]
            length, width = component.length.value_mm, component.width.value_mm
            quantity = None if length is None or width is None else _quantity(2 * (length + width) * len(component_occurrences) / 1_000)
            resolved = component.accepted and quantity is not None
            concepts.append(TableCostConcept(
                id=f"edge:{component.id}", label=f"Canto expuesto de {component.id}", concept_type="edge",
                tariff_id=edge_tariff.id,
                component_id=component.id, occurrence_ids=component_occurrences,
                formula="2 * (length_mm + width_mm) * occurrence_count -> m",
                quantity=quantity, quantity_unit="m", rate_eur_per_unit=edge_tariff.rate_eur_per_unit,
                rate_unit="EUR/m", amount_eur=_money(quantity * edge_tariff.rate_eur_per_unit) if resolved and quantity is not None else None,
                state="resolved" if resolved else "unknown", required=True,
                dependency_refs=(f"component:{component.id}", f"field:{component.id}.length_mm", f"field:{component.id}.width_mm", *refs(edge_tariff.id)),
            ))
    elif scope.edge_scope == "all_exposed":
        concepts.append(unknown("edge:unbased", "Canto sin tarifa válida", "edge", "m", "EUR/m", requested_id=edge_id))
    elif not catalog.synthetic:
        concepts.append(unknown(
            "edge:unscoped",
            "Alcance de canto pendiente de decisión",
            "edge",
            "m",
            "EUR/m",
        ))
    else:
        for component in evaluated.components:
            concepts.append(TableCostConcept(
                id=f"edge:{component.id}", label=f"Canto de {component.id}", concept_type="edge",
                component_id=component.id, occurrence_ids=occurrences[component.id], formula="edge_scope=none",
                quantity=None, quantity_unit="m", rate_eur_per_unit=None, rate_unit="EUR/m",
                amount_eur=None, state="not_applicable", required=False, dependency_refs=refs(edge_id),
            ))

    if "operation" in exclusions:
        concepts.append(excluded("operation"))
    else:
        for tariff_id in scope.operation_tariff_ids:
            tariff = tariffs.get(tariff_id)
            if tariff is not None and tariff.scope != "operation":
                tariff = None
            hours = scope.operation_hours_by_tariff.get(tariff_id)
            if tariff is None or hours is None:
                concepts.append(unknown(f"operation:{tariff_id}", f"Operación {tariff_id}", "operation", "h", "EUR/h", tariff, tariff_id))
            else:
                concepts.append(TableCostConcept(
                    id=f"operation:{tariff_id}", label=f"Operación {tariff_id}", concept_type="operation",
                    tariff_id=tariff.id,
                    formula="validated hours * catalog rate", quantity=hours, quantity_unit="h",
                    rate_eur_per_unit=tariff.rate_eur_per_unit, rate_unit="EUR/h",
                    amount_eur=_money(hours * tariff.rate_eur_per_unit), state="resolved", required=True,
                    dependency_refs=refs(tariff.id),
                ))
        if not scope.operation_tariff_ids and not catalog.synthetic:
            concepts.append(unknown(
                "operation:unscoped",
                "Operaciones pendientes de decisión",
                "operation",
                "h",
                "EUR/h",
            ))

    if "labor" in exclusions:
        concepts.append(excluded("labor"))
    else:
        labor = tariffs.get(scope.labor_tariff_id or "")
        if labor is not None and labor.scope != "labor":
            labor = None
        if labor is None or scope.labor_hours is None:
            concepts.append(unknown("labor:unbased", "Mano de obra pendiente de base horaria", "labor", "h", "EUR/h", labor, scope.labor_tariff_id))
        else:
            concepts.append(TableCostConcept(
                id="labor:hours", label="Mano de obra", concept_type="labor",
                tariff_id=labor.id,
                formula="validated hours * catalog rate", quantity=scope.labor_hours, quantity_unit="h",
                rate_eur_per_unit=labor.rate_eur_per_unit, rate_unit="EUR/h",
                amount_eur=_money(scope.labor_hours * labor.rate_eur_per_unit), state="resolved", required=True,
                dependency_refs=refs(labor.id),
            ))

    if "finishing" in exclusions:
        concepts.append(excluded("finishing"))
    else:
        finish = tariffs.get(scope.finish_tariff_id or "")
        if finish is not None and finish.scope != "finishing":
            finish = None
        if finish is None or scope.finish_quantity_m2 is None:
            concepts.append(unknown("finish:unbased", "Acabado pendiente de alcance", "finish", "m2", "EUR/m2", finish, scope.finish_tariff_id))
        else:
            concepts.append(TableCostConcept(
                id="finish:measured", label="Acabado medido", concept_type="finish",
                tariff_id=finish.id,
                formula="measured finish area * catalog rate", quantity=scope.finish_quantity_m2, quantity_unit="m2",
                rate_eur_per_unit=finish.rate_eur_per_unit, rate_unit="EUR/m2",
                amount_eur=_money(scope.finish_quantity_m2 * finish.rate_eur_per_unit), state="resolved", required=True,
                dependency_refs=refs(finish.id),
            ))

    known_subtotal = _money(sum(Decimal(str(item.amount_eur)) for item in concepts if item.amount_eur is not None))
    required_unknown = any(item.required and item.state == "unknown" for item in concepts)
    total_state = "partial" if required_unknown else "complete"
    grand_total = None if required_unknown else known_subtotal
    priced = [item for item in concepts if item.amount_eur is not None]
    principal = max(priced, key=lambda item: (item.amount_eur or 0, item.id)).id if priced else None
    operation_scoped = "operation" in exclusions or (
        bool(scope.operation_tariff_ids)
        and all(item in scope.operation_hours_by_tariff for item in scope.operation_tariff_ids)
    )
    labor_scoped = "labor" in exclusions or scope.labor_hours is not None
    total_hours = _quantity(sum(scope.operation_hours_by_tariff.values()) + (scope.labor_hours or 0)) if operation_scoped and labor_scoped else None
    provisional_price = None
    if grand_total is not None and scope.provisional_margin_percent is not None:
        divisor = Decimal("1") - Decimal(str(scope.provisional_margin_percent)) / Decimal("100")
        provisional_price = _money(Decimal(str(grand_total)) / divisor)
    identity_payload = {
        "program_hash": evaluated.program_hash,
        "result_revision": result_revision,
        "catalog": catalog.model_dump(mode="json"),
        "scope": scope.model_dump(mode="json"),
    }
    estimate_id = hashlib.sha256(json.dumps(identity_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    warnings = (("Tarifas sintéticas versionadas; no son una cotización de proveedor.",) if catalog.synthetic else ()) + (
        "El coste calculado no representa precio de venta ni equivale por sí solo a valor de mercado.",
        "El precio provisional excluye impuestos.",
    )
    return TableCostEstimate(
        estimate_id=estimate_id,
        result_revision=result_revision,
        program_hash=evaluated.program_hash,
        catalog_version=catalog.catalog_version,
        catalog_snapshot=catalog,
        synthetic=catalog.synthetic,
        currency=CURRENCY,
        scope=scope,
        concepts=tuple(concepts),
        known_subtotal_eur=known_subtotal,
        grand_total_eur=grand_total,
        total_state=total_state,
        total_hours=total_hours,
        principal_cost_contributor_id=principal,
        provisional_margin_percent=scope.provisional_margin_percent,
        provisional_sale_price_eur=provisional_price,
        warnings=warnings,
    )
