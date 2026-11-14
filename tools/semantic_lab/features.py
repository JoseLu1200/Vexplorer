from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import ezdxf
from ezdxf.path import make_path
from PIL import Image, ImageDraw


class UnsupportedGeometry(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ExtractionResult:
    features: dict[str, float]
    text: str
    geometry_signature: str
    render_sha256: str
    source_sha256: str
    supported_entity_count: int
    ignored_entity_count: int


@dataclass(frozen=True)
class _Primitive:
    kind: str
    points: tuple[tuple[float, float], ...]


_CURVE_TYPES = {"ARC", "CIRCLE", "ELLIPSE", "SPLINE", "LWPOLYLINE", "POLYLINE"}
_IGNORED_TYPES = {
    "ATTRIB",
    "DIMENSION",
    "HATCH",
    "LEADER",
    "MLEADER",
    "MTEXT",
    "POINT",
    "TEXT",
    "XLINE",
}


def _expanded_entities(entities: Iterable[object]) -> Iterable[object]:
    for entity in entities:
        if entity.dxftype() == "INSERT":
            try:
                yield from _expanded_entities(entity.virtual_entities())
            except (ezdxf.DXFError, ValueError):
                yield entity
        else:
            yield entity


def _xyz(value: object) -> tuple[float, float, float]:
    return float(value.x), float(value.y), float(value.z)


def _path_points(entity: object) -> tuple[tuple[float, float, float], ...]:
    path = make_path(entity)
    controls = tuple(path.control_vertices())
    if not controls:
        return ()
    xs = [float(point.x) for point in controls]
    ys = [float(point.y) for point in controls]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
    distance = max(span / 128.0, 1e-7)
    return tuple(_xyz(point) for point in path.flattening(distance=distance, segments=8))


def _entity_points(entity: object) -> tuple[tuple[float, float, float], ...]:
    kind = entity.dxftype()
    if kind == "LINE":
        return (_xyz(entity.dxf.start), _xyz(entity.dxf.end))
    if kind in _CURVE_TYPES:
        return _path_points(entity)
    if kind in {"3DFACE", "SOLID", "TRACE"}:
        points = tuple(_xyz(getattr(entity.dxf, f"v{index}")) for index in range(4))
        return points + (points[0],)
    return ()


def _normalize(primitives: list[_Primitive]) -> tuple[list[_Primitive], float, float]:
    all_points = [point for primitive in primitives for point in primitive.points]
    xmin = min(point[0] for point in all_points)
    xmax = max(point[0] for point in all_points)
    ymin = min(point[1] for point in all_points)
    ymax = max(point[1] for point in all_points)
    width = xmax - xmin
    height = ymax - ymin
    scale = max(width, height)
    if not math.isfinite(scale) or scale <= 1e-12:
        raise UnsupportedGeometry("degenerate_geometry")
    normalized = [
        _Primitive(
            primitive.kind,
            tuple(
                (round((x - xmin) / scale, 8), round((y - ymin) / scale, 8))
                for x, y in primitive.points
            ),
        )
        for primitive in primitives
    ]
    return normalized, width / scale, height / scale


def _render(primitives: list[_Primitive], image_path: Path | None, image_size: int) -> tuple[bytes, str]:
    image = Image.new("L", (image_size, image_size), 255)
    draw = ImageDraw.Draw(image)
    padding = max(8, image_size // 24)
    extent = image_size - 2 * padding
    for primitive in primitives:
        pixels = [
            (padding + round(x * extent), image_size - padding - round(y * extent))
            for x, y in primitive.points
        ]
        if len(pixels) >= 2:
            draw.line(pixels, fill=0, width=max(1, image_size // 192), joint="curve")
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    content = buffer.getvalue()
    if image_path is not None:
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(content)
    return content, hashlib.sha256(content).hexdigest()


def _features(
    primitives: list[_Primitive],
    width: float,
    height: float,
) -> dict[str, float]:
    kind_counts = Counter(primitive.kind for primitive in primitives)
    segments: list[tuple[float, float, float, float, float]] = []
    for primitive in primitives:
        for start, end in zip(primitive.points, primitive.points[1:]):
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length = math.hypot(dx, dy)
            if length > 1e-12:
                segments.append((start[0], start[1], end[0], end[1], length))
    total_length = sum(segment[4] for segment in segments)
    orientation = [0.0] * 8
    radial = [0.0] * 5
    for x1, y1, x2, y2, length in segments:
        angle = math.atan2(y2 - y1, x2 - x1) % math.pi
        orientation[min(7, int(angle / math.pi * 8))] += length
        radius = math.hypot((x1 + x2) / 2 - 0.5, (y1 + y2) / 2 - 0.5) / math.sqrt(0.5)
        radial[min(4, int(min(radius, 0.999999) * 5))] += length
    denominator = total_length or 1.0
    result: dict[str, float] = {
        "bbox_width_normalized": float(width),
        "bbox_height_normalized": float(height),
        "bbox_aspect_log": float(math.log((width + 1e-9) / (height + 1e-9))),
        "path_count_log1p": float(math.log1p(len(primitives))),
        "segment_count_log1p": float(math.log1p(len(segments))),
        "total_length_normalized": float(total_length),
    }
    for kind in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE", "FACE"):
        result[f"entity_{kind.lower()}_fraction"] = float(kind_counts[kind] / len(primitives))
    result.update({f"orientation_{index}": value / denominator for index, value in enumerate(orientation)})
    result.update({f"radial_{index}": value / denominator for index, value in enumerate(radial)})
    if not all(math.isfinite(value) for value in result.values()):
        raise UnsupportedGeometry("nonfinite_features")
    return result


def _observation_text(features: dict[str, float]) -> str:
    return (
        "geometric observation; "
        f"normalized width {features['bbox_width_normalized']:.4f}; "
        f"normalized height {features['bbox_height_normalized']:.4f}; "
        f"log aspect {features['bbox_aspect_log']:.4f}; "
        f"log path count {features['path_count_log1p']:.4f}; "
        f"log segment count {features['segment_count_log1p']:.4f}; "
        f"normalized line length {features['total_length_normalized']:.4f}"
    )


def extract_dxf(
    path: Path | str,
    *,
    image_path: Path | str | None = None,
    image_size: int = 384,
) -> ExtractionResult:
    source = Path(path)
    try:
        document = ezdxf.readfile(source)
    except (OSError, ezdxf.DXFError) as exc:
        raise UnsupportedGeometry("invalid_dxf") from exc
    primitives: list[_Primitive] = []
    ignored_count = 0
    for entity in _expanded_entities(document.modelspace()):
        kind = entity.dxftype()
        points = _entity_points(entity)
        if points:
            if any(abs(z) > 1e-9 for _, _, z in points):
                raise UnsupportedGeometry("nonzero_z_geometry")
            xy = tuple((x, y) for x, y, _ in points)
            if len(xy) >= 2:
                normalized_kind = "FACE" if kind in {"3DFACE", "SOLID", "TRACE"} else kind
                primitives.append(_Primitive(normalized_kind, xy))
        elif kind in _IGNORED_TYPES or kind == "INSERT":
            ignored_count += 1
        else:
            ignored_count += 1
    if not primitives:
        raise UnsupportedGeometry("no_supported_geometry")
    normalized, width, height = _normalize(primitives)
    signature_payload = [
        [primitive.kind, [[x, y] for x, y in primitive.points]] for primitive in normalized
    ]
    geometry_signature = hashlib.sha256(
        json.dumps(signature_payload, separators=(",", ":"), sort_keys=False).encode("ascii")
    ).hexdigest()
    _, render_sha256 = _render(
        normalized,
        Path(image_path) if image_path is not None else None,
        image_size,
    )
    features = _features(normalized, width, height)
    return ExtractionResult(
        features=features,
        text=_observation_text(features),
        geometry_signature=geometry_signature,
        render_sha256=render_sha256,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        supported_entity_count=len(primitives),
        ignored_entity_count=ignored_count,
    )
