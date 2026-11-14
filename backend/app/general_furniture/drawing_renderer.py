"""Schematic component drawings for the reviewed general-furniture BOM."""

from __future__ import annotations

from html import escape
from io import StringIO

import ezdxf

from backend.app.contratos.modelos import GeneralBomRow, GeneralDerivedArtifact


def _value(label: str, item: object) -> str:
    value = getattr(item, "value_mm")
    state = getattr(item, "state")
    shown = f"{value:g} mm" if value is not None else "unknown"
    return f"{label}={shown} [{state}]"


def _quantity(row: GeneralBomRow) -> str:
    shown = str(row.quantity.value) if row.quantity.value is not None else "unknown"
    return f"Q={shown} [{row.quantity.state}]"


def _source(row: GeneralBomRow) -> str:
    refs = (
        *row.source_view_ids,
        *row.source_contour_ids,
        *row.source_dimension_ids,
        *row.source_document_refs,
        *row.source_observation_ids,
        *row.source_evidence_ids,
    )
    return "source: " + ("; ".join(refs) if refs else "none")


def _incomplete_reasons(rows: tuple[GeneralBomRow, ...]) -> tuple[str, ...]:
    reasons: list[str] = []
    for row in rows:
        for label, item in (
            ("length", row.length),
            ("width", row.width),
            ("thickness", row.thickness),
        ):
            if item.value_mm is None:
                reasons.append(f"{row.component_id}:{label}_unknown")
        if row.quantity.value is None:
            reasons.append(f"{row.component_id}:quantity_unknown")
    return tuple(reasons)


def _svg(rows: tuple[GeneralBomRow, ...]) -> bytes:
    height = max(240, 80 + sum(max(1, len(row.occurrence_ids)) * 170 for row in rows))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<g font-family="monospace" font-size="16" fill="#111" stroke="#111">',
        '<text x="30" y="35" stroke="none">schematic; not manufacturing-ready</text>',
    ]
    y = 70
    for row in rows:
        occurrences = tuple((item, "confirmed") for item in row.occurrence_ids) + tuple(
            (item, "provisional scenario") for item in row.scenario_occurrence_ids
        )
        for occurrence_id, occurrence_status in occurrences:
            width = min(420.0, max(80.0, float(row.width.value_mm or 200) * 0.35))
            length = min(120.0, max(40.0, float(row.length.value_mm or 120) * 0.12))
            parts.append(
                f'<rect x="30" y="{y}" width="{width:g}" height="{length:g}" fill="none"/>'
            )
            labels = (
                f"{row.label} / {occurrence_id} [{occurrence_status}]",
                _value("L", row.length),
                _value("W", row.width),
                _value("T", row.thickness),
                _quantity(row),
                _source(row),
            )
            for index, label in enumerate(labels):
                parts.append(
                    f'<text x="{470}" y="{y + 18 + 20 * index}" stroke="none">{escape(label)}</text>'
                )
            y += 170
        if not occurrences:
            labels = (
                f"{row.label} / no physical occurrence",
                _value("L", row.length),
                _value("W", row.width),
                _value("T", row.thickness),
                _quantity(row),
                _source(row),
            )
            for index, label in enumerate(labels):
                parts.append(
                    f'<text x="30" y="{y + 18 + 20 * index}" stroke="none">{escape(label)}</text>'
                )
            y += 140
    parts.append("</g></svg>")
    return "".join(parts).encode("utf-8")


def _dxf(rows: tuple[GeneralBomRow, ...]) -> bytes:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    modelspace = document.modelspace()
    y = 0.0
    modelspace.add_text("schematic; not manufacturing-ready", height=5).set_placement(
        (0, y)
    )
    y -= 15
    for row in rows:
        occurrences = tuple((item, "confirmed") for item in row.occurrence_ids) + tuple(
            (item, "provisional scenario") for item in row.scenario_occurrence_ids
        )
        for occurrence_id, occurrence_status in occurrences:
            width = float(row.width.value_mm or 200)
            length = float(row.length.value_mm or 120)
            points = ((0, y), (width, y), (width, y - length), (0, y - length))
            modelspace.add_lwpolyline(points, close=True)
            labels = (
                f"{row.label} / {occurrence_id} [{occurrence_status}]",
                _value("L", row.length),
                _value("W", row.width),
                _value("T", row.thickness),
                _quantity(row),
                _source(row),
            )
            for index, label in enumerate(labels):
                modelspace.add_text(label, height=5).set_placement(
                    (width + 15, y - index * 8)
                )
            y -= max(length, 60) + 25
        if not occurrences:
            labels = (
                f"{row.label} / no physical occurrence",
                _value("L", row.length),
                _value("W", row.width),
                _value("T", row.thickness),
                _quantity(row),
                _source(row),
            )
            for index, label in enumerate(labels):
                modelspace.add_text(label, height=5).set_placement((0, y - index * 8))
            y -= 65
    stream = StringIO()
    document.write(stream)
    return stream.getvalue().encode("utf-8")


def render_general_component_drawings(
    rows: tuple[GeneralBomRow, ...], *, review_revision: int
) -> tuple[GeneralDerivedArtifact, ...]:
    """Render honest schematic SVG/DXF sheets, one rectangle per known occurrence."""

    reasons = _incomplete_reasons(rows)
    status = "incomplete" if reasons else "ready"
    return (
        GeneralDerivedArtifact(
            id=f"general-drawing-svg-r{review_revision}",
            kind="drawing_svg",
            status=status,
            review_revision=review_revision,
            filename=f"general-components-r{review_revision}.svg",
            media_type="image/svg+xml",
            incomplete_reasons=reasons,
            content=_svg(rows),
        ),
        GeneralDerivedArtifact(
            id=f"general-drawing-dxf-r{review_revision}",
            kind="drawing_dxf",
            status=status,
            review_revision=review_revision,
            filename=f"general-components-r{review_revision}.dxf",
            media_type="application/dxf",
            incomplete_reasons=reasons,
            content=_dxf(rows),
        ),
    )
