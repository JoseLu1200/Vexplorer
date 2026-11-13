from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from pathlib import Path
import re
from typing import Iterable

import ezdxf


UNIT_BY_INSUNITS = {1: ("in", 25.4), 4: ("mm", 1.0), 5: ("cm", 10.0), 6: ("m", 1000.0)}
MAX_ENTITIES = 100_000


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


@dataclass(frozen=True)
class ParsedDrawing:
    drawing_id: str
    source_unit: str
    unit_scale_to_mm: float | None
    entities: tuple[ParsedEntity, ...]
    warnings: tuple[str, ...]


def _point2(point: object) -> tuple[float, float]:
    return (float(point[0]), float(point[1]))  # type: ignore[index]


def _entity_id(entity: object, ordinal: int) -> str:
    handle = getattr(getattr(entity, "dxf", None), "handle", None)
    return f"entity-{handle}" if isinstance(handle, str) and handle else f"entity-{ordinal}"


def _finite_points(points: Iterable[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    result = tuple(points)
    if not all(isfinite(value) for point in result for value in point):
        raise ValueError("DXF entity contains non-finite coordinates")
    return result


def parse_dxf(path: Path, *, max_entities: int = MAX_ENTITIES) -> ParsedDrawing:
    """Read the deliberately small, documented DXF subset used by the demo."""
    raw = path.read_bytes()
    document = ezdxf.readfile(path)
    modelspace = document.modelspace()
    if len(modelspace) > max_entities:
        raise ValueError(f"entity limit exceeded: {len(modelspace)} > {max_entities}")
    unit_code = int(document.header.get("$INSUNITS", 0) or 0)
    unit, scale = UNIT_BY_INSUNITS.get(unit_code, ("unknown", None))
    warnings: list[str] = []
    if scale is None:
        warnings.append("source_unit_unknown")

    parsed: list[ParsedEntity] = []
    for ordinal, entity in enumerate(modelspace, start=1):
        kind = entity.dxftype()
        layer = str(entity.dxf.layer)
        entity_id = _entity_id(entity, ordinal)
        if kind == "LINE":
            parsed.append(ParsedEntity(entity_id, kind, layer, _finite_points((_point2(entity.dxf.start), _point2(entity.dxf.end)))))
        elif kind == "LWPOLYLINE":
            vertices = tuple(entity.get_points("xyb"))
            if any(abs(float(vertex[2])) > 1e-12 for vertex in vertices):
                warnings.append(f"unsupported_bulge:{entity_id}")
                continue
            parsed.append(ParsedEntity(entity_id, kind, layer, _finite_points((float(x), float(y)) for x, y, _ in vertices), bool(entity.closed)))
        elif kind in {"TEXT", "MTEXT"}:
            text = entity.plain_text() if kind == "MTEXT" else str(entity.dxf.text)
            insert = _point2(entity.dxf.insert)
            parsed.append(ParsedEntity(entity_id, kind, layer, (insert,), text=text.strip()))
        elif kind == "DIMENSION":
            dimension_type = int(entity.dxf.dimtype) & 0x0F
            conflict = False
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
            parsed.append(ParsedEntity(
                entity_id, kind, layer, _finite_points(points), text=str(entity.dxf.text or ""),
                measurement=measurement, dimension_conflict=conflict,
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
