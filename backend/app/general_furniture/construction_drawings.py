"""Pure SVG/DXF rendering for explicit general-construction sheet plans.

This module renders only primitives already present in the plan.  It never
infers a part outline, placement, dimension or construction detail.
"""
from __future__ import annotations

import json
from io import StringIO
from math import hypot
import re
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET

import ezdxf

from backend.app.contratos.modelos import GeneralDerivedArtifact

if TYPE_CHECKING:
    from backend.app.contratos.modelos import GeneralSheetPlan


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

_STYLE = {
    "observed": ("#111827", None, "OBSERVADO"),
    "deduced": ("#2563eb", "10 4 2 4", "DEDUCIDO"),
    "estimated": ("#d97706", "9 6", "ESTIMADO"),
    "unknown": ("#6b7280", "3 5", "DESCONOCIDO"),
    "conflict": ("#b91c1c", "2 3", "CONFLICTO"),
}
_DXF_LAYER = {state: f"VX_{state.upper()}" for state in _STYLE}
_DXF_PRESENTATION = {
    "observed": (7, "Continuous"),
    "deduced": (5, "CENTER"),
    "estimated": (30, "DASHED"),
    "unknown": (8, "DOT"),
    "conflict": (1, "DASHDOT"),
}
_APPID = "VEXPLORER"
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _tag(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def _number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _ascii_dxf(value: str) -> str:
    return (
        value.replace("≈", "~")
        .replace("–", "-")
        .replace("×", "x")
        .replace("·", "-")
    )


def _bounds(sheet: Any) -> tuple[float, float, float, float]:
    points = [point for primitive in sheet.primitives for point in primitive.points_mm]
    if points:
        min_x = min(point.x for point in points)
        min_y = min(point.y for point in points)
        max_x = max(point.x for point in points)
        max_y = max(point.y for point in points)
    else:
        min_x, min_y, max_x, max_y = 0.0, 0.0, 100.0, 100.0
    for primitive in sheet.primitives:
        if not primitive.text or not primitive.points_mm:
            continue
        font_size = 12.0
        text_width = len(primitive.text) * font_size * 0.6
        if primitive.kind == "dimension":
            _, _, dim1, dim2 = _dimension_geometry(primitive)
            anchor_x = (dim1[0] + dim2[0]) / 2
            anchor_y = (dim1[1] + dim2[1]) / 2 - 6
            min_x = min(min_x, anchor_x - text_width / 2)
            max_x = max(max_x, anchor_x + text_width / 2)
        else:
            anchor = primitive.points_mm[-1] if primitive.kind == "detail_callout" else primitive.points_mm[0]
            anchor_x, anchor_y = anchor.x, anchor.y - 5 if primitive.kind == "detail_callout" else anchor.y
            max_x = max(max_x, anchor_x + text_width)
        min_y = min(min_y, anchor_y - font_size)
        max_y = max(max_y, anchor_y + font_size * 0.3)

    notice = "PROPUESTA CONSTRUCTIVA · COTAS ESTIMADAS SEÑALADAS"
    required_width = max(
        700.0,
        len(sheet.title) * 18.0 * 0.6,
        len(notice) * 12.0 * 0.6,
        *(len(f"RESTRICCIÓN: {warning.message}") * 11.0 * 0.6 for warning in sheet.warnings),
    )
    max_x = max(max_x, min_x + required_width)
    return min_x, min_y, max(max_x, min_x + 1.0), max(max_y, min_y + 1.0)


def _dimension_geometry(primitive: Any) -> tuple[Any, Any, tuple[float, float], tuple[float, float]]:
    p1, p2, anchor = primitive.points_mm
    dx, dy = p2.x - p1.x, p2.y - p1.y
    length = hypot(dx, dy)
    if length == 0:
        raise ValueError(f"zero_length_dimension:{primitive.id}")
    ux, uy = dx / length, dy / length

    def project(point: Any) -> tuple[float, float]:
        distance = (point.x - anchor.x) * ux + (point.y - anchor.y) * uy
        return anchor.x + distance * ux, anchor.y + distance * uy

    return p1, p2, project(p1), project(p2)


def _svg_line(parent: ET.Element, start: tuple[float, float], end: tuple[float, float], **extra: str) -> None:
    ET.SubElement(
        parent,
        _tag("line"),
        {
            "x1": _number(start[0]),
            "y1": _number(start[1]),
            "x2": _number(end[0]),
            "y2": _number(end[1]),
            **extra,
        },
    )


def render_construction_sheet_svg(sheet: "GeneralSheetPlan") -> bytes:
    """Render a sheet without changing its explicit millimetre geometry."""
    min_x, min_y, max_x, max_y = _bounds(sheet)
    span = max(max_x - min_x, max_y - min_y)
    margin = max(30.0, span * 0.06)
    header = max(70.0, span * 0.08)
    footer = max(90.0 + len(sheet.warnings) * 18.0, span * 0.12)
    view_x = min_x - margin
    view_y = min_y - margin - header
    width = max_x - min_x + 2 * margin
    height = max_y - min_y + 2 * margin + header + footer
    root = ET.Element(
        _tag("svg"),
        {
            "viewBox": " ".join(_number(value) for value in (view_x, view_y, width, height)),
            "width": "1600",
            "height": str(max(1, round(1600 * height / width))),
            "data-coordinate-unit": "mm",
            "data-sheet-id": sheet.sheet_id,
            "data-sheet-kind": sheet.kind,
            **({"data-piece-id": sheet.piece_id} if sheet.piece_id is not None else {}),
        },
    )
    metadata = ET.SubElement(root, _tag("metadata"))
    metadata.text = json.dumps(
        {
            "authority": "provisional_not_manufacturing",
            "sheet_id": sheet.sheet_id,
            "piece_id": sheet.piece_id,
            "source_refs": sorted(
                {reference for primitive in sheet.primitives for reference in primitive.source_refs}
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    title = ET.SubElement(root, _tag("title"))
    title.text = sheet.title
    heading = ET.SubElement(
        root,
        _tag("text"),
        {"x": _number(min_x), "y": _number(view_y + 24), "font-size": "18", "fill": "#111827"},
    )
    heading.text = sheet.title
    notice = ET.SubElement(
        root,
        _tag("text"),
        {"x": _number(min_x), "y": _number(view_y + 48), "font-size": "12", "fill": "#b45309"},
    )
    notice.text = "PROPUESTA CONSTRUCTIVA · COTAS ESTIMADAS SEÑALADAS"

    drawing = ET.SubElement(root, _tag("g"), {"data-layer": "construction"})
    for index, primitive in enumerate(sheet.primitives):
        primitive_id = getattr(primitive, "id", f"{sheet.sheet_id}:{index + 1}")
        color, dash, _ = _STYLE[primitive.state]
        common = {"fill": "none", "stroke": color, "stroke-width": "1.5"}
        if dash:
            common["stroke-dasharray"] = dash
        group = ET.SubElement(
            drawing,
            _tag("g"),
            {
                "data-primitive-id": primitive_id,
                "data-kind": primitive.kind,
                "data-state": primitive.state,
                "data-source-refs": " ".join(primitive.source_refs),
            },
        )
        points = [(point.x, point.y) for point in primitive.points_mm]
        if primitive.kind == "line":
            for start, end in zip(points, points[1:]):
                _svg_line(group, start, end, **common)
        elif primitive.kind == "polyline":
            ET.SubElement(
                group,
                _tag("polyline"),
                {"points": " ".join(f"{_number(x)},{_number(y)}" for x, y in points), **common},
            )
        elif primitive.kind == "circle":
            center, edge = points
            ET.SubElement(
                group,
                _tag("circle"),
                {
                    "cx": _number(center[0]),
                    "cy": _number(center[1]),
                    "r": _number(hypot(edge[0] - center[0], edge[1] - center[1])),
                    **common,
                },
            )
        elif primitive.kind == "dimension":
            p1, p2, dim1, dim2 = _dimension_geometry(primitive)
            _svg_line(group, (p1.x, p1.y), dim1, **common)
            _svg_line(group, (p2.x, p2.y), dim2, **common)
            _svg_line(group, dim1, dim2, **common)
            dx, dy = dim2[0] - dim1[0], dim2[1] - dim1[1]
            dimension_length = hypot(dx, dy)
            tick_x, tick_y = -dy / dimension_length * 5, dx / dimension_length * 5
            for point in (dim1, dim2):
                _svg_line(
                    group,
                    (point[0] - tick_x, point[1] - tick_y),
                    (point[0] + tick_x, point[1] + tick_y),
                    **(common | {"data-role": "dimension-terminator"}),
                )
            label = ET.SubElement(
                group,
                _tag("text"),
                {
                    "x": _number((dim1[0] + dim2[0]) / 2),
                    "y": _number((dim1[1] + dim2[1]) / 2 - 6),
                    "font-size": "12",
                    "text-anchor": "middle",
                    "fill": color,
                    "stroke": "none",
                },
            )
            label.text = primitive.text
        elif primitive.kind == "detail_callout":
            target = points[0]
            label_point = points[-1] if len(points) > 1 else (target[0] + 60, target[1] + 40)
            route = points if len(points) > 1 else (target, label_point)
            for start, end in zip(route, route[1:]):
                _svg_line(
                    group,
                    start,
                    end,
                    **(common | {"data-role": "detail-leader"}),
                )
            label = ET.SubElement(
                group,
                _tag("text"),
                {
                    "x": _number(label_point[0]),
                    "y": _number(label_point[1] - 5),
                    "font-size": "12",
                    "fill": color,
                    "stroke": "none",
                },
            )
            label.text = primitive.text
        else:
            x, y = points[0]
            label = ET.SubElement(
                group,
                _tag("text"),
                {"x": _number(x), "y": _number(y), "font-size": "12", "fill": color, "stroke": "none"},
            )
            label.text = primitive.text

    legend_y = max_y + margin + 20
    for index, (state, (color, dash, label)) in enumerate(_STYLE.items()):
        x = min_x + index * max(120.0, width / len(_STYLE))
        line_attributes = {"stroke": color, "stroke-width": "2"}
        if dash:
            line_attributes["stroke-dasharray"] = dash
        _svg_line(root, (x, legend_y), (x + 34, legend_y), **line_attributes)
        text = ET.SubElement(
            root,
            _tag("text"),
            {"x": _number(x + 40), "y": _number(legend_y + 4), "font-size": "10", "fill": color},
        )
        text.text = label
    for index, warning in enumerate(sheet.warnings):
        text = ET.SubElement(
            root,
            _tag("text"),
            {
                "x": _number(min_x),
                "y": _number(legend_y + 30 + index * 16),
                "font-size": "11",
                "fill": "#92400e",
                "data-warning-code": warning.code,
            },
        )
        text.text = f"RESTRICCIÓN: {warning.message}"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _set_provenance(
    document: ezdxf.document.Drawing,
    entity: Any,
    primitive: Any,
    primitive_id: str,
) -> None:
    if _APPID not in document.appids:
        document.appids.add(_APPID)
    entity.set_xdata(
        _APPID,
        [(1000, primitive_id), (1000, primitive.state), *[(1000, ref) for ref in primitive.source_refs]],
    )


def render_construction_sheet_dxf(sheet: "GeneralSheetPlan") -> bytes:
    """Render explicit model-space geometry at exact millimetre dimensions."""
    document = ezdxf.new("R2010", setup=True)
    document.header["$INSUNITS"] = 4
    for state, (color, linetype) in _DXF_PRESENTATION.items():
        document.layers.add(_DXF_LAYER[state], color=color, linetype=linetype)
    document.layers.add("VX_PROVENANCE", color=8)
    document.layers.add("VX_NOTES", color=7)
    space = document.modelspace()
    for index, primitive in enumerate(sheet.primitives):
        primitive_id = getattr(primitive, "id", f"{sheet.sheet_id}:{index + 1}")
        layer = _DXF_LAYER[primitive.state]
        points = [(point.x, point.y) for point in primitive.points_mm]
        entities: list[Any] = []
        if primitive.kind == "line":
            entities.extend(space.add_line(start, end, dxfattribs={"layer": layer}) for start, end in zip(points, points[1:]))
        elif primitive.kind == "polyline":
            closed = len(points) > 2 and points[0] == points[-1]
            entities.append(space.add_lwpolyline(points[:-1] if closed else points, close=closed, dxfattribs={"layer": layer}))
        elif primitive.kind == "circle":
            center, edge = points
            entities.append(space.add_circle(center, hypot(edge[0] - center[0], edge[1] - center[1]), dxfattribs={"layer": layer}))
        elif primitive.kind == "dimension":
            p1, p2, dim1, dim2 = _dimension_geometry(primitive)
            dx, dy = dim2[0] - dim1[0], dim2[1] - dim1[1]
            dimension_length = hypot(dx, dy)
            tick_x, tick_y = -dy / dimension_length * 5, dx / dimension_length * 5
            entities.extend(
                (
                    space.add_line((p1.x, p1.y), dim1, dxfattribs={"layer": layer}),
                    space.add_line((p2.x, p2.y), dim2, dxfattribs={"layer": layer}),
                    space.add_line(dim1, dim2, dxfattribs={"layer": layer}),
                    space.add_line(
                        (dim1[0] - tick_x, dim1[1] - tick_y),
                        (dim1[0] + tick_x, dim1[1] + tick_y),
                        dxfattribs={"layer": layer},
                    ),
                    space.add_line(
                        (dim2[0] - tick_x, dim2[1] - tick_y),
                        (dim2[0] + tick_x, dim2[1] + tick_y),
                        dxfattribs={"layer": layer},
                    ),
                    space.add_text(
                        _ascii_dxf(primitive.text or "?"),
                        height=10,
                        dxfattribs={"layer": layer},
                    ).set_placement(((dim1[0] + dim2[0]) / 2, (dim1[1] + dim2[1]) / 2 + 5)),
                )
            )
        elif primitive.kind == "detail_callout":
            target = points[0]
            label_point = points[-1] if len(points) > 1 else (target[0] + 60, target[1] + 40)
            route = points if len(points) > 1 else (target, label_point)
            entities.extend(
                space.add_line(start, end, dxfattribs={"layer": layer})
                for start, end in zip(route, route[1:])
            )
            entities.append(space.add_text(
                    _ascii_dxf(primitive.text or ""),
                    height=10,
                    dxfattribs={"layer": layer},
                ).set_placement((label_point[0], label_point[1] - 5)))
        else:
            entities.append(
                space.add_text(
                    _ascii_dxf(primitive.text or ""),
                    height=10,
                    dxfattribs={"layer": layer},
                ).set_placement(points[0])
            )
        for entity in entities:
            _set_provenance(document, entity, primitive, primitive_id)
    min_x, _, _, max_y = _bounds(sheet)
    header_y = max_y + 160 + len(sheet.warnings) * 16
    space.add_text(sheet.title, height=18, dxfattribs={"layer": "VX_NOTES"}).set_placement((min_x, header_y))
    space.add_text(
        "PROPUESTA CONSTRUCTIVA - COTAS ESTIMADAS SENALADAS",
        height=10,
        dxfattribs={"layer": "VX_NOTES"},
    ).set_placement((min_x, header_y - 24))
    for index, state in enumerate(("observed", "deduced", "estimated", "unknown", "conflict")):
        layer = _DXF_LAYER[state]
        label = _STYLE[state][2]
        y = header_y - 50 - index * 18
        space.add_line((min_x, y), (min_x + 35, y), dxfattribs={"layer": layer})
        space.add_text(label, height=8, dxfattribs={"layer": layer}).set_placement((min_x + 42, y - 3))
    warning_y = header_y - 50 - len(_STYLE) * 18 - 10
    for index, warning in enumerate(sheet.warnings):
        space.add_text(
            _ascii_dxf(f"RESTRICCION: {warning.message}"),
            height=8,
            dxfattribs={"layer": "VX_NOTES"},
        ).set_placement((min_x, warning_y - index * 16))
    provenance = json.dumps(
        {
            "authority": "provisional_not_manufacturing",
            "sheet_id": sheet.sheet_id,
            "piece_id": sheet.piece_id,
            "title": sheet.title,
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    space.add_text(provenance, height=1, dxfattribs={"layer": "VX_PROVENANCE"}).set_placement((0, 0))
    document.layers.get("VX_PROVENANCE").dxf.flags = 1
    stream = StringIO()
    document.write(stream)
    return stream.getvalue().encode("utf-8")


def _filename(sheet: "GeneralSheetPlan", proposal_revision: int, review_revision: int, extension: str) -> str:
    label = "conjunto-propuesto" if sheet.kind == "assembly" else f"pieza-{sheet.piece_id}"
    slug = _SAFE_FILENAME.sub("-", label).strip("-._") or "plano"
    return f"{slug}-p{proposal_revision}-r{review_revision}.{extension}"


def render_construction_artifacts(plan: Any) -> tuple[GeneralDerivedArtifact, ...]:
    """Render both exact formats for every sheet in a snapshot-bound plan."""
    pieces = {piece.piece_id: piece for piece in plan.pieces}
    artifacts: list[GeneralDerivedArtifact] = []
    for sheet in plan.sheets:
        component_id = pieces[sheet.piece_id].component_id if sheet.piece_id in pieces else None
        blocking_reasons = tuple(
            warning.code
            for warning in sheet.warnings
            if warning.severity == "error" or warning.consequence == "blocks_fabrication"
        )
        status = "incomplete" if blocking_reasons else "ready"
        for extension, media_type, content in (
            ("svg", "image/svg+xml", render_construction_sheet_svg(sheet)),
            ("dxf", "application/dxf", render_construction_sheet_dxf(sheet)),
        ):
            kind = (
                f"construction_overview_{extension}"
                if sheet.kind == "assembly"
                else f"piece_sheet_{extension}"
            )
            artifacts.append(GeneralDerivedArtifact(
                id=f"{sheet.sheet_id}:{extension}:p{plan.proposal_revision}-r{plan.review_revision}",
                kind=kind,
                status=status,
                review_revision=plan.review_revision,
                filename=_filename(sheet, plan.proposal_revision, plan.review_revision, extension),
                media_type=media_type,
                incomplete_reasons=blocking_reasons,
                sheet_id=sheet.sheet_id,
                component_id=component_id,
                content=content,
            ))
    return tuple(artifacts)

