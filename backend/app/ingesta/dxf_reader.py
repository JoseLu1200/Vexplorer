from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import atan2, ceil, cos, isfinite, radians, sin
from pathlib import Path
import re
from typing import Iterable

import ezdxf
import ezdxf.path
from ezdxf import recover


UNIT_BY_INSUNITS = {1: ("in", 25.4), 4: ("mm", 1.0), 5: ("cm", 10.0), 6: ("m", 1000.0)}
MAX_ENTITIES = 100_000
# Untrusted CAD: nested blocks multiply primitives, so expansion is bounded by depth and by MAX_ENTITIES.
MAX_BLOCK_DEPTH = 8
# Arcs and circles are flattened with a fixed angular resolution so the result is unit-independent and deterministic.
SEGMENTS_PER_TURN = 64
# Other curves (bulges, splines, ellipses, hatch boundaries) use a chord tolerance relative to the entity size.
RELATIVE_FLATTENING = 1e-3
MAX_LABEL_CHARS = 80
# Individual unsupported_entity warnings kept before collapsing the rest into per-kind counts.
MAX_UNSUPPORTED_WARNINGS = 20


@dataclass(frozen=True)
class ParsedEntity:
    id: str
    kind: str
    layer: str
    points: tuple[tuple[float, float], ...]
    closed: bool = False
    text: str | None = None
    measurement: float | None = None
    dimension_conflict: bool = False
    extension_starts: tuple[tuple[float, float], tuple[float, float]] | None = None
    dimension_line: tuple[tuple[float, float], tuple[float, float]] | None = None
    text_position: tuple[float, float] | None = None
    display_text: str | None = None
    linetype: str | None = None
    # Exact circle (center x, center y, radius) in source units; only for CIRCLE.
    circle: tuple[float, float, float] | None = None
    # Block names from the outermost INSERT down to the one holding this primitive; empty at top level.
    block_path: tuple[str, ...] = ()
    hatch_pattern: str | None = None
    ordinate_axis: str | None = None


@dataclass(frozen=True)
class BlockReference:
    id: str
    name: str
    insert_point: tuple[float, float]
    primitive_ids: tuple[str, ...]
    depth: int


@dataclass(frozen=True)
class ParsedDrawing:
    drawing_id: str
    source_unit: str
    unit_scale_to_mm: float | None
    entities: tuple[ParsedEntity, ...]
    warnings: tuple[str, ...]
    block_references: tuple[BlockReference, ...] = ()


def _point2(point: object) -> tuple[float, float]:
    return (float(point[0]), float(point[1]))  # type: ignore[index]


def _entity_id(entity: object, ordinal: int) -> str:
    handle = getattr(getattr(entity, "dxf", None), "handle", None)
    return f"entity-{handle}" if isinstance(handle, str) and handle else f"entity-{ordinal}"


def _label(value: object) -> str:
    return str(value).strip()[:MAX_LABEL_CHARS]


def _effective_layer(entity: object, parent_layer: str | None) -> str:
    layer = str(entity.dxf.layer)  # type: ignore[attr-defined]
    # AutoCAD rule: block content on layer "0" takes the layer of the INSERT that places it.
    return parent_layer if parent_layer is not None and layer == "0" else layer


def _linetype(document: object, entity: object, layer: str | None = None, parent_linetype: str | None = None) -> str | None:
    """Effective linetype name, upper-case.

    BYLAYER resolves through the (effective) layer; BYBLOCK takes the linetype of the enclosing INSERT and
    stays unknown at top level.
    """
    name = str(entity.dxf.linetype).strip().upper()  # type: ignore[attr-defined]
    if name == "BYBLOCK":
        return parent_linetype
    if name == "BYLAYER":
        try:
            name = str(document.layers.get(layer if layer is not None else entity.dxf.layer).dxf.linetype).strip().upper()  # type: ignore[attr-defined]
        except (ezdxf.DXFError, KeyError, AttributeError):
            return None
    return None if name in {"", "BYBLOCK", "BYLAYER"} else name


def _finite_points(points: Iterable[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    result = tuple(points)
    if not all(isfinite(value) for point in result for value in point):
        raise ValueError("DXF entity contains non-finite coordinates")
    return result


def _arc_points(entity: object, start_deg: float, sweep_deg: float) -> tuple[tuple[float, float], ...]:
    center = entity.dxf.center  # type: ignore[attr-defined]
    radius = float(entity.dxf.radius)  # type: ignore[attr-defined]
    count = max(2, ceil(SEGMENTS_PER_TURN * sweep_deg / 360.0))
    ocs_points = [
        (center[0] + radius * cos(radians(start_deg + sweep_deg * index / count)),
         center[1] + radius * sin(radians(start_deg + sweep_deg * index / count)), center[2])
        for index in range(count + 1)
    ]
    points = [_point2(point) for point in entity.ocs().points_to_wcs(ocs_points)]  # type: ignore[attr-defined]
    return tuple(points)


def _flatten(entity: object, warnings: list[str], warning: str) -> list[tuple[tuple[float, float], ...]]:
    """Flatten curves through ezdxf.path with a chord tolerance relative to the entity's own size."""
    paths = ezdxf.path.from_hatch(entity) if entity.dxftype() == "HATCH" else [ezdxf.path.make_path(entity)]  # type: ignore[attr-defined]
    result = []
    for path in paths:
        control = [_point2(point) for point in path.control_vertices()]
        if not control:
            continue
        xs = [point[0] for point in control]
        ys = [point[1] for point in control]
        size = max(max(xs) - min(xs), max(ys) - min(ys))
        distance = max(size * RELATIVE_FLATTENING, 1e-9)
        result.append(tuple(_point2(point) for point in path.flattening(distance)))
    warnings.append(warning)
    return result


def _parse_dimension(document: object, entity: object, entity_id: str, layer: str, unit: str, warnings: list[str]) -> ParsedEntity:
    dimension_type = int(entity.dxf.dimtype) & 0x0F  # type: ignore[attr-defined]
    conflict = False
    measurement: float | None = None
    ordinate_axis: str | None = None
    if dimension_type == 6:
        # Ordinate: defpoint is the origin, defpoint2 the feature; bit 64 selects the X axis.
        origin = _point2(entity.dxf.defpoint)  # type: ignore[attr-defined]
        feature = _point2(entity.dxf.defpoint2)  # type: ignore[attr-defined]
        ordinate_axis = "x" if int(entity.dxf.dimtype) & 64 else "y"  # type: ignore[attr-defined]
        offset = abs(feature[0] - origin[0]) if ordinate_axis == "x" else abs(feature[1] - origin[1])
        measurement = offset if isfinite(offset) and offset > 1e-9 else None
    else:
        try:
            measurement = float(entity.get_measurement()) if dimension_type in {0, 1} else None  # type: ignore[attr-defined]
        except (TypeError, ValueError, ezdxf.DXFError):
            measurement = None
    if measurement is None:
        warnings.append(f"unsupported_dimension:{entity_id}")
    else:
        raw_text = str(entity.dxf.text or "")  # type: ignore[attr-defined]
        if raw_text not in {"", "<>", " "}:
            if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", raw_text):
                displayed = float(raw_text)
                if not isfinite(displayed) or abs(displayed - measurement) > 1e-6:
                    conflict = True
                    warnings.append(f"dimension_text_conflict:{entity_id}:geometry={measurement:g}:text={raw_text[:80]}")
            else:
                conflict = True
                warnings.append(f"dimension_text_override:{entity_id}:text={raw_text[:80]}")
        try:
            style = document.dimstyles.get(entity.dxf.dimstyle)  # type: ignore[attr-defined]
            overrides = entity.get_acad_dstyle(style)  # type: ignore[attr-defined]
            dimension_scale = float(overrides.get("dimlfac", getattr(style.dxf, "dimlfac", 1.0)))
        except (ezdxf.DXFError, AttributeError, KeyError, TypeError, ValueError):
            dimension_scale = 1.0
        if not isfinite(dimension_scale) or abs(dimension_scale - 1.0) > 1e-12:
            conflict = True
            warnings.append(f"dimension_scale_conflict:{entity_id}:scale={dimension_scale:g}")
    points = []
    for attr in ("defpoint", "defpoint2", "defpoint3"):
        if entity.dxf.hasattr(attr):  # type: ignore[attr-defined]
            points.append(_point2(getattr(entity.dxf, attr)))  # type: ignore[attr-defined]
    extension_starts = None
    dimension_line = None
    text_position = None
    display_text = None
    if dimension_type in {0, 1} and len(points) == 3:
        base, start_a, start_b = points
        angle = (
            radians(float(entity.dxf.angle))  # type: ignore[attr-defined]
            if dimension_type == 0
            else atan2(start_b[1] - start_a[1], start_b[0] - start_a[0])
        )
        direction = (cos(angle), sin(angle))

        def project(point: tuple[float, float]) -> tuple[float, float]:
            offset = (point[0] - base[0], point[1] - base[1])
            along = offset[0] * direction[0] + offset[1] * direction[1]
            return (base[0] + along * direction[0], base[1] + along * direction[1])

        extension_starts = (start_a, start_b)
        dimension_line = (project(start_a), project(start_b))
        text_position = (
            _point2(entity.dxf.text_midpoint)  # type: ignore[attr-defined]
            if entity.dxf.hasattr("text_midpoint")  # type: ignore[attr-defined]
            else ((dimension_line[0][0] + dimension_line[1][0]) / 2, (dimension_line[0][1] + dimension_line[1][1]) / 2)
        )
        raw_text = str(entity.dxf.text or "")  # type: ignore[attr-defined]
        display_text = (
            raw_text
            if raw_text not in {"", "<>"}
            else f"{measurement:g} {unit}" if measurement is not None and unit != "unknown"
            else f"{measurement:g} source-unit" if measurement is not None
            else "unresolved"
        )
    return ParsedEntity(
        entity_id, "DIMENSION", layer, _finite_points(points), text=str(entity.dxf.text or ""),  # type: ignore[attr-defined]
        measurement=measurement, dimension_conflict=conflict, extension_starts=extension_starts,
        dimension_line=dimension_line, text_position=text_position, display_text=display_text,
        ordinate_axis=ordinate_axis,
    )


class _Expansion:
    """Walks modelspace and block content into flat primitives with deterministic, traceable IDs.

    Virtual block entities have no DXF handle, so their IDs are the INSERT's ID plus nesting ordinals
    (`entity-<handle>-b<i>`, `-m<k>` for MINSERT cells). No `/` so the IDs stay safe in URLs and DOM ids.
    """

    def __init__(self, document: object, unit: str, max_entities: int) -> None:
        self.document = document
        self.unit = unit
        self.max_entities = max_entities
        self.parsed: list[ParsedEntity] = []
        self.blocks: list[BlockReference] = []
        self.warnings: list[str] = []
        self.visits = 0
        self.unsupported_overflow: dict[str, int] = {}
        self.unsupported_listed = 0

    def _unsupported(self, kind: str, entity_id: str) -> None:
        if self.unsupported_listed < MAX_UNSUPPORTED_WARNINGS:
            self.unsupported_listed += 1
            self.warnings.append(f"unsupported_entity:{kind}:{entity_id}")
        else:
            self.unsupported_overflow[kind] = self.unsupported_overflow.get(kind, 0) + 1

    def finish(self) -> None:
        for kind, count in sorted(self.unsupported_overflow.items()):
            self.warnings.append(f"unsupported_entity_more:{kind}:{count}")

    def _add(self, entity: ParsedEntity) -> None:
        if len(self.parsed) >= self.max_entities:
            raise ValueError(f"entity limit exceeded after block expansion: > {self.max_entities}")
        self.parsed.append(entity)

    def visit(self, entity: object, entity_id: str, parent_layer: str | None = None, parent_linetype: str | None = None, block_path: tuple[str, ...] = ()) -> None:
        # Every visit counts, also INSERTs and unsupported entities, so empty or unsupported nests cannot bypass the bound.
        self.visits += 1
        if self.visits > self.max_entities:
            raise ValueError(f"entity limit exceeded after block expansion: > {self.max_entities}")
        kind = entity.dxftype()  # type: ignore[attr-defined]
        layer = _effective_layer(entity, parent_layer)
        linetype = _linetype(self.document, entity, layer, parent_linetype)
        if kind == "LINE":
            self._add(ParsedEntity(entity_id, kind, layer, _finite_points((_point2(entity.dxf.start), _point2(entity.dxf.end))), linetype=linetype, block_path=block_path))  # type: ignore[attr-defined]
        elif kind == "LWPOLYLINE" or (kind == "POLYLINE" and entity.is_2d_polyline):  # type: ignore[attr-defined]
            closed = bool(entity.closed) if kind == "LWPOLYLINE" else bool(entity.is_closed)  # type: ignore[attr-defined]
            bulged = any(abs(float(vertex[2])) > 1e-12 for vertex in entity.get_points("xyb")) if kind == "LWPOLYLINE" else any(abs(float(vertex.dxf.bulge)) > 1e-12 for vertex in entity.vertices)  # type: ignore[attr-defined]
            if bulged:
                flattened = _flatten(entity, self.warnings, f"approximated_bulge:{entity_id}")
                points = flattened[0] if flattened else ()
                if closed and len(points) > 1 and points[0] == points[-1]:
                    points = points[:-1]
            elif kind == "LWPOLYLINE":
                points = tuple((float(x), float(y)) for x, y, _ in entity.get_points("xyb"))  # type: ignore[attr-defined]
            else:
                points = tuple(_point2(vertex.dxf.location) for vertex in entity.vertices)  # type: ignore[attr-defined]
            if points:
                self._add(ParsedEntity(entity_id, kind, layer, _finite_points(points), closed, linetype=linetype, block_path=block_path))
        elif kind == "CIRCLE":
            center = _point2(entity.ocs().to_wcs(entity.dxf.center))  # type: ignore[attr-defined]
            radius = float(entity.dxf.radius)  # type: ignore[attr-defined]
            points = list(_arc_points(entity, 0.0, 360.0))
            points[-1] = points[0]  # closed shape repeats its first point so open-polyline renderers close it
            self._add(ParsedEntity(entity_id, kind, layer, _finite_points(points), True, linetype=linetype, circle=(center[0], center[1], radius), block_path=block_path))
        elif kind == "ARC":
            start = float(entity.dxf.start_angle)  # type: ignore[attr-defined]
            sweep = (float(entity.dxf.end_angle) - start) % 360.0 or 360.0  # type: ignore[attr-defined]
            self._add(ParsedEntity(entity_id, kind, layer, _finite_points(_arc_points(entity, start, sweep)), linetype=linetype, block_path=block_path))
        elif kind in {"ELLIPSE", "SPLINE"}:
            flattened = _flatten(entity, self.warnings, f"approximated_curve:{entity_id}")
            if flattened and flattened[0]:
                self._add(ParsedEntity(entity_id, kind, layer, _finite_points(flattened[0]), linetype=linetype, block_path=block_path))
        elif kind == "HATCH":
            pattern = "SOLID" if entity.dxf.solid_fill else _label(entity.dxf.pattern_name)  # type: ignore[attr-defined]
            flattened = _flatten(entity, self.warnings, f"approximated_hatch_boundary:{entity_id}")
            for index, boundary in enumerate(flattened, start=1):
                if len(boundary) >= 3:
                    self._add(ParsedEntity(f"{entity_id}-p{index}", kind, layer, _finite_points(boundary), True, linetype=linetype, hatch_pattern=pattern, block_path=block_path))
        elif kind in {"TEXT", "MTEXT", "ATTRIB"}:
            if kind == "MTEXT":
                text = entity.plain_text()  # type: ignore[attr-defined]
            elif kind == "ATTRIB":
                text = f"{entity.dxf.tag}: {entity.dxf.text}"  # type: ignore[attr-defined]
            else:
                text = str(entity.dxf.text)  # type: ignore[attr-defined]
            self._add(ParsedEntity(entity_id, kind, layer, (_point2(entity.dxf.insert),), text=text.strip(), block_path=block_path))  # type: ignore[attr-defined]
        elif kind == "DIMENSION":
            self._add(_parse_dimension(self.document, entity, entity_id, layer, self.unit, self.warnings))
        elif kind == "INSERT":
            self._insert(entity, entity_id, layer, linetype, block_path)
        else:
            self._unsupported(kind, entity_id)

    def _insert(self, insert: object, insert_id: str, layer: str, linetype: str | None, block_path: tuple[str, ...]) -> None:
        name = _label(insert.dxf.name)  # type: ignore[attr-defined]
        if len(block_path) >= MAX_BLOCK_DEPTH:
            self.warnings.append(f"unsupported_block_depth:{insert_id}")
            return
        path = (*block_path, name)
        for attrib_index, attrib in enumerate(getattr(insert, "attribs", ()), start=1):
            self.visit(attrib, f"{insert_id}-a{attrib_index}", layer, linetype, path)
        cells = list(insert.multi_insert()) if getattr(insert, "mcount", 1) > 1 else [insert]  # type: ignore[attr-defined]
        for cell_index, cell in enumerate(cells, start=1):
            cell_id = f"{insert_id}-m{cell_index}" if len(cells) > 1 else insert_id
            first = len(self.parsed)
            try:
                children = list(cell.virtual_entities())  # type: ignore[attr-defined]
            except (ezdxf.DXFError, ValueError, KeyError, ZeroDivisionError):
                self.warnings.append(f"unsupported_block:{cell_id}")
                continue
            for child_index, child in enumerate(children, start=1):
                if child.dxftype() in {"ATTDEF"}:
                    continue
                self.visit(child, f"{cell_id}-b{child_index}", layer, linetype, path)
            point = _point2(cell.dxf.insert)  # type: ignore[attr-defined]
            primitive_ids = tuple(item.id for item in self.parsed[first:])
            self.blocks.append(BlockReference(cell_id, name, point, primitive_ids, len(block_path)))


def _read_document(path: Path, warnings: list[str]) -> object:
    try:
        return ezdxf.readfile(path)
    except ezdxf.DXFStructureError:
        # Slower tolerant loader, only as a retry; it also audits and reports what it repaired.
        document, auditor = recover.readfile(path)
        warnings.append(f"recovered_dxf:fixes={len(auditor.fixes)}:errors={len(auditor.errors)}")
        return document


def parse_dxf(path: Path, *, max_entities: int = MAX_ENTITIES) -> ParsedDrawing:
    """Read the documented DXF subset: lines, polylines (bulges flattened), circles, arcs, curves, hatches,
    texts, attributes, linear and ordinate dimensions, and block references expanded with traceable IDs."""
    raw = path.read_bytes()
    warnings: list[str] = []
    document = _read_document(path, warnings)
    modelspace = document.modelspace()
    if len(modelspace) > max_entities:
        raise ValueError(f"entity limit exceeded: {len(modelspace)} > {max_entities}")
    unit_code = int(document.header.get("$INSUNITS", 0) or 0)
    unit, scale = UNIT_BY_INSUNITS.get(unit_code, ("unknown", None))
    if scale is None:
        warnings.append("source_unit_unknown")
        measurement_system = document.header.get("$MEASUREMENT", None)
        if measurement_system in (0, 1):
            # A hint for the reviewer only; units are never resolved from it.
            warnings.append(f"unit_hint_measurement:{'metric' if measurement_system == 1 else 'imperial'}")

    expansion = _Expansion(document, unit, max_entities)
    expansion.warnings = warnings
    for ordinal, entity in enumerate(modelspace, start=1):
        expansion.visit(entity, _entity_id(entity, ordinal))
    expansion.finish()

    for layout in document.layouts:
        if layout.name == "Model":
            continue
        # Title blocks usually live in paperspace and are harmless; unread dimensions there are not.
        kinds = [entity.dxftype() for entity in layout if entity.dxftype() != "VIEWPORT"]
        dimensions = sum(1 for kind in kinds if kind in {"DIMENSION", "ARC_DIMENSION", "LEADER", "MLEADER"})
        if dimensions:
            warnings.append(f"paperspace_dimensions:{_label(layout.name)}:{dimensions}")
        if len(kinds) - dimensions:
            warnings.append(f"paperspace_annotations:{_label(layout.name)}:{len(kinds) - dimensions}")

    return ParsedDrawing(
        drawing_id=f"drawing-{sha256(raw).hexdigest()[:16]}",
        source_unit=unit,
        unit_scale_to_mm=scale,
        entities=tuple(expansion.parsed),
        warnings=tuple(warnings),
        block_references=tuple(expansion.blocks),
    )
