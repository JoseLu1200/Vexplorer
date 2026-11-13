from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from pathlib import Path
from typing import Iterable

import ezdxf


UNIT_BY_INSUNITS = {1: ("in", 25.4), 4: ("mm", 1.0), 5: ("cm", 10.0), 6: ("m", 1000.0)}


@dataclass(frozen=True)
class ParsedEntity:
    id: str
    kind: str
    layer: str
    points: tuple[tuple[float, float], ...]
    closed: bool = False
    text: str | None = None
    measurement: float | None = None


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
    return f"entity-{handle or ordinal:>s}" if isinstance(handle, str) else f"entity-{ordinal}"


def _finite_points(points: Iterable[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    result = tuple(points)
    if not all(isfinite(value) for point in result for value in point):
        raise ValueError("DXF entity contains non-finite coordinates")
    return result


def parse_dxf(path: Path) -> ParsedDrawing:
    """Read the deliberately small, documented DXF subset used by the demo."""
    raw = path.read_bytes()
    document = ezdxf.readfile(path)
    unit_code = int(document.header.get("$INSUNITS", 0) or 0)
    unit, scale = UNIT_BY_INSUNITS.get(unit_code, ("unknown", None))
    warnings: list[str] = []
    if scale is None:
        warnings.append("source_unit_unknown")

    parsed: list[ParsedEntity] = []
    for ordinal, entity in enumerate(document.modelspace(), start=1):
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
            try:
                measurement = float(entity.get_measurement())
            except (TypeError, ValueError, ezdxf.DXFError):
                measurement = None
                warnings.append(f"unsupported_dimension:{entity_id}")
            points = []
            for attr in ("defpoint", "defpoint2", "defpoint3"):
                if entity.dxf.hasattr(attr):
                    points.append(_point2(getattr(entity.dxf, attr)))
            parsed.append(ParsedEntity(entity_id, kind, layer, _finite_points(points), measurement=measurement))
        else:
            warnings.append(f"unsupported_entity:{kind}:{entity_id}")

    return ParsedDrawing(
        drawing_id=f"drawing-{sha256(raw).hexdigest()[:16]}",
        source_unit=unit,
        unit_scale_to_mm=scale,
        entities=tuple(parsed),
        warnings=tuple(warnings),
    )
