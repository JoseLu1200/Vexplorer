from __future__ import annotations

from backend.app.contratos.modelos import ComponentProposal, DecompositionScenario, DrawingContour, DrawingExtraction


def _axis_aligned_rectangle_size(contour: DrawingContour, tolerance_mm: float = 1e-6) -> tuple[float, float] | None:
    """Accept only a closed four-corner rectangle supported by source entities."""
    if not contour.closed or not contour.source_entity_ids or contour.points_mm is None or len(contour.points_mm) != 4:
        return None
    xs = [point.x for point in contour.points_mm]
    ys = [point.y for point in contour.points_mm]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    if max_x - min_x <= tolerance_mm or max_y - min_y <= tolerance_mm:
        return None
    expected = ((min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y))
    for x, y in expected:
        if not any(abs(point.x - x) <= tolerance_mm and abs(point.y - y) <= tolerance_mm for point in contour.points_mm):
            return None
    for index, point in enumerate(contour.points_mm):
        following = contour.points_mm[(index + 1) % 4]
        horizontal = abs(point.y - following.y) <= tolerance_mm
        vertical = abs(point.x - following.x) <= tolerance_mm
        if horizontal == vertical:
            return None
    return max_x - min_x, max_y - min_y


def resolve_orthographic_dimensions(front: tuple[float, float], top: tuple[float, float], side: tuple[float, float], tolerance_mm: float = 0.1) -> tuple[float, float, float] | None:
    """Resolve FRONT=(W,H), TOP=(W,D), SIDE=(D,H) without sorting axes."""
    width, height = front
    top_width, depth = top
    side_depth, side_height = side
    if abs(width - top_width) > tolerance_mm or abs(height - side_height) > tolerance_mm or abs(depth - side_depth) > tolerance_mm:
        return None
    return width, height, depth


MIN_PLAUSIBLE_THICKNESS_MM = 3.0
MAX_THICKNESS_FRACTION_OF_WIDTH = 0.1


def _inner_vertical_gaps(extraction: DrawingExtraction, contour: DrawingContour, tolerance_mm: float = 1e-6) -> list[tuple[float, str]]:
    """Inner vertical LINEs spanning a view outline, as (distance to the nearest vertical edge, entity id)."""
    xs = [point.x for point in contour.points_mm or ()]
    ys = [point.y for point in contour.points_mm or ()]
    if not xs:
        return []
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    height = max_y - min_y
    gaps: list[tuple[float, str]] = []
    for entity in extraction.entities:
        if entity.kind != "LINE" or not entity.points_mm or len(entity.points_mm) != 2:
            continue
        first, second = entity.points_mm
        low, high = min(first.y, second.y), max(first.y, second.y)
        if abs(first.x - second.x) > tolerance_mm or not min_x + tolerance_mm < first.x < max_x - tolerance_mm:
            continue
        if low < min_y - tolerance_mm or high > max_y + tolerance_mm or high - low < 0.8 * height:
            continue
        gaps.append((min(first.x - min_x, max_x - first.x), entity.id))
    return gaps


def observe_side_thickness(extraction: DrawingExtraction, front: DrawingContour, top: DrawingContour, overall_width: float) -> tuple[float, tuple[str, ...]] | None:
    """Side-panel thickness drawn as symmetric inner vertical lines in FRONT and repeated in TOP.

    Returns None unless exactly one symmetric gap exists in FRONT and TOP shows the same gap: an observation to be
    confirmed by a person, never a measurement of the other panels.
    """
    low, high = MIN_PLAUSIBLE_THICKNESS_MM, MAX_THICKNESS_FRACTION_OF_WIDTH * overall_width
    front_gaps = [item for item in _inner_vertical_gaps(extraction, front) if low <= item[0] <= high]
    candidates = sorted({round(gap, 3) for gap, _ in front_gaps})
    values = [value for value in candidates if sum(1 for gap, _ in front_gaps if abs(gap - value) <= 0.1) >= 2]
    if len(values) != 1:
        return None
    value = values[0]
    front_ids = tuple(entity_id for gap, entity_id in front_gaps if abs(gap - value) <= 0.1)
    top_ids = tuple(entity_id for gap, entity_id in _inner_vertical_gaps(extraction, top) if abs(gap - value) <= 0.1)
    if not top_ids:
        return None
    return value, tuple(sorted(set(front_ids) | set(top_ids)))


def derive_decomposition_scenarios(extraction: DrawingExtraction) -> tuple[DecompositionScenario, ...]:
    """Apply explicit rectangular-shelving hypotheses to observed mounted views."""
    view_labels = {view.id: view.label for view in extraction.views}
    by_label: dict[str, list[DrawingContour]] = {}
    for contour in extraction.contours:
        if _axis_aligned_rectangle_size(contour) is not None:
            by_label.setdefault(view_labels.get(contour.view_id, "UNKNOWN"), []).append(contour)
    if not all(by_label.get(label) for label in ("FRONT", "TOP", "SIDE")):
        return ()
    front = max(by_label["FRONT"], key=lambda item: _axis_aligned_rectangle_size(item)[0] * _axis_aligned_rectangle_size(item)[1])
    top = max(by_label["TOP"], key=lambda item: _axis_aligned_rectangle_size(item)[0] * _axis_aligned_rectangle_size(item)[1])
    side = max(by_label["SIDE"], key=lambda item: _axis_aligned_rectangle_size(item)[0] * _axis_aligned_rectangle_size(item)[1])
    resolved = resolve_orthographic_dimensions(
        _axis_aligned_rectangle_size(front), _axis_aligned_rectangle_size(top), _axis_aligned_rectangle_size(side)
    )
    if resolved is None:
        return ()
    overall_width, overall_height, depth = resolved

    front_xs = [point.x for point in front.points_mm or ()]
    front_ys = [point.y for point in front.points_mm or ()]
    min_x, max_x = min(front_xs), max(front_xs)
    min_y, max_y = min(front_ys), max(front_ys)
    front_lines: list[tuple[float, str]] = []
    side_xs = [point.x for point in side.points_mm or ()]
    side_ys = [point.y for point in side.points_mm or ()]
    side_min_x, side_max_x = min(side_xs), max(side_xs)
    side_min_y, side_max_y = min(side_ys), max(side_ys)
    side_lines: list[tuple[float, str]] = []
    for entity in extraction.entities:
        if entity.kind != "LINE" or not entity.points_mm or len(entity.points_mm) != 2:
            continue
        first, second = entity.points_mm
        if abs(first.y - second.y) > 1e-6:
            continue
        span = abs(first.x - second.x)
        if span >= 0.8 * overall_width and min_y < first.y < max_y and min(first.x, second.x) <= min_x + 0.1 * overall_width and max(first.x, second.x) >= max_x - 0.1 * overall_width:
            front_lines.append(((first.y - min_y) / overall_height, entity.id))
        if span >= 0.8 * depth and side_min_y < first.y < side_max_y and min(first.x, second.x) <= side_min_x + 0.1 * depth and max(first.x, second.x) >= side_max_x - 0.1 * depth:
            side_lines.append(((first.y - side_min_y) / overall_height, entity.id))
    matched_lines: list[str] = []
    for front_level, front_id in sorted(front_lines):
        match = next(((level, entity_id) for level, entity_id in side_lines if abs(front_level - level) <= 0.02 and entity_id not in matched_lines), None)
        if match:
            matched_lines.extend((front_id, match[1]))
    shelf_quantity = len(matched_lines) // 2 or None

    contour_ids = (front.id, top.id, side.id)
    observation_ids = tuple(item.id for item in extraction.observations if set(item.contour_ids) & set(contour_ids))
    entity_ids = set(front.source_entity_ids) | set(top.source_entity_ids) | set(side.source_entity_ids)
    evidence_ids = tuple(item.id for item in extraction.evidence if set(item.source_entity_ids) & entity_ids)
    common = dict(source_observation_ids=observation_ids, source_contour_ids=contour_ids, evidence_ids=evidence_ids)
    observed_thickness = observe_side_thickness(extraction, front, top, overall_width)

    def proposal(scenario: str, role: str, label: str, quantity: int | None, length: float | None, derivation: str, basis: float) -> ComponentProposal:
        assumptions = ["Regla familiar para estantería rectangular; la proyección montada no demuestra cada pieza."]
        thickness_fields: dict = {}
        if role == "side_panel" and observed_thickness is not None:
            thickness_fields = dict(observed_thickness_mm=observed_thickness[0], thickness_source_entity_ids=observed_thickness[1])
            assumptions.append(f"Espesor observado de {observed_thickness[0]:g} mm por líneas verticales interiores simétricas en alzado y repetidas en planta; es una observación de los laterales que una persona debe confirmar, no se aplica a otras piezas.")
        if quantity is None:
            assumptions.append("Cantidad de baldas interiores no respaldada por líneas horizontales suficientes.")
        source_entity_ids = tuple(matched_lines) if role == "shelf" else tuple(sorted(entity_ids))
        return ComponentProposal(id=f"proposal-{scenario}-{role}", label=label, role=role, quantity=quantity, length_mm=length, width_mm=depth, thickness_mm=None, length_derivation=derivation, length_basis_mm=basis, assumptions=tuple(assumptions), source_entity_ids=source_entity_ids, **thickness_fields, **common)

    between_key = "between-sides"
    cap_key = "cap-sides"
    between = DecompositionScenario(
        id="scenario-between-sides", title="Tapa y base entre laterales",
        components=(
            proposal(between_key, "side_panel", "Laterales", 2, overall_height, "direct_observation", overall_height),
            proposal(between_key, "top_panel", "Tapa", 1, None, "overall_width_minus_two_thickness", overall_width),
            proposal(between_key, "base_panel", "Base", 1, None, "overall_width_minus_two_thickness", overall_width),
            proposal(between_key, "shelf", "Baldas interiores", shelf_quantity, None, "overall_width_minus_two_thickness", overall_width),
        ),
        assumptions=("Tapa, base y baldas se montan entre dos laterales; confirmar espesor y montaje.",),
        incompatible_with=("scenario-cap-sides",),
    )
    capped = DecompositionScenario(
        id="scenario-cap-sides", title="Tapa y base cubren laterales",
        components=(
            proposal(cap_key, "side_panel", "Laterales", 2, None, "overall_height_minus_two_thickness", overall_height),
            proposal(cap_key, "top_panel", "Tapa", 1, overall_width, "direct_observation", overall_width),
            proposal(cap_key, "base_panel", "Base", 1, overall_width, "direct_observation", overall_width),
            proposal(cap_key, "shelf", "Baldas interiores", shelf_quantity, None, "overall_width_minus_two_thickness", overall_width),
        ),
        assumptions=("Tapa y base cubren los extremos de los laterales; confirmar espesor y montaje.",),
        incompatible_with=("scenario-between-sides",),
    )
    return between, capped
