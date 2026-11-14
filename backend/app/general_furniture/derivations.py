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
    GeneralDerivedArtifact,
    GeneralDerivedPackage,
    GeneralFurnitureReview,
    GeneralScene,
    GeneralSceneItem,
)
from backend.app.general_furniture.drawing_renderer import (
    render_general_component_drawings,
)


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
            "width_mm",
            "thickness_mm",
            "material",
            "finish",
        )
    )
    for row in rows:
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
                row.width.value_mm or "",
                row.thickness.value_mm or "",
                _csv_safe(row.material.value or ""),
                _csv_safe(row.finish.value or ""),
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


def derive_general_package(review: GeneralFurnitureReview) -> GeneralDerivedPackage:
    occurrences = {}
    for item in review.occurrences:
        occurrences.setdefault(item.component_id, []).append(item.id)
    provisional_occurrences = {}
    for item in review.scenario_occurrences:
        provisional_occurrences.setdefault(item.component_id, []).append(item.id)
    rows = tuple(
        GeneralBomRow(
            component_id=item.id,
            label=item.label,
            kind=item.kind,
            role=item.role,
            occurrence_ids=tuple(occurrences.get(item.id, ())),
            scenario_occurrence_ids=tuple(provisional_occurrences.get(item.id, ())),
            occurrence_status="confirmed" if occurrences.get(item.id) else "provisional" if provisional_occurrences.get(item.id) else "unknown",
            quantity=item.quantity,
            length=item.length,
            width=item.width,
            thickness=item.thickness,
            material=item.material,
            finish=item.finish,
            source_view_ids=item.source_view_ids,
            source_observation_ids=item.source_observation_ids,
            source_contour_ids=item.source_contour_ids,
            source_evidence_ids=item.source_evidence_ids,
            source_dimension_ids=item.source_dimension_ids,
            source_document_refs=item.source_document_refs,
        )
        for item in review.components
    )
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
    incomplete_reasons = tuple(
        sorted(
            {
                field
                for component in review.components
                for field in component.unknown_fields
            }
            | set(all_missing)
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
    )
