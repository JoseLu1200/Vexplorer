from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import atan2, cos, isfinite, radians, sin
from pathlib import Path
import re
from typing import Any, Iterable, Iterator

import ezdxf
import ezdxf.path
from ezdxf import recover


UNIT_BY_INSUNITS = {1: ("in", 25.4), 4: ("mm", 1.0), 5: ("cm", 10.0), 6: ("m", 1000.0)}
MAX_ENTITIES = 100_000
MAX_BLOCK_DEPTH = 8
MAX_CURVE_POINTS = 4096


class _EntityLimitExceeded(ValueError):
    pass


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
    circular: dict[str, Any] | None = None


@dataclass(frozen=True)
class ParsedDrawing:
    drawing_id: str
    source_unit: str
    unit_scale_to_mm: float | None
    entities: tuple[ParsedEntity, ...]
    warnings: tuple[str, ...]


def _point2(point: object) -> tuple[float, float]:
    return (float(point[0]), float(point[1]))  # type: ignore[index]


def _planar_xy_points(points: Iterable[object], tolerance: float = 1e-9) -> tuple[tuple[float, float], ...] | None:
    points_3d = tuple((float(point[0]), float(point[1]), float(point[2])) for point in points)  # type: ignore[index]
    if not all(isfinite(value) for point in points_3d for value in point):
        raise ValueError("DXF entity contains non-finite coordinates")
    if points_3d and any(abs(point[2]) > tolerance for point in points_3d):
        return None
    return tuple((x, y) for x, y, _ in points_3d)


def _rendered_dimension_text(entity: object) -> str | None:
    try:
        visual_entities = entity.virtual_entities()  # type: ignore[attr-defined]
    except (AttributeError, ezdxf.DXFError):
        return None
    for visual in visual_entities:
        if visual.dxftype() == "MTEXT":
            value = visual.plain_text().strip()
        elif visual.dxftype() == "TEXT":
            value = str(visual.dxf.text).strip()
        else:
            continue
        if value:
            return value
    return None


def _entity_id(entity: object, ordinal: int) -> str:
    handle = getattr(getattr(entity, "dxf", None), "handle", None)
    return f"entity-{handle}" if isinstance(handle, str) and handle else f"entity-{ordinal}"


def _finite_points(points: Iterable[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    result = tuple(points)
    if not all(isfinite(value) for point in result for value in point):
        raise ValueError("DXF entity contains non-finite coordinates")
    return result


def _read_document(path: Path, warnings: list[str]) -> object:
    try:
        return ezdxf.readfile(path)
    except ezdxf.DXFStructureError:
        document, auditor = recover.readfile(path)
        warnings.append(f"recovered_dxf:fixes={len(auditor.fixes)}:errors={len(auditor.errors)}")
        return document


def _approximate_curve(entity: object, entity_id: str, warnings: list[str]) -> tuple[tuple[float, float], ...] | None:
    try:
        path = ezdxf.path.make_path(entity)
        control = []
        for index, point in enumerate(path.control_vertices()):
            if index >= MAX_CURVE_POINTS:
                warnings.append(f"curve_point_limit:{entity_id}")
                return None
            control.append(point)
        if not control:
            return None
        xs = [float(point[0]) for point in control]
        ys = [float(point[1]) for point in control]
        distance = max(max(max(xs) - min(xs), max(ys) - min(ys)) * 1e-3, 1e-9)
        flattened = []
        for index, point in enumerate(path.flattening(distance, segments=4)):
            if index >= MAX_CURVE_POINTS:
                warnings.append(f"curve_point_limit:{entity_id}")
                return None
            flattened.append(point)
    except (AttributeError, ValueError, ezdxf.DXFError):
        return None
    points = _planar_xy_points(flattened)
    if points is None:
        warnings.append(f"unsupported_entity_plane:{entity.dxftype()}:{entity_id}")  # type: ignore[attr-defined]
        return None
    warnings.append(f"approximated_curve:{entity_id}:max_points={MAX_CURVE_POINTS}")
    return points


def _linetype(
    document: object,
    entity: object,
    layer: str,
    parent_linetype: str | None = None,
) -> str | None:
    name = str(entity.dxf.linetype).strip().upper()  # type: ignore[attr-defined]
    if name == "BYBLOCK":
        return parent_linetype
    if name == "BYLAYER":
        try:
            name = str(document.layers.get(layer).dxf.linetype).strip().upper()  # type: ignore[attr-defined]
        except (AttributeError, KeyError, ezdxf.DXFError):
            return None
    return None if name in {"", "BYLAYER", "BYBLOCK", "CONTINUOUS"} else name


def _expanded_entities(
    document: object,
    modelspace: object,
    *,
    max_entities: int,
    warnings: list[str],
) -> Iterator[tuple[object, str, str, str | None]]:
    visits = 0

    def count() -> None:
        nonlocal visits
        visits += 1
        if visits > max_entities:
            raise _EntityLimitExceeded(f"entity limit exceeded after block expansion: > {max_entities}")

    def walk(
        entity: object,
        entity_id: str,
        parent_layer: str | None = None,
        parent_linetype: str | None = None,
        depth: int = 0,
    ) -> Iterator[tuple[object, str, str, str | None]]:
        count()
        own_layer = str(entity.dxf.layer)  # type: ignore[attr-defined]
        layer = parent_layer if parent_layer is not None and own_layer == "0" else own_layer
        linetype = _linetype(document, entity, layer, parent_linetype)
        if entity.dxftype() != "INSERT":  # type: ignore[attr-defined]
            yield entity, entity_id, layer, linetype
            return
        if depth >= MAX_BLOCK_DEPTH:
            warnings.append(f"unsupported_block_depth:{entity_id}")
            return
        for index, attrib in enumerate(getattr(entity, "attribs", ()), start=1):
            yield from walk(attrib, f"{entity_id}-a{index}", layer, linetype, depth + 1)
        cells = entity.multi_insert() if getattr(entity, "mcount", 1) > 1 else (entity,)  # type: ignore[attr-defined]
        for cell_index, cell in enumerate(cells, start=1):
            if cell is not entity:
                count()
            cell_id = f"{entity_id}-m{cell_index}" if getattr(entity, "mcount", 1) > 1 else entity_id
            try:
                children = cell.virtual_entities()  # type: ignore[attr-defined]
                for child_index, child in enumerate(children, start=1):
                    if child.dxftype() == "ATTDEF":
                        continue
                    yield from walk(child, f"{cell_id}-b{child_index}", layer, linetype, depth + 1)
            except _EntityLimitExceeded:
                raise
            except (ezdxf.DXFError, KeyError, ValueError, ZeroDivisionError):
                warnings.append(f"unsupported_block:{cell_id}")

    for ordinal, entity in enumerate(modelspace, start=1):  # type: ignore[arg-type]
        yield from walk(entity, _entity_id(entity, ordinal))


def parse_dxf(path: Path, *, max_entities: int = MAX_ENTITIES) -> ParsedDrawing:
    """Read the deliberately small, documented DXF subset used by the demo."""
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

    parsed: list[ParsedEntity] = []
    for entity, entity_id, layer, linetype in _expanded_entities(
        document, modelspace, max_entities=max_entities, warnings=warnings,
    ):
        kind = entity.dxftype()
        if kind == "LINE":
            points = _planar_xy_points((entity.dxf.start, entity.dxf.end))
            if points is None:
                warnings.append(f"unsupported_entity_plane:{kind}:{entity_id}")
                continue
            parsed.append(ParsedEntity(entity_id, kind, layer, points, linetype=linetype))
        elif kind == "LWPOLYLINE":
            vertices = tuple(entity.get_points("xyb"))
            if any(abs(float(vertex[2])) > 1e-12 for vertex in vertices):
                warnings.append(f"unsupported_bulge:{entity_id}")
                continue
            points = _planar_xy_points(entity.vertices_in_wcs())
            if points is None:
                warnings.append(f"unsupported_entity_plane:{kind}:{entity_id}")
                continue
            parsed.append(ParsedEntity(entity_id, kind, layer, points, bool(entity.closed), linetype=linetype))
        elif kind in {"CIRCLE", "ARC"}:
            extrusion = entity.dxf.extrusion
            if abs(float(extrusion.x)) > 1e-9 or abs(float(extrusion.y)) > 1e-9 or abs(abs(float(extrusion.z)) - 1.0) > 1e-9:
                warnings.append(f"unsupported_entity_plane:{kind}:{entity_id}")
                continue
            center_wcs = entity.ocs().to_wcs(entity.dxf.center)
            if kind == "CIRCLE":
                radius = float(entity.dxf.radius)
                sample_wcs = entity.ocs().to_wcs((entity.dxf.center.x + radius, entity.dxf.center.y, entity.dxf.center.z))
                points = _planar_xy_points((sample_wcs,))
                start_angle = end_angle = None
            else:
                radius = float(entity.dxf.radius)
                points = _planar_xy_points((entity.start_point, entity.end_point))
                start_angle = float(entity.dxf.start_angle)
                end_angle = float(entity.dxf.end_angle)
            center = _planar_xy_points((center_wcs,))
            if center is None or points is None or not isfinite(radius) or radius <= 0:
                warnings.append(f"unsupported_entity_plane:{kind}:{entity_id}")
                continue
            parsed.append(ParsedEntity(
                entity_id, kind, layer, points, closed=kind == "CIRCLE", linetype=linetype,
                circular={
                    "kind": kind.lower(), "center_source": center[0], "radius_source": radius,
                    "start_angle_deg": start_angle, "end_angle_deg": end_angle,
                },
            ))
        elif kind in {"ELLIPSE", "SPLINE"}:
            points = _approximate_curve(entity, entity_id, warnings)
            if points:
                parsed.append(ParsedEntity(entity_id, kind, layer, points, linetype=linetype))
            else:
                warnings.append(f"unsupported_entity:{kind}:{entity_id}")
        elif kind in {"TEXT", "MTEXT", "ATTRIB"}:
            text = entity.plain_text() if kind == "MTEXT" else str(entity.dxf.text)
            insert = _planar_xy_points((entity.dxf.insert,))
            if insert is None:
                warnings.append(f"unsupported_entity_plane:{kind}:{entity_id}")
                continue
            parsed.append(ParsedEntity(entity_id, kind, layer, insert, text=text.strip(), linetype=linetype))
        elif kind == "DIMENSION":
            dimension_type = int(entity.dxf.dimtype) & 0x0F
            conflict = False
            dimension_scale = 1.0
            if dimension_type == 6 and entity.dxf.hasattr("defpoint") and entity.dxf.hasattr("defpoint2"):
                origin = _point2(entity.dxf.defpoint)
                feature = _point2(entity.dxf.defpoint2)
                measurement = abs(
                    feature[0] - origin[0]
                    if int(entity.dxf.dimtype) & 64
                    else feature[1] - origin[1]
                )
                if not isfinite(measurement) or measurement <= 1e-9:
                    measurement = None
            else:
                try:
                    measurement = float(entity.get_measurement()) if dimension_type in {0, 1} else None
                except (TypeError, ValueError, ezdxf.DXFError):
                    measurement = None
            if measurement is None:
                warnings.append(f"unsupported_dimension:{entity_id}")
            else:
                raw_text = str(entity.dxf.text or "")
                if raw_text not in {"", "<>", " "}:
                    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", raw_text):
                        displayed = float(raw_text)
                        if not isfinite(displayed) or abs(displayed - measurement) > 1e-6:
                            conflict = True
                            warnings.append(
                                f"dimension_text_conflict:{entity_id}:geometry={measurement:g}:text={raw_text[:80]}"
                            )
                    else:
                        conflict = True
                        warnings.append(f"dimension_text_override:{entity_id}:text={raw_text[:80]}")
                style = document.dimstyles.get(entity.dxf.dimstyle)
                overrides = entity.get_acad_dstyle(style)
                dimension_scale = float(overrides.get("dimlfac", getattr(style.dxf, "dimlfac", 1.0)))
                if not isfinite(dimension_scale) or abs(dimension_scale - 1.0) > 1e-12:
                    conflict = True
                    warnings.append(f"dimension_scale_conflict:{entity_id}:scale={dimension_scale:g}")
            points = []
            for attr in ("defpoint", "defpoint2", "defpoint3"):
                if entity.dxf.hasattr(attr):
                    points.append(_point2(getattr(entity.dxf, attr)))
            extension_starts = None
            dimension_line = None
            text_position = None
            display_text = None
            if dimension_type in {0, 1} and len(points) == 3:
                base, start_a, start_b = points
                angle = (
                    radians(float(entity.dxf.angle))
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
                    _point2(entity.dxf.text_midpoint)
                    if entity.dxf.hasattr("text_midpoint")
                    else (
                        (dimension_line[0][0] + dimension_line[1][0]) / 2,
                        (dimension_line[0][1] + dimension_line[1][1]) / 2,
                    )
                )
                raw_text = str(entity.dxf.text or "")
                rendered_text = _rendered_dimension_text(entity) if abs(dimension_scale - 1.0) > 1e-12 else None
                display_text = rendered_text or (
                    raw_text if raw_text not in {"", "<>"}
                    else f"{measurement:g} {unit}" if measurement is not None and unit != "unknown"
                    else f"{measurement:g} source-unit" if measurement is not None
                    else "unresolved"
                )
            parsed.append(ParsedEntity(
                entity_id, kind, layer, _finite_points(points), text=str(entity.dxf.text or ""),
                measurement=measurement, dimension_conflict=conflict, extension_starts=extension_starts,
                dimension_line=dimension_line, text_position=text_position, display_text=display_text,
            ))
        else:
            warnings.append(f"unsupported_entity:{kind}:{entity_id}")

    return ParsedDrawing(
        drawing_id=f"drawing-{sha256(raw).hexdigest()[:16]}",
        source_unit=unit,
        unit_scale_to_mm=scale,
        entities=tuple(parsed),
        warnings=tuple(warnings),
    )
