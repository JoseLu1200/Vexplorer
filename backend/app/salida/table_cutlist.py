"""CSV genérico 0.5 inspirado conceptualmente por la lista de corte de Pablo (1d4b747).

Este formato no certifica fabricabilidad y no completa datos que el programa de mesa no modela.
"""

from __future__ import annotations

import csv
import io

from backend.app.contratos.modelos import EvaluatedTableProgram


FIELDS = (
    "schema_version",
    "result_revision",
    "program_hash",
    "manufacturing_status",
    "component_id",
    "role",
    "accepted",
    "quantity",
    "occurrence_ids",
    "length_mm",
    "length_state",
    "width_mm",
    "width_state",
    "thickness_mm",
    "thickness_state",
    "material",
    "material_state",
    "finish",
    "finish_state",
    "grain",
    "grain_state",
    "edge_banding",
    "edge_banding_state",
    "evidence_ids",
    "unknown_fields",
)


def _safe_csv(value: object) -> object:
    if isinstance(value, str) and value.lstrip(" \t\r\n")[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def export_table_cutlist_csv(
    evaluated: EvaluatedTableProgram,
    *,
    result_revision: int,
) -> str:
    if result_revision <= 0:
        raise ValueError("invalid_result_revision")
    if evaluated.state != "completed":
        raise ValueError("table_revision_not_accepted")
    occurrences: dict[str, list[tuple[int, str]]] = {
        component.id: [] for component in evaluated.components
    }
    seen_occurrence_ids: set[str] = set()
    for occurrence in evaluated.occurrences:
        if occurrence.id in seen_occurrence_ids:
            raise ValueError(f"duplicate_occurrence_id:{occurrence.id}")
        seen_occurrence_ids.add(occurrence.id)
        occurrences[occurrence.component_id].append(
            (occurrence.occurrence_index, occurrence.id)
        )
    for component in evaluated.components:
        if component.quantity != len(occurrences[component.id]):
            raise ValueError(f"occurrence_quantity_mismatch:{component.id}")

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for component in evaluated.components:
        occurrence_ids = tuple(
            occurrence_id for _, occurrence_id in sorted(occurrences[component.id])
        )
        row = {
            "schema_version": "0.5.0",
            "result_revision": result_revision,
            "program_hash": evaluated.program_hash,
            "manufacturing_status": "generic_not_certified",
            "component_id": component.id,
            "role": component.role,
            "accepted": component.accepted,
            "quantity": len(occurrence_ids),
            "occurrence_ids": "|".join(occurrence_ids),
            "length_mm": component.length.value_mm,
            "length_state": component.length.state,
            "width_mm": component.width.value_mm,
            "width_state": component.width.state,
            "thickness_mm": component.thickness.value_mm,
            "thickness_state": component.thickness.state,
            "material": "",
            "material_state": "unknown",
            "finish": "",
            "finish_state": "unknown",
            "grain": "",
            "grain_state": "unknown",
            "edge_banding": "",
            "edge_banding_state": "unknown",
            "evidence_ids": "|".join(component.evidence_ids),
            "unknown_fields": "material|finish|grain|edge_banding",
        }
        writer.writerow({key: _safe_csv(value) for key, value in row.items()})
    return stream.getvalue()
