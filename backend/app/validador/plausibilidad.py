"""Contraste conservador de geometría observada con el catálogo del taller.

Adaptado de la propuesta de Pablo Loureiro en 7bb29ae. Este módulo no
rellena medidas ni asigna roles: solo produce hallazgos internos trazables.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
import json
from math import atan2, cos, degrees, hypot, isfinite, radians, sin
from pathlib import Path
from typing import Any

from backend.app.contratos.modelos import DrawingExtraction


DIMENSION_ATTACH_TOLERANCE_MM = 0.5
MAX_DIMENSIONS_CHECKED = 200
PANDEO_WARNING_CODE = "pandeo_luz_excesiva"
HORIZONTAL_LOAD_BEARING_ROLES = frozenset(
    {"shelf", "top_panel", "tabletop", "balda", "tapa", "estante", "encimera", "sobre"}
)
VERTICAL_SUPPORT_ROLES = frozenset(
    {
        "divider",
        "montante",
        "vertical_divider",
        "intermediate_support",
        "central_support",
        "vertical_support",
    }
)
DEFAULT_DEFLECTION_THRESHOLDS: tuple[tuple[float, float], ...] = (
    (30.0, 1400.0),
    (25.0, 1200.0),
    (19.0, 950.0),
    (18.0, 900.0),
    (16.0, 750.0),
)
DEFAULT_SPAN_TO_THICKNESS_RATIO = 45.0


@dataclass(frozen=True)
class _SpanThreshold:
    min_thickness_mm: float
    max_span_mm: float


@dataclass(frozen=True)
class _DeflectionLimits:
    default_thresholds: tuple[_SpanThreshold, ...]
    material_overrides: dict[str, tuple[_SpanThreshold, ...]]
    fallback_span_to_thickness_ratio: float


@dataclass(frozen=True)
class _DrillingSystem:
    id: str
    label: str
    pitch_mm: float
    hole_diameter_mm: float
    setback_mm: float | None


@dataclass(frozen=True)
class _Catalog:
    source: str
    confirmed_by_workshop: bool
    tolerance_mm: float
    drilling_systems: tuple[_DrillingSystem, ...]
    deflection_limits: _DeflectionLimits


def _positive_number(value: object, field: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"workshop_catalog_invalid:{field}")
    result = float(value)
    if not isfinite(result) or result <= 0:
        raise ValueError(f"workshop_catalog_invalid:{field}")
    return result


def _default_deflection_limits() -> _DeflectionLimits:
    return _DeflectionLimits(
        default_thresholds=tuple(
            _SpanThreshold(min_thickness_mm=thickness, max_span_mm=span)
            for thickness, span in DEFAULT_DEFLECTION_THRESHOLDS
        ),
        material_overrides={},
        fallback_span_to_thickness_ratio=DEFAULT_SPAN_TO_THICKNESS_RATIO,
    )


def _parse_threshold_table(raw: object, field: str) -> tuple[_SpanThreshold, ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"workshop_catalog_invalid:{field}")
    thresholds: list[_SpanThreshold] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"workshop_catalog_invalid:{field}[{index}]")
        min_thickness = _positive_number(
            entry.get("min_thickness_mm"), f"{field}[{index}].min_thickness_mm"
        )
        max_span = _positive_number(entry.get("max_span_mm"), f"{field}[{index}].max_span_mm")
        assert min_thickness is not None and max_span is not None
        thresholds.append(
            _SpanThreshold(min_thickness_mm=min_thickness, max_span_mm=max_span)
        )
    thresholds.sort(key=lambda item: item.min_thickness_mm, reverse=True)
    return tuple(thresholds)


def _parse_deflection_limits(raw: object) -> _DeflectionLimits:
    if raw is None:
        return _default_deflection_limits()
    if not isinstance(raw, dict):
        raise ValueError("workshop_catalog_invalid:deflection_limits")
    default_raw = raw.get("default_max_span_by_thickness_mm")
    default_thresholds = (
        _parse_threshold_table(default_raw, "deflection_limits.default_max_span_by_thickness_mm")
        if default_raw is not None
        else _default_deflection_limits().default_thresholds
    )
    overrides_raw = raw.get("material_overrides", {})
    if not isinstance(overrides_raw, dict):
        raise ValueError("workshop_catalog_invalid:deflection_limits.material_overrides")
    overrides: dict[str, tuple[_SpanThreshold, ...]] = {}
    for material_key, table in overrides_raw.items():
        if not isinstance(material_key, str) or not material_key.strip():
            raise ValueError("workshop_catalog_invalid:deflection_limits.material_overrides.key")
        overrides[material_key.strip().lower()] = _parse_threshold_table(
            table, f"deflection_limits.material_overrides.{material_key}"
        )
    ratio = _positive_number(
        raw.get("fallback_span_to_thickness_ratio", DEFAULT_SPAN_TO_THICKNESS_RATIO),
        "deflection_limits.fallback_span_to_thickness_ratio",
    )
    assert ratio is not None
    return _DeflectionLimits(
        default_thresholds=default_thresholds,
        material_overrides=overrides,
        fallback_span_to_thickness_ratio=ratio,
    )


def _parse_catalog(payload: object) -> _Catalog:
    if not isinstance(payload, dict):
        raise ValueError("workshop_catalog_invalid:root")
    source = payload.get("source")
    confirmed = payload.get("confirmed_by_workshop", False)
    systems = payload.get("drilling_systems", [])
    if not isinstance(source, str) or not source.strip():
        raise ValueError("workshop_catalog_invalid:source")
    if not isinstance(confirmed, bool):
        raise ValueError("workshop_catalog_invalid:confirmed_by_workshop")
    if not isinstance(systems, list):
        raise ValueError("workshop_catalog_invalid:drilling_systems")
    parsed = []
    for index, item in enumerate(systems):
        if not isinstance(item, dict):
            raise ValueError(f"workshop_catalog_invalid:drilling_systems[{index}]")
        system_id = item.get("id")
        label = item.get("label")
        if not isinstance(system_id, str) or not system_id or not isinstance(label, str) or not label:
            raise ValueError(f"workshop_catalog_invalid:drilling_systems[{index}].identity")
        parsed.append(
            _DrillingSystem(
                id=system_id,
                label=label,
                pitch_mm=_positive_number(item.get("pitch_mm"), f"{system_id}.pitch_mm"),
                hole_diameter_mm=_positive_number(
                    item.get("hole_diameter_mm"), f"{system_id}.hole_diameter_mm"
                ),
                setback_mm=_positive_number(
                    item.get("setback_mm"), f"{system_id}.setback_mm", optional=True
                ),
            )
        )
    return _Catalog(
        source=source,
        confirmed_by_workshop=confirmed,
        tolerance_mm=_positive_number(payload.get("tolerance_mm", 0.1), "tolerance_mm"),
        drilling_systems=tuple(parsed),
        deflection_limits=_parse_deflection_limits(payload.get("deflection_limits")),
    )


def _load_catalog(path: Path | None) -> _Catalog:
    try:
        if path is None:
            catalog_file = resources.files("backend.app.validador").joinpath("catalogo_taller.json")
            text = catalog_file.read_text(encoding="utf-8")
        else:
            text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError("workshop_catalog_not_found") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("workshop_catalog_invalid:json") from exc
    return _parse_catalog(payload)


def _circle(entity: object) -> tuple[float, float, float] | None:
    circular = getattr(entity, "circular", None)
    center = getattr(circular, "center_mm", None)
    radius = getattr(circular, "radius_mm", None)
    if (
        circular is None
        or str(getattr(circular, "kind", "")).lower() != "circle"
        or center is None
        or radius is None
    ):
        return None
    values = (float(center.x), float(center.y), float(radius))
    return values if all(isfinite(value) for value in values) and values[2] > 0 else None


def _row_measurements(
    circles: list[tuple[float, float, float]], tolerance: float
) -> tuple[float | None, float | None, tuple[float, float] | None]:
    if len(circles) < 3:
        return None, None, None
    radii = [circle[2] for circle in circles]
    if max(radii) - min(radii) > tolerance:
        return None, None, None
    endpoints = max(
        ((left, right) for left in circles for right in circles),
        key=lambda pair: hypot(pair[1][0] - pair[0][0], pair[1][1] - pair[0][1]),
    )
    dx = endpoints[1][0] - endpoints[0][0]
    dy = endpoints[1][1] - endpoints[0][1]
    length = hypot(dx, dy)
    if length <= tolerance:
        return 2 * sum(radii) / len(radii), None, None
    direction = (dx / length, dy / length)
    origin = endpoints[0]
    if any(abs((x - origin[0]) * direction[1] - (y - origin[1]) * direction[0]) > tolerance for x, y, _ in circles):
        return 2 * sum(radii) / len(radii), None, None
    along = sorted((x - origin[0]) * direction[0] + (y - origin[1]) * direction[1] for x, y, _ in circles)
    spacings = [right - left for left, right in zip(along, along[1:])]
    pitch = sum(spacings) / len(spacings)
    if pitch <= 0 or max(abs(spacing - pitch) for spacing in spacings) > tolerance:
        return 2 * sum(radii) / len(radii), None, direction
    return 2 * sum(radii) / len(radii), pitch, direction


def _polygon_area(points: list[tuple[float, float]]) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]))) / 2


def _inside(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def _setback(
    extraction: DrawingExtraction,
    view_id: str,
    centers: list[tuple[float, float]],
    direction: tuple[float, float] | None,
) -> float | None:
    if direction is None:
        return None
    candidates: list[tuple[float, float]] = []
    for contour in extraction.contours:
        if contour.view_id != view_id or not contour.closed or not contour.points_mm:
            continue
        polygon = [(float(point.x), float(point.y)) for point in contour.points_mm]
        if len(polygon) > 1 and polygon[0] == polygon[-1]:
            polygon.pop()
        if len(polygon) < 3 or not all(_inside(center, polygon) for center in centers):
            continue
        distances = []
        for start, end in zip(polygon, polygon[1:] + polygon[:1]):
            edge_x, edge_y = end[0] - start[0], end[1] - start[1]
            edge_length = hypot(edge_x, edge_y)
            if edge_length == 0:
                continue
            edge_direction = (edge_x / edge_length, edge_y / edge_length)
            if abs(direction[0] * edge_direction[1] - direction[1] * edge_direction[0]) > 1e-6:
                continue
            distances.append(
                abs((centers[0][0] - start[0]) * edge_direction[1] - (centers[0][1] - start[1]) * edge_direction[0])
            )
        if distances:
            candidates.append((_polygon_area(polygon), min(distances)))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _best_system(
    systems: tuple[_DrillingSystem, ...], diameter: float | None, pitch: float | None, setback: float | None
) -> _DrillingSystem | None:
    complete = [system for system in systems if system.setback_mm is not None]
    if not complete or diameter is None or pitch is None or setback is None:
        return complete[0] if complete else None
    return min(
        complete,
        key=lambda system: abs(diameter - system.hole_diameter_mm)
        + abs(pitch - system.pitch_mm)
        + abs(setback - system.setback_mm),
    )


def _point_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return hypot(point[0] - start[0], point[1] - start[1])
    projection = max(
        0.0,
        min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared),
    )
    nearest = start[0] + projection * dx, start[1] + projection * dy
    return hypot(point[0] - nearest[0], point[1] - nearest[1])


def _feature_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    measurement_direction: tuple[float, float],
) -> float:
    """Distance to an endpoint or to a feature line transverse to the measured axis."""
    endpoint_distance = min(
        hypot(point[0] - start[0], point[1] - start[1]),
        hypot(point[0] - end[0], point[1] - end[1]),
    )
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = hypot(dx, dy)
    if length == 0:
        return endpoint_distance
    alignment = abs(
        (dx / length) * measurement_direction[0]
        + (dy / length) * measurement_direction[1]
    )
    if alignment <= 1e-6:
        return min(endpoint_distance, _point_segment_distance(point, start, end))
    return endpoint_distance


def _angle_on_arc(angle: float, start: float, end: float, tolerance_deg: float = 1e-7) -> bool:
    sweep = (end - start) % 360.0
    offset = (angle - start) % 360.0
    return offset <= sweep + tolerance_deg


def _circular_distance(point: tuple[float, float], circular: object) -> float:
    center = circular.center_mm
    radius = float(circular.radius_mm)
    radial = hypot(point[0] - center.x, point[1] - center.y)
    if circular.kind == "circle":
        return abs(radial - radius)
    angle = degrees(atan2(point[1] - center.y, point[0] - center.x)) % 360.0
    if _angle_on_arc(angle, float(circular.start_angle_deg), float(circular.end_angle_deg)):
        return abs(radial - radius)
    endpoints = []
    for degrees_value in (float(circular.start_angle_deg), float(circular.end_angle_deg)):
        radians_value = radians(degrees_value)
        endpoints.append(
            (
                center.x + radius * cos(radians_value),
                center.y + radius * sin(radians_value),
            )
        )
    return min(hypot(point[0] - x, point[1] - y) for x, y in endpoints)


def _dimension_findings(extraction: DrawingExtraction) -> list[dict[str, Any]]:
    if extraction.coordinate_unit != "mm":
        return []
    entities = {entity.id: entity for entity in extraction.entities}
    closed_entity_ids = {
        entity_id
        for contour in extraction.contours
        if contour.closed
        for entity_id in contour.source_entity_ids
    }
    geometry_by_view: dict[str, list[object]] = {}
    for view in extraction.views:
        geometry = []
        for entity_id in view.entity_ids:
            entity = entities.get(entity_id)
            if entity is None or entity.kind in {"DIMENSION", "TEXT", "MTEXT", "ATTRIB"}:
                continue
            circular = entity.circular
            if circular is not None and circular.center_mm is not None and circular.radius_mm is not None:
                geometry.append(("circular", circular))
                continue
            if not entity.points_mm or len(entity.points_mm) < 2:
                continue
            points = [(point.x, point.y) for point in entity.points_mm]
            pairs = list(zip(points, points[1:]))
            if entity_id in closed_entity_ids and points[0] != points[-1]:
                pairs.append((points[-1], points[0]))
            geometry.extend(("segment", pair) for pair in pairs)
        geometry_by_view[view.id] = geometry

    evidence_by_dimension = {
        dimension.id: list(dimension.evidence_ids) for dimension in extraction.dimensions
    }
    result = []
    for graphic in extraction.dimension_graphics[:MAX_DIMENSIONS_CHECKED]:
        anchors = (graphic.extension_start_a_mm, graphic.extension_start_b_mm)
        dimension_line = (graphic.dimension_start_mm, graphic.dimension_end_mm)
        geometry = geometry_by_view.get(graphic.view_id, [])
        if (
            any(anchor is None for anchor in anchors)
            or any(point is None for point in dimension_line)
            or not geometry
        ):
            continue
        line_dx = dimension_line[1].x - dimension_line[0].x
        line_dy = dimension_line[1].y - dimension_line[0].y
        line_length = hypot(line_dx, line_dy)
        if line_length <= 1e-9:
            continue
        measurement_direction = line_dx / line_length, line_dy / line_length
        distances = []
        for anchor in anchors:
            point = (anchor.x, anchor.y)
            distances.append(
                min(
                    _circular_distance(point, value)
                    if kind == "circular"
                    else _feature_segment_distance(
                        point, value[0], value[1], measurement_direction
                    )
                    for kind, value in geometry
                )
            )
        worst = max(distances)
        passed = worst <= DIMENSION_ATTACH_TOLERANCE_MM
        result.append(
            {
                "id": f"plausibility-{graphic.dimension_id}",
                "check": "dimension_attached_to_geometry",
                "status": "pass" if passed else "fail",
                "message": (
                    "Los dos puntos medidos por la cota se apoyan en geometría dibujada de su vista."
                    if passed
                    else f"Un punto medido por la cota queda a {worst:.1f} mm de la geometría dibujada más cercana; la cota debe revisarse."
                ),
                "system_id": None,
                "observed": {"maximum_attachment_gap_mm": worst},
                "evidence_ids": evidence_by_dimension.get(graphic.dimension_id, []),
                "entity_ids": [graphic.source_entity_id],
            }
        )
    return result


def _piece_field(piece: Any, name: str, default: Any = None) -> Any:
    if isinstance(piece, Mapping):
        return piece.get(name, default)
    return getattr(piece, name, default)


def _known_positive_mm(piece: Any, field_name: str) -> float | None:
    field_states = _piece_field(piece, "field_states")
    if isinstance(field_states, Mapping) and field_states.get(field_name) == "unknown":
        return None
    raw = _piece_field(piece, field_name)
    if raw is None or isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if not isfinite(value) or value <= 0:
        return None
    return value


def _normalized_role(piece: Any) -> str:
    role = _piece_field(piece, "role")
    if not isinstance(role, str) or not role.strip():
        role = _piece_field(piece, "kind", "")
    return role.strip().lower() if isinstance(role, str) else ""


def _max_span_for_piece(
    limits: _DeflectionLimits, thickness_mm: float, material: str | None
) -> float:
    thresholds = limits.default_thresholds
    if isinstance(material, str) and material.strip():
        normalized = material.strip().lower()
        for key in sorted(limits.material_overrides, key=len, reverse=True):
            if key in normalized:
                thresholds = limits.material_overrides[key]
                break
    for threshold in thresholds:
        if thickness_mm >= threshold.min_thickness_mm:
            return threshold.max_span_mm
    return thickness_mm * limits.fallback_span_to_thickness_ratio


def _count_intermediate_supports(
    piece: Any,
    pieces: Sequence[Any],
    explicit_supports: int | None,
    has_explicit_support: bool | None,
) -> int:
    if explicit_supports is not None:
        return max(0, explicit_supports)
    if has_explicit_support is not None:
        return 1 if has_explicit_support else 0
    piece_supports = _piece_field(piece, "intermediate_supports")
    if piece_supports is None:
        piece_supports = _piece_field(piece, "support_count")
    if isinstance(piece_supports, int) and not isinstance(piece_supports, bool):
        return max(0, piece_supports)
    piece_has_support = _piece_field(piece, "has_intermediate_support")
    if isinstance(piece_has_support, bool):
        return 1 if piece_has_support else 0
    return 0


def _deflection_findings(
    pieces: Sequence[Any],
    catalog: _Catalog,
    *,
    intermediate_supports: int | None = None,
    has_intermediate_support: bool | None = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, piece in enumerate(pieces):
        role = _normalized_role(piece)
        if role not in HORIZONTAL_LOAD_BEARING_ROLES:
            continue
        length_mm = _known_positive_mm(piece, "length_mm")
        thickness_mm = _known_positive_mm(piece, "thickness_mm")
        if length_mm is None or thickness_mm is None:
            continue
        piece_id = str(_piece_field(piece, "id") or f"piece-{index}")
        piece_label = str(_piece_field(piece, "label") or piece_id)
        material_raw = _piece_field(piece, "material")
        material = material_raw.strip() if isinstance(material_raw, str) and material_raw.strip() else None
        supports = _count_intermediate_supports(
            piece, pieces, intermediate_supports, has_intermediate_support
        )
        effective_span_mm = length_mm / (supports + 1)
        max_span_mm = _max_span_for_piece(catalog.deflection_limits, thickness_mm, material)
        exceeded = effective_span_mm > max_span_mm
        evidence_ids = _piece_field(piece, "evidence_ids") or ()
        entity_ids = _piece_field(piece, "source_entity_ids") or ()
        if exceeded:
            support_note = (
                "sin apoyo intermedio"
                if supports == 0
                else f"con {supports} apoyo(s) intermedio(s) (luz por vano {effective_span_mm:.0f} mm)"
            )
            message = (
                f"Posible pandeo en '{piece_label}' ({piece_id}): luz de {length_mm:.0f} mm "
                f"con espesor de {thickness_mm:g} mm ({support_note}) supera el máximo "
                f"recomendado de {max_span_mm:.0f} mm."
            )
            if not catalog.confirmed_by_workshop:
                message = f"Aviso orientativo basado en un catálogo no confirmado por el taller. {message}"
        else:
            message = (
                f"Luz admisible en '{piece_label}' ({piece_id}): {effective_span_mm:.0f} mm "
                f"con espesor de {thickness_mm:g} mm dentro del máximo de {max_span_mm:.0f} mm."
            )
            if not catalog.confirmed_by_workshop:
                message = (
                    "Comprobación orientativa sin pase estructural: el catálogo no está confirmado "
                    f"por el taller. {message}"
                )
        status = "warning" if exceeded else ("pass" if catalog.confirmed_by_workshop else "unknown")
        findings.append(
            {
                "id": f"plausibility-pandeo-{piece_id}",
                "check": "structural_deflection",
                "code": PANDEO_WARNING_CODE if exceeded else None,
                "status": status,
                "severity": "warning" if exceeded else "info",
                "message": message,
                "system_id": None,
                "catalog": {
                    "source": catalog.source,
                    "confirmed_by_workshop": catalog.confirmed_by_workshop,
                    "authority": (
                        "confirmed_workshop_catalog"
                        if catalog.confirmed_by_workshop
                        else "advisory_unconfirmed_catalog"
                    ),
                },
                "observed": {
                    "piece_id": piece_id,
                    "piece_label": piece_label,
                    "role": role,
                    "length_mm": length_mm,
                    "effective_span_mm": effective_span_mm,
                    "thickness_mm": thickness_mm,
                    "max_span_mm": max_span_mm,
                    "intermediate_supports": supports,
                    "material": material,
                },
                "evidence_ids": list(evidence_ids),
                "entity_ids": list(entity_ids),
            }
        )
    return findings


def evaluate_deflection_plausibility(
    pieces: Sequence[Any],
    *,
    intermediate_supports: int | None = None,
    has_intermediate_support: bool | None = None,
    catalog_path: Path | None = None,
) -> tuple[dict[str, Any], ...]:
    """Evalúa pandeo por luz excesiva en piezas horizontales portantes sin inventar cotas."""
    catalog = _load_catalog(catalog_path)
    return tuple(
        _deflection_findings(
            pieces,
            catalog,
            intermediate_supports=intermediate_supports,
            has_intermediate_support=has_intermediate_support,
        )
    )


def evaluate_plausibility(
    extraction: DrawingExtraction,
    catalog_path: Path | None = None,
    *,
    pieces: Sequence[Any] | None = None,
) -> tuple[dict, ...]:
    """Devuelve hallazgos internos sin modificar ni completar la extracción."""
    catalog = _load_catalog(catalog_path)
    entities = {entity.id: entity for entity in extraction.entities}
    findings: list[dict[str, Any]] = []
    for evidence in extraction.evidence:
        if evidence.kind != "geometry" or not evidence.id.startswith("evidence-holes-"):
            continue
        row_entities = [entities.get(entity_id) for entity_id in evidence.source_entity_ids]
        circles = [_circle(entity) for entity in row_entities if entity is not None]
        circles = [circle for circle in circles if circle is not None]
        views = [
            view
            for view in extraction.views
            if set(evidence.source_entity_ids) <= set(view.entity_ids)
        ]
        if len(circles) != len(evidence.source_entity_ids):
            diameter, pitch, direction = None, None, None
        else:
            diameter, pitch, direction = _row_measurements(circles, catalog.tolerance_mm)
        centers = [(circle[0], circle[1]) for circle in circles]
        setback = _setback(extraction, views[0].id, centers, direction) if len(views) == 1 else None
        system = _best_system(catalog.drilling_systems, diameter, pitch, setback)
        complete = diameter is not None and pitch is not None and setback is not None and system is not None
        matches = complete and all(
            abs(observed - expected) <= catalog.tolerance_mm
            for observed, expected in (
                (diameter, system.hole_diameter_mm),
                (pitch, system.pitch_mm),
                (setback, system.setback_mm),
            )
        )
        if not catalog.confirmed_by_workshop or not complete:
            status = "unknown"
            message = "Catálogo no confirmado o geometría insuficiente; requiere revisión humana."
        elif matches:
            status = "pass"
            message = f"La fila coincide con {system.label} dentro de la tolerancia del taller."
        else:
            status = "fail"
            message = f"La fila no coincide con {system.label} en todas sus medidas."
        findings.append(
            {
                "id": f"plausibility-{evidence.id}",
                "check": "hole_row_drilling_system",
                "status": status,
                "message": message,
                "system_id": system.id if system is not None else None,
                "observed": {
                    "diameter_mm": diameter,
                    "pitch_mm": pitch,
                    "setback_mm": setback,
                },
                "evidence_ids": [evidence.id],
                "entity_ids": list(evidence.source_entity_ids),
            }
        )
    findings.extend(_dimension_findings(extraction))
    if pieces:
        findings.extend(_deflection_findings(pieces, catalog))
    return tuple(findings)
