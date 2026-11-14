"""Readable schematic drawings for a reviewed general-furniture snapshot."""

from __future__ import annotations

from html import escape
from io import StringIO
import json
from textwrap import wrap

import ezdxf

from backend.app.contratos.modelos import GeneralBomRow, GeneralDerivedArtifact


_STATE_ES = {
    "observed": "observado",
    "derived": "derivado",
    "hypothesis": "hipótesis",
    "confirmed": "confirmado",
    "unknown": "desconocido",
    "conflict": "conflicto",
}
_SVG_WIDTH = 1400
_TEXT_X = 470
_LINE_HEIGHT = 21
_WRAP_COLUMNS = 82


def _state(value: str) -> str:
    return _STATE_ES.get(value, value)


def _value(label: str, item: object) -> str:
    value = getattr(item, "value_mm")
    shown = f"{value:g} mm" if value is not None else "desconocido"
    return f"{label}: {shown} [{_state(getattr(item, 'state'))}]"


def _quantity(row: GeneralBomRow) -> str:
    shown = str(row.quantity.value) if row.quantity.value is not None else "desconocida"
    return f"Cantidad: {shown} [{_state(row.quantity.state)}]"


def _refs(row: GeneralBomRow) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *row.source_view_ids,
                *row.source_contour_ids,
                *row.source_dimension_ids,
                *row.source_document_refs,
                *row.source_observation_ids,
                *row.source_evidence_ids,
            )
        )
    )


def _wrapped(value: str, *, columns: int = _WRAP_COLUMNS) -> tuple[str, ...]:
    return tuple(
        wrap(
            value,
            width=columns,
            break_long_words=True,
            break_on_hyphens=False,
            replace_whitespace=False,
        )
        or ("",)
    )


def _occurrences(row: GeneralBomRow) -> tuple[tuple[str | None, str], ...]:
    values = tuple((item, "confirmed") for item in row.occurrence_ids) + tuple(
        (item, "provisional") for item in row.scenario_occurrence_ids
    )
    return values or ((None, "unknown"),)


def _title(row: GeneralBomRow, occurrence_id: str | None, status: str) -> str:
    if status == "confirmed":
        occurrence = f"Ocurrencia física: {occurrence_id} [confirmada]"
    elif status == "provisional":
        occurrence = f"Escenario provisional: {occurrence_id} [hipótesis]"
    else:
        occurrence = "Sin ocurrencia física materializada"
    return f"{row.label} · {occurrence}"


def _display_lines(
    row: GeneralBomRow, occurrence_id: str | None, status: str
) -> tuple[str, ...]:
    lines = [*_wrapped(_title(row, occurrence_id, status))]
    lines.extend(
        (
            _value("Largo", row.length),
            _value("Ancho", row.width),
            _value("Espesor", row.thickness),
            _quantity(row),
        )
    )
    if row.length.value_mm is None or row.width.value_mm is None:
        lines.append("Geometría no dibujada: falta largo o ancho")
    else:
        lines.append("Contorno esquemático sin colocación y no a escala de lámina")
    references = _refs(row)
    if references:
        lines.append(
            f"Procedencia: {len(references)} referencias; detalle íntegro en metadatos"
        )
    else:
        lines.append("Referencias de procedencia: ninguna")
    return tuple(lines)


def _metadata(rows: tuple[GeneralBomRow, ...]) -> str:
    values = []
    for row in rows:
        values.append(
            {
                "component_id": row.component_id,
                "label": row.label,
                "occurrence_ids": list(row.occurrence_ids),
                "scenario_occurrence_ids": list(row.scenario_occurrence_ids),
                "occurrence_status": row.occurrence_status,
                "quantity_state": row.quantity.state,
                "source_view_ids": list(row.source_view_ids),
                "source_contour_ids": list(row.source_contour_ids),
                "source_dimension_ids": list(row.source_dimension_ids),
                "source_document_refs": list(row.source_document_refs),
                "source_observation_ids": list(row.source_observation_ids),
                "source_evidence_ids": list(row.source_evidence_ids),
                "authority": "schematic_unplaced_not_manufacturing_ready",
            }
        )
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


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


def _outline_size(row: GeneralBomRow) -> tuple[float, float] | None:
    if row.length.value_mm is None or row.width.value_mm is None:
        return None
    scale = min(360.0 / row.length.value_mm, 150.0 / row.width.value_mm)
    return row.length.value_mm * scale, row.width.value_mm * scale


def _exact_outline_mm(row: GeneralBomRow) -> tuple[float, float] | None:
    if row.length.value_mm is None or row.width.value_mm is None:
        return None
    return float(row.length.value_mm), float(row.width.value_mm)


def _svg(rows: tuple[GeneralBomRow, ...]) -> bytes:
    blocks = []
    y = 90.0
    for row in rows:
        references = " · ".join(_refs(row)) or "ninguna"
        for occurrence_id, status in _occurrences(row):
            lines = _display_lines(row, occurrence_id, status)
            block_height = max(190.0, 35.0 + len(lines) * _LINE_HEIGHT)
            blocks.append((row, occurrence_id, status, references, lines, y))
            y += block_height + 24.0
    height = max(260.0, y + 30.0)
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_SVG_WIDTH}" '
            f'height="{height:g}" viewBox="0 0 {_SVG_WIDTH} {height:g}" '
            'data-authority="esquema_sin_colocacion_no_fabricacion">'
        ),
        '<metadata id="provenance">' + escape(_metadata(rows)) + "</metadata>",
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<g font-family="Arial, sans-serif" font-size="16" fill="#17202a">',
        '<text x="30" y="36" font-size="19" font-weight="700">ESQUEMA PROVISIONAL · SIN COLOCACIÓN VALIDADA · NO APTO PARA FABRICACIÓN</text>',
        '<text x="30" y="62" font-size="14">Las dimensiones escritas mandan; el contorno es solo una ayuda visual y no está a escala de lámina.</text>',
    ]
    for row, occurrence_id, status, references, lines, block_y in blocks:
        parts.append(
            f'<g class="component" data-component-id="{escape(row.component_id)}" '
            f'data-occurrence-status="{status}">'
        )
        parts.append(
            "<desc>"
            + escape(
                f"component_id={row.component_id}; occurrence_id={occurrence_id}; "
                f"status={status}; source_refs={references}"
            )
            + "</desc>"
        )
        outline = _outline_size(row)
        if outline is not None:
            width, outline_height = outline
            parts.append(
                f'<rect class="component-outline" x="30" y="{block_y:g}" '
                f'width="{width:g}" height="{outline_height:g}" fill="#f8fafc" '
                'stroke="#263238" stroke-width="2"/>'
            )
        text_x = _TEXT_X if outline is not None else 30
        for index, line in enumerate(lines):
            parts.append(
                f'<text x="{text_x}" y="{block_y + 19 + index * _LINE_HEIGHT:g}" '
                f'stroke="none">{escape(line)}</text>'
            )
        parts.append("</g>")
    parts.append("</g></svg>")
    return "".join(parts).encode("utf-8")


def _dxf(rows: tuple[GeneralBomRow, ...]) -> bytes:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4
    document.layers.add("SCHEMATIC_UNPLACED", color=7)
    document.layers.add("ANNOTATIONS", color=3)
    provenance_layer = document.layers.add("PROVENANCE", color=8)
    provenance_layer.off()
    modelspace = document.modelspace()
    modelspace.add_text(
        "ESQUEMA PROVISIONAL - SIN COLOCACION VALIDADA - NO APTO PARA FABRICACION",
        height=6,
        dxfattribs={"layer": "ANNOTATIONS"},
    ).set_placement((0, 0))
    y = -20.0
    for row in rows:
        for occurrence_id, status in _occurrences(row):
            lines = _display_lines(row, occurrence_id, status)
            outline = _exact_outline_mm(row)
            if outline is not None:
                length_mm, width_mm = outline
                modelspace.add_lwpolyline(
                    (
                        (0, y),
                        (length_mm, y),
                        (length_mm, y - width_mm),
                        (0, y - width_mm),
                    ),
                    close=True,
                    dxfattribs={"layer": "SCHEMATIC_UNPLACED"},
                )
            text_x = outline[0] + 50.0 if outline is not None else 0.0
            modelspace.add_mtext(
                "\\P".join(lines),
                dxfattribs={"char_height": 5, "width": 340, "layer": "ANNOTATIONS"},
            ).set_location((text_x, y))
            # One MTEXT per exact source reference preserves the full token while
            # the entity width lets CAD viewers wrap it without truncation.
            reference_y = y - (len(lines) + 1) * 7
            for index, reference in enumerate(_refs(row), start=1):
                modelspace.add_mtext(
                    f"Referencia {index}: {reference}",
                    dxfattribs={"char_height": 4, "width": 340, "layer": "PROVENANCE"},
                ).set_location((text_x, reference_y))
                reference_y -= 12
            geometry_height = outline[1] + 100.0 if outline is not None else 0.0
            y -= max(
                190.0,
                geometry_height,
                (len(lines) + len(_refs(row)) + 3) * 10.0,
            )
    stream = StringIO()
    document.write(stream)
    return stream.getvalue().encode("utf-8")


def render_general_component_drawings(
    rows: tuple[GeneralBomRow, ...], *, review_revision: int
) -> tuple[GeneralDerivedArtifact, ...]:
    """Render readable, provenance-complete schematics without manufacturing authority."""

    reasons = _incomplete_reasons(rows)
    status = "incomplete" if reasons else "ready"
    return (
        GeneralDerivedArtifact(
            id=f"general-drawing-svg-r{review_revision}", kind="drawing_svg",
            status=status, review_revision=review_revision,
            filename=f"general-components-r{review_revision}.svg", media_type="image/svg+xml",
            incomplete_reasons=reasons, content=_svg(rows),
        ),
        GeneralDerivedArtifact(
            id=f"general-drawing-dxf-r{review_revision}", kind="drawing_dxf",
            status=status, review_revision=review_revision,
            filename=f"general-components-r{review_revision}.dxf", media_type="application/dxf",
            incomplete_reasons=reasons, content=_dxf(rows),
        ),
    )
