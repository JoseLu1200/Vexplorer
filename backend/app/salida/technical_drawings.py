"""Deterministic SVG and DXF renderers for reviewed table drawing plans.

The input plan is the sole source of geometry and provenance. This module only
maps its explicit primitives to presentation formats; it does not evaluate
bindings, expand quantities, place occurrences or infer missing dimensions.
"""
from __future__ import annotations

import json
from io import StringIO
from math import atan2, degrees, hypot
import re
from uuid import NAMESPACE_URL, uuid5
from xml.etree import ElementTree as ET

import ezdxf
from ezdxf.document import CREATED_BY_EZDXF, WRITTEN_BY_EZDXF
from ezdxf.lldxf.tagwriter import TagWriter

from backend.app.contratos.modelos import (
    Point2D,
    TableDrawingArtifactData,
    TableDrawingExports,
    TableDrawingPlan,
    TableDrawingPrimitive,
    TableSheetPlan,
)


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

_STATE_STYLE = {
    "observed": ("#2563eb", 5, "observado"),
    "calculated": ("#0f766e", 3, "calculado"),
    "proposed": ("#d97706", 30, "hipotesis"),
    "confirmed": ("#7c3aed", 6, "confirmado"),
    "unknown": ("#6b7280", 8, "desconocido"),
    "conflict": ("#b91c1c", 1, "conflicto"),
}
_DXF_LAYER = {state: f"VX_{state.upper()}" for state in _STATE_STYLE}
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_DXF_XDATA_APPID = "VEXPLORER"
_DXF_XDATA_CHUNK_SIZE = 240


def _svg_tag(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def _format_mm(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _filename(sheet_id: str, revision: int, extension: str) -> str:
    slug = _SAFE_FILENAME.sub("-", sheet_id).strip("-._") or "sheet"
    return f"{slug}-r{revision}.{extension}"


def _presentation_text(primitive: TableDrawingPrimitive) -> str:
    """Keep dense provenance machine-readable without printing it beyond the sheet."""
    value = primitive.text or "?"
    if not value.upper().startswith("PROVENANCE="):
        return value
    reference_count = len(primitive.dependency_refs)
    if reference_count == 0:
        reference_count = len(tuple(item for item in value.partition("=")[2].split(",") if item))
    return f"PROCEDENCIA: {reference_count} referencias · detalle completo en metadatos"


def _text_metadata(primitive: TableDrawingPrimitive) -> str:
    return json.dumps(
        {
            "dependency_refs": list(primitive.dependency_refs),
            "primitive_id": primitive.id,
            "text": primitive.text,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _geometry_bounds(sheet: TableSheetPlan) -> tuple[float, float, float, float]:
    points = [point for primitive in sheet.primitives for point in primitive.points_mm]
    if not points:
        return (0.0, 0.0, 100.0, 100.0)
    min_x = min(point.x for point in points)
    min_y = min(point.y for point in points)
    max_x = max(point.x for point in points)
    max_y = max(point.y for point in points)
    if min_x == max_x:
        max_x += 1.0
    if min_y == max_y:
        max_y += 1.0
    return min_x, min_y, max_x, max_y


def _dimension_points(primitive: TableDrawingPrimitive) -> tuple[Point2D, Point2D, Point2D, Point2D]:
    """Return measurement and dimension-line endpoints from an explicit anchor."""
    p1, p2, anchor = primitive.points_mm
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    length = hypot(dx, dy)
    if length == 0:
        # The contract validates arity; a zero span remains a malformed plan.
        raise ValueError(f"zero_length_dimension:{primitive.id}")
    ux, uy = dx / length, dy / length

    def project(point: Point2D) -> Point2D:
        distance = (point.x - anchor.x) * ux + (point.y - anchor.y) * uy
        return Point2D(x=anchor.x + distance * ux, y=anchor.y + distance * uy)

    return p1, p2, project(p1), project(p2)


def _svg_line(
    parent: ET.Element,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str,
    *,
    stroke_width: float,
    dash_pattern: str,
    dashed: bool = False,
) -> None:
    attributes = {
        "x1": _format_mm(start[0]),
        "y1": _format_mm(start[1]),
        "x2": _format_mm(end[0]),
        "y2": _format_mm(end[1]),
        "stroke": color,
        "stroke-width": _format_mm(stroke_width),
    }
    if dashed:
        attributes["stroke-dasharray"] = dash_pattern
    ET.SubElement(parent, _svg_tag("line"), attributes)


def _render_svg(plan: TableDrawingPlan, sheet: TableSheetPlan) -> bytes:
    min_x, min_y, max_x, max_y = _geometry_bounds(sheet)
    span_x = max_x - min_x
    span_y = max_y - min_y
    drawing_span = max(span_x, span_y)
    font_scale = max(1.0, drawing_span / 900.0)
    stroke_width = 1.5 * font_scale
    dash_pattern = f"{_format_mm(6 * font_scale)} {_format_mm(4 * font_scale)}"
    margin = max(20.0 * font_scale, drawing_span * 0.05)
    header = 60.0 * font_scale
    footer = (90.0 + len(sheet.warnings) * 14.0) * font_scale
    width = span_x + margin * 2
    height = span_y + margin * 2 + header + footer
    intrinsic_width = 1600
    intrinsic_height = max(1, round(intrinsic_width * height / width))

    root = ET.Element(
        _svg_tag("svg"),
        {
            "viewBox": f"0 0 {_format_mm(width)} {_format_mm(height)}",
            "width": str(intrinsic_width),
            "height": str(intrinsic_height),
            "preserveAspectRatio": "xMidYMid meet",
            "role": "img",
            "aria-label": sheet.title,
            "data-sheet-id": sheet.sheet_id,
            "data-result-revision": str(plan.result_revision),
            "data-program-hash": plan.program_hash,
            "data-coordinate-unit": plan.coordinate_unit,
        },
    )
    metadata = ET.SubElement(root, _svg_tag("metadata"))
    metadata.text = (
        f"drawing_id={plan.drawing_id};result_revision={plan.result_revision};"
        f"program_hash={plan.program_hash};sheet_id={sheet.sheet_id}"
    )
    title = ET.SubElement(root, _svg_tag("title"))
    title.text = sheet.title
    description = ET.SubElement(root, _svg_tag("desc"))
    description.text = "Plano derivado; no validado para fabricacion, resistencia ni uniones."

    ET.SubElement(
        root,
        _svg_tag("rect"),
        {"x": "0", "y": "0", "width": _format_mm(width), "height": _format_mm(height), "fill": "#ffffff"},
    )
    heading = ET.SubElement(
        root,
        _svg_tag("text"),
        {
            "x": _format_mm(margin),
            "y": _format_mm(margin),
            "fill": "#111827",
            "font-size": _format_mm(18 * font_scale),
            "font-family": "sans-serif",
        },
    )
    heading.text = sheet.title
    notice = ET.SubElement(
        root,
        _svg_tag("text"),
        {
            "x": _format_mm(margin),
            "y": _format_mm(margin + 22 * font_scale),
            "fill": "#b45309",
            "font-size": _format_mm(11 * font_scale),
            "font-family": "sans-serif",
        },
    )
    notice.text = "PLANO DERIVADO - NO VALIDADO PARA FABRICACION"

    def map_point(point: Point2D) -> tuple[float, float]:
        return point.x - min_x + margin, max_y - point.y + margin + header

    geometry = ET.SubElement(root, _svg_tag("g"), {"data-layer": "drawing"})
    for primitive in sheet.primitives:
        color, _, _ = _STATE_STYLE[primitive.state]
        group = ET.SubElement(
            geometry,
            _svg_tag("g"),
            {
                "data-primitive-id": primitive.id,
                "data-state": primitive.state,
                "data-dependencies": " ".join(primitive.dependency_refs),
                **({"data-full-text": primitive.text} if primitive.text is not None else {}),
            },
        )
        mapped = [map_point(point) for point in primitive.points_mm]
        dashed = primitive.state in {"proposed", "unknown", "conflict"}
        if primitive.kind == "line":
            ET.SubElement(
                group,
                _svg_tag("polyline"),
                {
                    "points": " ".join(f"{_format_mm(x)},{_format_mm(y)}" for x, y in mapped),
                    "fill": "none",
                    "stroke": color,
                    "stroke-width": _format_mm(stroke_width),
                    **({"stroke-dasharray": dash_pattern} if dashed else {}),
                },
            )
        elif primitive.kind == "rect":
            (x1, y1), (x2, y2) = mapped
            ET.SubElement(
                group,
                _svg_tag("rect"),
                {
                    "x": _format_mm(min(x1, x2)),
                    "y": _format_mm(min(y1, y2)),
                    "width": _format_mm(abs(x2 - x1)),
                    "height": _format_mm(abs(y2 - y1)),
                    "fill": "none",
                    "stroke": color,
                    "stroke-width": _format_mm(stroke_width),
                    **({"stroke-dasharray": dash_pattern} if dashed else {}),
                },
            )
        elif primitive.kind == "dimension":
            p1, p2, dim1, dim2 = _dimension_points(primitive)
            mp1, mp2, md1, md2 = map_point(p1), map_point(p2), map_point(dim1), map_point(dim2)
            _svg_line(
                group,
                mp1,
                md1,
                color,
                stroke_width=stroke_width,
                dash_pattern=dash_pattern,
                dashed=dashed,
            )
            _svg_line(
                group,
                mp2,
                md2,
                color,
                stroke_width=stroke_width,
                dash_pattern=dash_pattern,
                dashed=dashed,
            )
            _svg_line(
                group,
                md1,
                md2,
                color,
                stroke_width=stroke_width,
                dash_pattern=dash_pattern,
                dashed=dashed,
            )
            label = primitive.text or (f"{_format_mm(primitive.value_mm)} mm" if primitive.value_mm is not None else "?")
            text = ET.SubElement(
                group,
                _svg_tag("text"),
                {
                    "x": _format_mm((md1[0] + md2[0]) / 2),
                    "y": _format_mm((md1[1] + md2[1]) / 2 - 5),
                    "fill": color,
                    "font-size": _format_mm(11 * font_scale),
                    "font-family": "sans-serif",
                    "text-anchor": "middle",
                },
            )
            text.text = label
        else:
            x, y = mapped[0]
            text = ET.SubElement(
                group,
                _svg_tag("text"),
                {
                    "x": _format_mm(x),
                    "y": _format_mm(y),
                    "fill": color,
                    "font-size": _format_mm(12 * font_scale),
                    "font-family": "sans-serif",
                },
            )
            text.text = _presentation_text(primitive)

    legend_y = height - footer + 20 * font_scale
    legend = ET.SubElement(root, _svg_tag("g"), {"data-layer": "legend"})
    for index, (state, (color, _, label)) in enumerate(_STATE_STYLE.items()):
        x = margin + (index % 3) * max(150.0 * font_scale, span_x / 3)
        y = legend_y + (index // 3) * 24 * font_scale
        ET.SubElement(
            legend,
            _svg_tag("rect"),
            {
                "x": _format_mm(x),
                "y": _format_mm(y - 10 * font_scale),
                "width": _format_mm(14 * font_scale),
                "height": _format_mm(4 * font_scale),
                "fill": color,
            },
        )
        item = ET.SubElement(
            legend,
            _svg_tag("text"),
            {
                "x": _format_mm(x + 20 * font_scale),
                "y": _format_mm(y),
                "fill": "#374151",
                "font-size": _format_mm(10 * font_scale),
                "font-family": "sans-serif",
            },
        )
        item.text = label
    warning_y = legend_y + 60 * font_scale
    for index, warning in enumerate(sheet.warnings):
        item = ET.SubElement(
            root,
            _svg_tag("text"),
            {
                "x": _format_mm(margin),
                "y": _format_mm(warning_y + index * 14 * font_scale),
                "fill": "#b91c1c",
                "font-size": _format_mm(10 * font_scale),
                "font-family": "sans-serif",
            },
        )
        item.text = f"AVISO: {warning}"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=True)


def _set_deterministic_header(
    document: ezdxf.document.Drawing,
    plan: TableDrawingPlan,
    sheet: TableSheetPlan,
) -> None:
    identity = f"vexplorer:{plan.program_hash}:{plan.result_revision}:{sheet.sheet_id}"
    document.header["$TDCREATE"] = 2451544.5
    document.header["$TDUPDATE"] = 2451544.5
    document.header["$TDINDWG"] = 0.0
    document.header["$FINGERPRINTGUID"] = "{" + str(uuid5(NAMESPACE_URL, identity)).upper() + "}"
    document.header["$VERSIONGUID"] = "{" + str(uuid5(NAMESPACE_URL, identity + ":version")).upper() + "}"


def _render_dxf(plan: TableDrawingPlan, sheet: TableSheetPlan) -> bytes:
    document = ezdxf.new("R2018", setup=True)
    document.units = 4
    _set_deterministic_header(document, plan, sheet)
    document.appids.add(_DXF_XDATA_APPID)
    for state, (_, color, _) in _STATE_STYLE.items():
        document.layers.add(_DXF_LAYER[state], color=color)
    document.layers.add("VX_METADATA", color=7)
    modelspace = document.modelspace()
    min_x, min_y, max_x, max_y = _geometry_bounds(sheet)
    span = max(max_x - min_x, max_y - min_y)
    text_height = max(2.5, min(12.0, span * 0.015))

    metadata_text = (
        f"VEXPLORER TECHNICAL DRAWING\\Ptitle={sheet.title}"
        f"\\Psheet_id={sheet.sheet_id}"
        f"\\Presult_revision={plan.result_revision}\\Pprogram_hash={plan.program_hash}"
        "\\PPLANO DERIVADO - NO VALIDADO PARA FABRICACION"
    )
    modelspace.add_mtext(
        metadata_text,
        dxfattribs={"insert": (min_x, max_y + text_height * 8), "char_height": text_height, "layer": "VX_METADATA"},
    )
    modelspace.add_mtext(
        "LEYENDA: OBSERVADO | CALCULADO | HIPOTESIS | CONFIRMADO | DESCONOCIDO | CONFLICTO",
        dxfattribs={"insert": (min_x, min_y - text_height * 8), "char_height": text_height, "layer": "VX_METADATA"},
    )
    if sheet.warnings:
        modelspace.add_mtext(
            "\\P".join(f"AVISO: {warning}" for warning in sheet.warnings),
            dxfattribs={"insert": (min_x, min_y - text_height * 12), "char_height": text_height, "layer": "VX_METADATA"},
        )

    for primitive in sheet.primitives:
        layer = _DXF_LAYER[primitive.state]
        points = [(point.x, point.y) for point in primitive.points_mm]
        if primitive.kind == "line":
            if len(points) == 2:
                modelspace.add_line(points[0], points[1], dxfattribs={"layer": layer})
            else:
                modelspace.add_lwpolyline(points, dxfattribs={"layer": layer})
        elif primitive.kind == "rect":
            (x1, y1), (x2, y2) = points
            modelspace.add_lwpolyline(
                ((x1, y1), (x2, y1), (x2, y2), (x1, y2)),
                close=True,
                dxfattribs={"layer": layer},
            )
        elif primitive.kind == "dimension":
            p1, p2, anchor = points
            angle = degrees(atan2(p2[1] - p1[1], p2[0] - p1[0]))
            label = f"{_format_mm(primitive.value_mm)} mm" if primitive.value_mm is not None else "??"
            dimension = modelspace.add_linear_dim(
                base=anchor,
                p1=p1,
                p2=p2,
                text=label,
                angle=angle,
                dxfattribs={"layer": layer},
            )
            dimension.render()
        else:
            text_entity = modelspace.add_text(
                _presentation_text(primitive),
                dxfattribs={"insert": points[0], "height": text_height, "layer": layer},
            )
            metadata_payload = _text_metadata(primitive)
            text_entity.set_xdata(
                _DXF_XDATA_APPID,
                [
                    (1000, metadata_payload[index:index + _DXF_XDATA_CHUNK_SIZE])
                    for index in range(0, len(metadata_payload), _DXF_XDATA_CHUNK_SIZE)
                ],
            )

    # ``Drawing.write()`` commits pending entities but also injects the current
    # timestamp and a random version GUID. Commit once into a scratch stream,
    # then replace only that volatile library metadata and export the already
    # updated sections without another metadata mutation.
    document.write(StringIO(), fmt="asc")
    _set_deterministic_header(document, plan, sheet)
    ezdxf_metadata = document.ezdxf_metadata()
    ezdxf_metadata[CREATED_BY_EZDXF] = "ezdxf deterministic export"
    ezdxf_metadata[WRITTEN_BY_EZDXF] = "ezdxf deterministic export"
    stream = StringIO(newline="\n")
    document.export_sections(
        TagWriter(stream, write_handles=True, dxfversion=document.dxfversion)
    )
    return document.encode(stream.getvalue())


def render_table_drawings(plan: TableDrawingPlan) -> TableDrawingExports:
    """Render every explicit sheet as deterministic SVG and re-openable DXF bytes."""
    sheet_ids = [sheet.sheet_id for sheet in plan.sheets]
    if len(sheet_ids) != len(set(sheet_ids)):
        raise ValueError("duplicate_table_sheet_id")
    artifacts: list[TableDrawingArtifactData] = []
    for sheet in plan.sheets:
        artifacts.append(
            TableDrawingArtifactData(
                sheet_id=sheet.sheet_id,
                format="svg",
                media_type="image/svg+xml",
                filename=_filename(sheet.sheet_id, plan.result_revision, "svg"),
                content=_render_svg(plan, sheet),
            )
        )
        artifacts.append(
            TableDrawingArtifactData(
                sheet_id=sheet.sheet_id,
                format="dxf",
                media_type="application/dxf",
                filename=_filename(sheet.sheet_id, plan.result_revision, "dxf"),
                content=_render_dxf(plan, sheet),
            )
        )
    return TableDrawingExports(
        result_revision=plan.result_revision,
        program_hash=plan.program_hash,
        artifacts=tuple(artifacts),
    )
