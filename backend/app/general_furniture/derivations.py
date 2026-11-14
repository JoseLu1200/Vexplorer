from __future__ import annotations

import csv
import io
import json
from html import escape

import ezdxf

from backend.app.contratos.modelos import (
    GeneralBomRow,
    GeneralCostBasis,
    GeneralCostBasisContributor,
    GeneralDerivedFieldReview,
    GeneralDerivedArtifact,
    GeneralDerivedPackage,
    GeneralFurnitureReview,
    GeneralPieceGeometry,
    GeneralQuantity,
    GeneralScene,
    GeneralSceneItem,
    GeneralTextValue,
    GeneralValue,
)
from backend.app.general_furniture.drawing_renderer import (
    render_general_component_drawings,
)
from backend.app.general_furniture.construction_planner import plan_general_construction
from backend.app.general_furniture.construction_drawings import render_construction_artifacts


def _csv_safe(value: str) -> str:
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def _bom_csv(rows: tuple[GeneralBomRow, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        (
            "component_id",
            "label",
            "role",
            "quantity",
            "quantity_state",
            "occurrence_status",
            "physical_occurrence_ids",
            "scenario_occurrence_ids",
            "length_mm",
            "length_state",
            "length_range_min_mm",
            "length_range_max_mm",
            "width_mm",
            "width_state",
            "width_range_min_mm",
            "width_range_max_mm",
            "thickness_mm",
            "thickness_state",
            "thickness_range_min_mm",
            "thickness_range_max_mm",
            "material",
            "finish",
            "length_review_status",
            "width_review_status",
            "thickness_review_status",
            "quantity_review_status",
            "material_review_status",
            "finish_review_status",
        )
    )
    for row in rows:
        review_statuses = {
            item.field: item.status for item in row.machine_field_reviews
        }
        writer.writerow(
            (
                row.component_id,
                _csv_safe(row.label),
                _csv_safe(row.role),
                row.quantity.value or "",
                row.quantity.state,
                row.occurrence_status,
                "|".join(row.occurrence_ids),
                "|".join(row.scenario_occurrence_ids),
                row.length.value_mm or "",
                row.length.state,
                row.length.range_mm.min_mm if row.length.range_mm else "",
                row.length.range_mm.max_mm if row.length.range_mm else "",
                row.width.value_mm or "",
                row.width.state,
                row.width.range_mm.min_mm if row.width.range_mm else "",
                row.width.range_mm.max_mm if row.width.range_mm else "",
                row.thickness.value_mm or "",
                row.thickness.state,
                row.thickness.range_mm.min_mm if row.thickness.range_mm else "",
                row.thickness.range_mm.max_mm if row.thickness.range_mm else "",
                _csv_safe(row.material.value or ""),
                _csv_safe(row.finish.value or ""),
                review_statuses.get("length", ""),
                review_statuses.get("width", ""),
                review_statuses.get("thickness", ""),
                review_statuses.get("quantity", ""),
                review_statuses.get("material", ""),
                review_statuses.get("finish", ""),
            )
        )
    return stream.getvalue().encode("utf-8-sig")


def _drawing_svg(rows: tuple[GeneralBomRow, ...]) -> bytes:
    elements = []
    y = 20.0
    for row in rows:
        if row.length.value_mm is None or row.width.value_mm is None:
            continue
        scale = min(500 / row.length.value_mm, 240 / row.width.value_mm, 1.0)
        width = row.length.value_mm * scale
        height = row.width.value_mm * scale
        elements.append(
            f'<rect x="20" y="{y}" width="{width}" height="{height}" fill="none" stroke="black"/>'
        )
        elements.append(
            f'<text x="25" y="{y + 16}">{escape(row.label)} — esquema, sin colocación</text>'
        )
        y += height + 30
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="560" height="{max(y, 80)}">'
        + "".join(elements)
        + "</svg>"
    ).encode("utf-8")


def _drawing_dxf(rows: tuple[GeneralBomRow, ...]) -> bytes:
    document = ezdxf.new("R2010")
    space = document.modelspace()
    y = 0.0
    for row in rows:
        if row.length.value_mm is None or row.width.value_mm is None:
            continue
        length, width = row.length.value_mm, row.width.value_mm
        space.add_lwpolyline(
            ((0, y), (length, y), (length, y + width), (0, y + width)),
            close=True,
            dxfattribs={"layer": "SCHEMATIC_UNPLACED"},
        )
        space.add_text(
            row.label, height=10, dxfattribs={"layer": "LABELS"}
        ).set_placement((5, y + 5))
        y += width + 50
    stream = io.StringIO()
    document.write(stream)
    return stream.getvalue().encode("utf-8")


_MACHINE_FIELDS = (
    "length", "width", "thickness", "quantity", "material", "finish"
)


def _masked_unknown(value):
    if isinstance(value, GeneralValue):
        return GeneralValue(
            value_mm=None,
            state="unknown",
            dependency_refs=value.dependency_refs,
            evidence_ids=value.evidence_ids,
            dimension_ids=value.dimension_ids,
        )
    if isinstance(value, GeneralQuantity):
        return GeneralQuantity(
            value=None,
            state="unknown",
            dependency_refs=value.dependency_refs,
            evidence_ids=value.evidence_ids,
        )
    if isinstance(value, GeneralTextValue):
        return GeneralTextValue(
            value=None,
            state="unknown",
            dependency_refs=value.dependency_refs,
            evidence_ids=value.evidence_ids,
        )
    raise TypeError("unsupported_general_derived_field")


def _machine_projected_fields(review: GeneralFurnitureReview, component):
    if review.reviewer_kind != "machine":
        return (
            {field: getattr(component, field) for field in _MACHINE_FIELDS},
            (),
        )
    decisions = {item.target_ref: item for item in review.machine_field_reviews}
    checks = {item.id: item for item in review.machine_checks}
    rejected_targets = {
        item.target_ref
        for item in review.machine_field_reviews
        if item.status in {"rejected", "conflict"}
    }
    parameter_by_binding = {
        f"binding:{item.binding_id}": f"parameter:{item.id}"
        for item in review.construction_parameters
        if item.binding_id is not None
    }

    def has_rejected_dependency(field: str, raw_value) -> bool:
        if f"component:{component.id}.existence" in rejected_targets:
            return True
        if field in {"length", "width", "thickness"} and f"component:{component.id}.geometry" in rejected_targets:
            return True
        pending = list(getattr(raw_value, "dependency_refs", ()))
        seen = set()
        parameters = {f"parameter:{item.id}": item for item in review.construction_parameters}
        while pending:
            reference = pending.pop()
            reference = parameter_by_binding.get(reference, reference)
            if reference in seen:
                continue
            seen.add(reference)
            if reference in rejected_targets:
                return True
            parameter = parameters.get(reference)
            if parameter is not None:
                pending.extend(parameter.dependency_refs)
        return False
    projected = {}
    metadata = []
    for field in _MACHINE_FIELDS:
        target_ref = f"component:{component.id}.{field}"
        decision = decisions.get(target_ref)
        status = decision.status if decision is not None else "unreviewed"
        check_ids = decision.check_ids if decision is not None else ()
        selected_checks = tuple(checks[item] for item in check_ids if item in checks)
        raw_value = getattr(component, field)
        if status == "accepted" and has_rejected_dependency(field, raw_value):
            status = "conflict"
        if field == "quantity" and status == "accepted" and raw_value.value is not None:
            scenario_indices = {
                item.occurrence_index
                for item in review.scenario_occurrences
                if item.component_id == component.id
            }
            if not component.quantity.state in {"observed", "derived", "confirmed"} and scenario_indices != set(range(1, raw_value.value + 1)):
                status = "unreviewed"
        metadata.append(
            GeneralDerivedFieldReview(
                field=field,
                target_ref=target_ref,
                status=status,
                check_ids=check_ids,
                check_summaries=tuple(item.summary for item in selected_checks),
                source_refs=tuple(
                    dict.fromkeys(
                        reference
                        for item in selected_checks
                        for reference in item.source_refs
                    )
                ),
            )
        )
        projected[field] = raw_value if status == "accepted" else _masked_unknown(raw_value)
    return projected, tuple(metadata)


def _construction_projected_review(
    review: GeneralFurnitureReview, rows: tuple[GeneralBomRow, ...]
) -> GeneralFurnitureReview:
    """Apply the same closed machine projection before planning any geometry."""
    if review.reviewer_kind != "machine":
        return review
    rejected = {
        item.target_ref
        for item in review.machine_field_reviews
        if item.status in {"rejected", "conflict"}
    }
    rows_by_id = {row.component_id: row for row in rows}
    components = []
    retained_ids = set()
    for component in review.components:
        if f"component:{component.id}.existence" in rejected:
            continue
        row = rows_by_id[component.id]
        geometry = component.geometry
        if f"component:{component.id}.geometry" in rejected:
            geometry = GeneralPieceGeometry(
                shape_kind="unknown",
                source_contour_ids=component.geometry.source_contour_ids,
                basis_refs=component.geometry.basis_refs,
                rationale="Geometry rejected by the machine review.",
            )
        components.append(component.model_copy(update={
            "length": row.length,
            "width": row.width,
            "thickness": row.thickness,
            "quantity": row.quantity,
            "material": row.material,
            "finish": row.finish,
            "geometry": geometry,
        }))
        retained_ids.add(component.id)
    return review.model_copy(update={
        "components": tuple(components),
        "construction_parameters": tuple(
            parameter
            for parameter in review.construction_parameters
            if f"parameter:{parameter.id}" not in rejected
        ),
        "scenario_occurrences": tuple(
            occurrence
            for occurrence in review.scenario_occurrences
            if occurrence.component_id in retained_ids
            and rows_by_id[occurrence.component_id].quantity.value is not None
        ),
        "construction_details": tuple(
            detail
            for detail in review.construction_details
            if f"detail:{detail.id}" not in rejected
            and set(detail.component_ids) <= retained_ids
            and not set(detail.parameter_refs) & rejected
            and not (
                detail.geometry is not None
                and set(detail.geometry.dimension_refs) & rejected
            )
        ),
        "construction_decisions": tuple(
            decision
            for decision in review.construction_decisions
            if f"decision:{decision.id}" not in rejected
        ),
        "construction_placements": tuple(
            placement
            for placement in review.construction_placements
            if placement.piece_id in retained_ids
        ),
    })


def derive_general_package(review: GeneralFurnitureReview) -> GeneralDerivedPackage:
    occurrences = {}
    for item in review.occurrences:
        occurrences.setdefault(item.component_id, []).append(item.id)
    provisional_occurrences = {}
    for item in review.scenario_occurrences:
        provisional_occurrences.setdefault(item.component_id, []).append(item.id)
    rows_list = []
    for item in review.components:
        projected, machine_field_reviews = _machine_projected_fields(review, item)
        quantity_is_usable = (
            review.reviewer_kind != "machine"
            or next(
                value.status
                for value in machine_field_reviews
                if value.field == "quantity"
            ) == "accepted"
        )
        physical_ids = (
            tuple(occurrences.get(item.id, ())) if quantity_is_usable else ()
        )
        scenario_ids = (
            tuple(provisional_occurrences.get(item.id, ()))
            if quantity_is_usable
            else ()
        )
        rows_list.append(GeneralBomRow(
            component_id=item.id,
            label=item.label,
            kind=item.kind,
            role=item.role,
            occurrence_ids=physical_ids,
            scenario_occurrence_ids=scenario_ids,
            occurrence_status="confirmed" if physical_ids else "provisional" if scenario_ids else "unknown",
            quantity=projected["quantity"],
            length=projected["length"],
            width=projected["width"],
            thickness=projected["thickness"],
            material=projected["material"],
            finish=projected["finish"],
            source_view_ids=item.source_view_ids,
            source_observation_ids=item.source_observation_ids,
            source_contour_ids=item.source_contour_ids,
            source_evidence_ids=item.source_evidence_ids,
            source_dimension_ids=item.source_dimension_ids,
            source_document_refs=item.source_document_refs,
            machine_field_reviews=machine_field_reviews,
        ))
    rows = tuple(rows_list)
    contributors = []
    for row in rows:
        count = len(row.occurrence_ids)
        reliable = {"observed", "derived", "confirmed"}
        area = None
        volume = None
        missing = []
        if count and row.length.state in reliable and row.width.state in reliable:
            area = round(
                float(row.length.value_mm)
                * float(row.width.value_mm)
                * count
                / 1_000_000,
                9,
            )
            if row.thickness.state in reliable:
                volume = round(area * float(row.thickness.value_mm) / 1000, 12)
            else:
                missing.append("thickness")
        else:
            missing.extend(
                name
                for name, value in (
                    ("quantity", row.quantity),
                    ("length", row.length),
                    ("width", row.width),
                )
                if value.state not in reliable
            )
        if row.material.value is None:
            missing.append("material")
        if row.finish.value is None:
            missing.append("finish")
        contributors.append(
            GeneralCostBasisContributor(
                component_id=row.component_id,
                occurrence_ids=row.occurrence_ids,
                area_m2=area,
                volume_m3=volume,
                material=row.material,
                finish=row.finish,
                missing_data=tuple(dict.fromkeys(missing)),
            )
        )
    all_missing = tuple(
        sorted({value for item in contributors for value in item.missing_data})
    )
    unresolved_declared_fields: set[str] = set()
    rows_by_component = {row.component_id: row for row in rows}
    for component in review.components:
        row = rows_by_component[component.id]
        for field in component.unknown_fields:
            value = getattr(row, field, None)
            resolved_value = (
                getattr(value, "value_mm", None)
                if field in {"length", "width", "thickness"}
                else getattr(value, "value", None)
            )
            if resolved_value is None:
                unresolved_declared_fields.add(field)
    incomplete_reasons = tuple(
        sorted(
            unresolved_declared_fields
            | set(all_missing)
            | {
                f"{row.component_id}:{item.field}_machine_{item.status}"
                for row in rows
                for item in row.machine_field_reviews
                if item.status != "accepted"
            }
        )
    )
    artifact_status = "incomplete" if incomplete_reasons else "ready"
    json_bytes = json.dumps(
        [row.model_dump(mode="json") for row in rows],
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    data_artifacts = tuple(
        GeneralDerivedArtifact(
            id=f"general-r{review.review_revision}-{kind}",
            kind=kind,
            status=artifact_status,
            review_revision=review.review_revision,
            filename=filename,
            media_type=media_type,
            incomplete_reasons=incomplete_reasons,
            content=content,
        )
        for kind, filename, media_type, content in (
            ("bom_csv", "bom.csv", "text/csv", _bom_csv(rows)),
            ("bom_json", "bom.json", "application/json", json_bytes),
        )
    )
    artifacts = data_artifacts + render_general_component_drawings(
        rows, review_revision=review.review_revision
    )
    construction_review = _construction_projected_review(review, rows)
    construction = (
        plan_general_construction(construction_review, review.construction_validation)
        if review.construction_validation is not None
        else None
    )
    if construction is not None:
        artifacts += render_construction_artifacts(construction)
    scene_items = tuple(
        GeneralSceneItem(
            id=f"scene:{row.component_id}",
            component_id=row.component_id,
            occurrence_ids=row.occurrence_ids,
            scenario_occurrence_ids=row.scenario_occurrence_ids,
            occurrence_status=row.occurrence_status,
            length=row.length,
            width=row.width,
            thickness=row.thickness,
            position_mm=None,
            status="schematic_unplaced"
            if row.length.value_mm is not None and row.width.value_mm is not None
            else "unavailable",
        )
        for row in rows
    )
    cost_status = (
        "unavailable" if not contributors else "partial" if all_missing else "complete"
    )
    return GeneralDerivedPackage(
        run_id=review.run_id,
        proposal_revision=review.proposal_revision,
        review_revision=review.review_revision,
        status="incomplete" if incomplete_reasons else "ready",
        bom_rows=rows,
        artifacts=artifacts,
        scene=GeneralScene(
            status="schematic_incomplete" if incomplete_reasons else "schematic_ready",
            items=scene_items,
            warnings=(
                "Representación esquemática sin colocaciones de montaje validadas.",
            ),
        ),
        cost_basis=GeneralCostBasis(
            status=cost_status,
            contributors=tuple(contributors),
            missing_data=all_missing,
        ),
        construction=construction,
    )
