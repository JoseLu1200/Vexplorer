from __future__ import annotations

from collections import defaultdict
from math import sqrt

from backend.app.contratos.modelos import (
    Bounds2D,
    Bounds3D,
    DrawingExtraction,
    GeneralAssemblyCandidate,
    GeneralAssemblyContext,
    GeneralAssemblyContextComponent,
    GeneralAssemblyContextContour,
    GeneralAssemblyContextRegion,
    GeneralAssemblyFrame,
    GeneralAssemblyPlacement,
    GeneralAssemblyValidationIssue,
    GeneralAssemblyValidationReport,
    GeneralFurnitureReview,
    GeneralScene,
    GeneralSceneItem,
    Point3D,
    Size3D,
)
from backend.app.general_furniture.measurements import derive_geometry_measurements
from backend.app.general_furniture.projection_hypotheses import derive_source_spatial_regions

_NUMERICAL_EPSILON_MM = 1e-6
_BOX_FIT_TOLERANCE_MM = 0.01
_REPROJECTION_TOLERANCE_MM = 0.5
_DIMENSION_TOLERANCE_MM = 0.5
_PENETRATION_TOLERANCE_MM = 1.0
_RELIABLE_STATES = {"observed", "derived", "confirmed"}


def _bounds(points: object) -> Bounds2D:
    xs = [float(point.x) for point in points]  # type: ignore[attr-defined]
    ys = [float(point.y) for point in points]  # type: ignore[attr-defined]
    return Bounds2D(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys))


def _box_fit_residual(points: object) -> float:
    values = [(float(point.x), float(point.y)) for point in points]  # type: ignore[attr-defined]
    if len(values) > 1 and values[0] == values[-1]:
        values.pop()
    xs = [value[0] for value in values]
    ys = [value[1] for value in values]
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    box_area = span_x * span_y
    if box_area <= _NUMERICAL_EPSILON_MM:
        return max(span_x, span_y, _NUMERICAL_EPSILON_MM)
    area = abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(values, values[1:] + values[:1]))) / 2
    return sqrt(max(0.0, box_area - area))


def build_assembly_context(
    extraction: DrawingExtraction, review: GeneralFurnitureReview
) -> GeneralAssemblyContext:
    if (
        extraction.source_unit == "unknown"
        or extraction.coordinate_unit != "mm"
        or extraction.unit_scale_to_mm is None
        or any(item.points_mm is None for item in extraction.contours)
    ):
        raise ValueError("assembly_metric_scale_required")
    measurements = derive_geometry_measurements(extraction)
    source_regions = derive_source_spatial_regions(extraction, measurements)
    contours = {item.id: item for item in extraction.contours}
    evidence_by_entity: dict[str, set[str]] = defaultdict(set)
    for evidence in extraction.evidence:
        for entity_id in evidence.source_entity_ids:
            evidence_by_entity[entity_id].add(evidence.id)
    regions: list[GeneralAssemblyContextRegion] = []
    context_contours: list[GeneralAssemblyContextContour] = []
    for region in source_regions:
        selected = [contours[value] for value in region.source_contour_ids]
        metric_points = tuple(
            point for contour in selected for point in (contour.points_mm or ())
        )
        metric_bounds = _bounds(metric_points)
        view_id = region.source_view_ids[0]
        regions.append(
            GeneralAssemblyContextRegion(
                id=region.id,
                view_id=view_id,
                bounds_source=Bounds2D(
                    min_x=region.bounds_source[0], min_y=region.bounds_source[1],
                    max_x=region.bounds_source[2], max_y=region.bounds_source[3],
                ),
                bounds_mm=metric_bounds,
                contour_ids=region.source_contour_ids,
            )
        )
        for contour in selected:
            contour_evidence = tuple(sorted({value for entity_id in contour.source_entity_ids for value in evidence_by_entity[entity_id]}))
            context_contours.append(
                GeneralAssemblyContextContour(
                    id=contour.id, view_id=view_id, region_id=region.id,
                    bounds_mm=_bounds(contour.points_mm or ()),
                    evidence_ids=contour_evidence,
                    source_entity_ids=contour.source_entity_ids,
                    box_fit_residual_mm=_box_fit_residual(contour.points_mm or ()),
                )
            )
    occurrences: dict[str, list[str]] = defaultdict(list)
    for item in review.occurrences:
        occurrences[item.component_id].append(item.id)
    provisional_occurrences: dict[str, list[str]] = defaultdict(list)
    for item in review.scenario_occurrences:
        provisional_occurrences[item.component_id].append(item.id)
    ledger_refs = {
        *(f"contour:{item.id}" for item in extraction.contours),
        *(f"evidence:{item.id}" for item in extraction.evidence),
        *(f"dimension:{item.id}" for item in extraction.dimensions),
        *(f"view:{item.id}" for item in extraction.views),
    }
    components: list[GeneralAssemblyContextComponent] = []
    for item in review.components:
        if item.kind != "panel":
            raise ValueError("assembly_unsupported_component_kind")
        component_source_refs = {
            *(f"contour:{value}" for value in item.source_contour_ids),
            *(f"evidence:{value}" for value in item.source_evidence_ids),
            *(f"dimension:{value}" for value in item.source_dimension_ids),
            *(f"view:{value}" for value in item.source_view_ids),
        }
        public_source_backed = bool(component_source_refs) and component_source_refs <= ledger_refs
        dimensions = (("length", item.length), ("width", item.width), ("thickness", item.thickness))
        if any(
            value.value_mm is None
            or (
                value.state not in _RELIABLE_STATES
                and not (
                    value.state == "hypothesis"
                    and bool(value.dependency_refs or value.evidence_ids or value.dimension_ids)
                    and public_source_backed
                )
            )
            for name, value in dimensions
        ):
            raise ValueError("assembly_reviewed_dimensions_required")
        quantity_reliable = item.quantity.state in _RELIABLE_STATES or (
            item.quantity.state == "hypothesis"
            and bool(item.quantity.dependency_refs or item.quantity.evidence_ids)
            and public_source_backed
        )
        expected = item.quantity.value if quantity_reliable else None
        component_occurrences = tuple(
            occurrences.get(item.id) or provisional_occurrences.get(item.id, ())
        )
        if expected is None or len(component_occurrences) != expected:
            raise ValueError("assembly_confirmed_quantity_required")
        components.append(
            GeneralAssemblyContextComponent(
                id=item.id,
                length_mm=float(item.length.value_mm), width_mm=float(item.width.value_mm),
                thickness_mm=float(item.thickness.value_mm), occurrence_ids=component_occurrences,
            )
        )
    return GeneralAssemblyContext(
        drawing_id=extraction.drawing_id, run_id=review.run_id,
        proposal_revision=review.proposal_revision, review_revision=review.review_revision,
        regions=tuple(regions), contours=tuple(context_contours), components=tuple(components),
        warnings=tuple(sorted({"non_rectangular_contour" for item in context_contours if item.box_fit_residual_mm > _BOX_FIT_TOLERANCE_MM})),
    )


def _issue(code: str, message: str, occurrence_ids: tuple[str, ...] = (), source_refs: tuple[str, ...] = (), *, severity: str = "error") -> GeneralAssemblyValidationIssue:
    return GeneralAssemblyValidationIssue(code=code, severity=severity, message=message, occurrence_ids=occurrence_ids, source_refs=source_refs)  # type: ignore[arg-type]


def _axis(value: str) -> tuple[str, int]:
    return value[1], 1 if value[0] == "+" else -1


def _project_interval(bounds: Bounds2D, region: Bounds2D, frame: GeneralAssemblyFrame, *, horizontal: bool) -> tuple[str, tuple[float, float]]:
    if horizontal:
        low, high = bounds.min_x, bounds.max_x
        reverse_corner = frame.origin_corner in ("lower_right", "upper_right")
        origin = region.max_x if reverse_corner else region.min_x
        local = (origin - high, origin - low) if reverse_corner else (low - origin, high - origin)
        signed = frame.horizontal_axis
    else:
        low, high = bounds.min_y, bounds.max_y
        reverse_corner = frame.origin_corner in ("upper_left", "upper_right")
        origin = region.max_y if reverse_corner else region.min_y
        local = (origin - high, origin - low) if reverse_corner else (low - origin, high - origin)
        signed = frame.vertical_axis
    axis, sign = _axis(signed)
    return axis, local if sign > 0 else (-local[1], -local[0])


def _world_dimensions(component: GeneralAssemblyContextComponent, orientation: object) -> dict[str, float]:
    result: dict[str, float] = {}
    for name, value in (("length_axis", component.length_mm), ("width_axis", component.width_mm), ("thickness_axis", component.thickness_mm)):
        result[getattr(orientation, name)[1]] = value
    return result


def validate_assembly(
    extraction: DrawingExtraction,
    review: GeneralFurnitureReview,
    candidate: GeneralAssemblyCandidate,
) -> GeneralAssemblyValidationReport:
    try:
        context = build_assembly_context(extraction, review)
    except ValueError as error:
        return GeneralAssemblyValidationReport(status="incomplete", issues=(_issue(str(error), str(error)),), placements=())
    issues: list[GeneralAssemblyValidationIssue] = []
    if (candidate.run_id, candidate.proposal_revision, candidate.review_revision) != (review.run_id, review.proposal_revision, review.review_revision):
        issues.append(_issue("stale_revision", "Candidate does not target the reviewed BOM revision."))
    regions = {item.id: item for item in context.regions}
    contours = {item.id: item for item in context.contours}
    components = {item.id: item for item in context.components}
    frames = {item.id: item for item in candidate.frames}
    occurrence_index = {
        item.id: item
        for item in (*review.occurrences, *review.scenario_occurrences)
    }
    expected_ids = {
        occurrence_id
        for component in context.components
        for occurrence_id in component.occurrence_ids
    }
    actual_ids = {item.occurrence_id for item in candidate.placements}
    for missing in sorted(expected_ids - actual_ids):
        issues.append(_issue("missing_occurrence", "Reviewed occurrence has no placement hypothesis.", (missing,)))
    for extra in sorted(actual_ids - expected_ids):
        issues.append(_issue("unknown_occurrence", "Placement targets an unknown occurrence.", (extra,)))
    used_contours: dict[str, tuple[str, str | None]] = {}
    used_entities: dict[str, tuple[str, str | None]] = {}
    placements: list[GeneralAssemblyPlacement] = []
    for hypothesis in candidate.placements:
        occurrence = occurrence_index.get(hypothesis.occurrence_id)
        component = components.get(hypothesis.component_id)
        if occurrence is None or component is None or occurrence.component_id != hypothesis.component_id or occurrence.occurrence_index != hypothesis.occurrence_index:
            issues.append(_issue("occurrence_identity_mismatch", "Occurrence id, index and component must match the review.", (hypothesis.occurrence_id,)))
            continue
        intervals: dict[str, list[tuple[float, float]]] = defaultdict(list)
        source_refs: set[str] = set()
        for projection in hypothesis.projections:
            frame = frames.get(projection.frame_id)
            contour = contours.get(projection.contour_id)
            if frame is None:
                issues.append(_issue("unknown_frame", "Projection references an unknown frame.", (hypothesis.occurrence_id,), (projection.frame_id,)))
                continue
            if contour is None:
                issues.append(_issue("unknown_contour", "Projection references an unknown contour.", (hypothesis.occurrence_id,), (projection.contour_id,)))
            unknown_evidence = set(projection.evidence_ids) - {item.id for item in extraction.evidence}
            if unknown_evidence:
                issues.append(_issue("unknown_evidence", "Projection references unknown evidence.", (hypothesis.occurrence_id,), tuple(sorted(unknown_evidence))))
            if contour is None:
                continue
            if frame.region_id != contour.region_id or frame.view_id != contour.view_id or frame.region_id not in regions:
                issues.append(_issue("frame_contour_mismatch", "Frame and contour must belong to the same region and view.", (hypothesis.occurrence_id,), (frame.id, contour.id)))
                continue
            if not set(projection.evidence_ids) <= set(contour.evidence_ids):
                issues.append(_issue("evidence_contour_mismatch", "Evidence does not prove the occurrence-specific contour.", (hypothesis.occurrence_id,), projection.evidence_ids))
            previous = used_contours.get(contour.id)
            contour_shared_between_occurrences = previous is not None and previous[0] != hypothesis.occurrence_id
            if previous is not None and not (projection.occlusion_ambiguity_id and projection.occlusion_ambiguity_id == previous[1]):
                issues.append(_issue("shared_contour_identity", "A contour cannot identify two physical occurrences without explicit shared occlusion ambiguity.", (previous[0], hypothesis.occurrence_id), (contour.id,)))
            else:
                used_contours[contour.id] = (hypothesis.occurrence_id, projection.occlusion_ambiguity_id)
            for entity_id in () if contour_shared_between_occurrences else contour.source_entity_ids:
                previous_entity = used_entities.get(entity_id)
                shared_ambiguity = (
                    previous_entity is not None
                    and projection.occlusion_ambiguity_id is not None
                    and projection.occlusion_ambiguity_id == previous_entity[1]
                )
                if previous_entity is not None and previous_entity[0] != hypothesis.occurrence_id and not shared_ambiguity:
                    issues.append(_issue("shared_evidence_identity", "Source geometry cannot identify two physical occurrences without explicit shared occlusion ambiguity.", (previous_entity[0], hypothesis.occurrence_id), (entity_id,)))
                else:
                    used_entities[entity_id] = (hypothesis.occurrence_id, projection.occlusion_ambiguity_id)
            if contour.box_fit_residual_mm > _BOX_FIT_TOLERANCE_MM:
                issues.append(_issue("contour_box_fit_residual", "Non-rectangular contour cannot be treated as an exact panel box.", (hypothesis.occurrence_id,), (contour.id,)))
            region = regions[frame.region_id]
            for horizontal in (True, False):
                axis, interval = _project_interval(contour.bounds_mm, region.bounds_mm, frame, horizontal=horizontal)
                intervals[axis].append(interval)
            source_refs.update((f"frame:{frame.id}", f"contour:{contour.id}", *(f"evidence:{value}" for value in projection.evidence_ids)))
        if set(intervals) != {"x", "y", "z"}:
            issues.append(_issue("incomplete_axis_coverage", "Two or more projections must cover x, y and z.", (hypothesis.occurrence_id,)))
            continue
        resolved: dict[str, tuple[float, float]] = {}
        for axis, values in intervals.items():
            starts, ends = [value[0] for value in values], [value[1] for value in values]
            if max(starts) - min(starts) > _REPROJECTION_TOLERANCE_MM or max(ends) - min(ends) > _REPROJECTION_TOLERANCE_MM:
                issues.append(_issue("reprojection_mismatch", f"Projected {axis} intervals disagree across views.", (hypothesis.occurrence_id,)))
            resolved[axis] = (sum(starts) / len(starts), sum(ends) / len(ends))
        expected_dimensions = _world_dimensions(component, hypothesis.orientation)
        for axis in ("x", "y", "z"):
            actual = resolved[axis][1] - resolved[axis][0]
            if abs(actual - expected_dimensions[axis]) > _DIMENSION_TOLERANCE_MM:
                issues.append(_issue("dimension_mismatch", f"Projected {axis} extent does not match reviewed BOM under orientation.", (hypothesis.occurrence_id,)))
        placements.append(GeneralAssemblyPlacement(occurrence_id=hypothesis.occurrence_id, occurrence_index=hypothesis.occurrence_index, component_id=hypothesis.component_id, position_mm=Point3D(x=resolved["x"][0], y=resolved["y"][0], z=resolved["z"][0]), size_mm=Size3D(x=resolved["x"][1] - resolved["x"][0], y=resolved["y"][1] - resolved["y"][0], z=resolved["z"][1] - resolved["z"][0]), orientation=hypothesis.orientation, source_refs=tuple(sorted(source_refs))))
    max_penetration = 0.0
    penetration_hypotheses = {frozenset(item.occurrence_ids): item for item in candidate.penetration_hypotheses}
    used_penetration_hypotheses: set[frozenset[str]] = set()
    for index, left in enumerate(placements):
        for right in placements[index + 1:]:
            overlaps = tuple(min(getattr(left.position_mm, axis) + getattr(left.size_mm, axis), getattr(right.position_mm, axis) + getattr(right.size_mm, axis)) - max(getattr(left.position_mm, axis), getattr(right.position_mm, axis)) for axis in ("x", "y", "z"))
            if all(value > _NUMERICAL_EPSILON_MM for value in overlaps):
                penetration = min(overlaps)
                max_penetration = max(max_penetration, penetration)
                if penetration > _PENETRATION_TOLERANCE_MM:
                    pair = frozenset((left.occurrence_id, right.occurrence_id))
                    explanation = penetration_hypotheses.get(pair)
                    if explanation is None:
                        issues.append(_issue("aabb_penetration", "World AABBs penetrate beyond collision tolerance without a projected joinery hypothesis.", (left.occurrence_id, right.occurrence_id)))
                    else:
                        explanation_refs = set(explanation.source_refs)
                        left_refs, right_refs = set(left.source_refs), set(right.source_refs)
                        if not explanation_refs <= left_refs | right_refs or not explanation_refs & left_refs or not explanation_refs & right_refs:
                            issues.append(_issue("penetration_evidence_mismatch", "Penetration hypothesis must cite observed projection evidence from both occurrences.", (left.occurrence_id, right.occurrence_id), explanation.source_refs))
                        else:
                            used_penetration_hypotheses.add(pair)
                            issues.append(_issue("aabb_penetration_unresolved", "Projected overlap is observed, but no machining feature proves that the coarse AABB penetration is physically resolved.", (left.occurrence_id, right.occurrence_id), explanation.source_refs))
    for pair, explanation in penetration_hypotheses.items():
        if pair not in used_penetration_hypotheses:
            issues.append(_issue("unused_penetration_hypothesis", "Penetration hypothesis does not explain a measured AABB overlap.", explanation.occurrence_ids, explanation.source_refs))
    has_errors = any(item.severity == "error" for item in issues)
    bounds = None
    scene = None
    if placements:
        bounds = Bounds3D(min=Point3D(x=min(item.position_mm.x for item in placements), y=min(item.position_mm.y for item in placements), z=min(item.position_mm.z for item in placements)), max=Point3D(x=max(item.position_mm.x + item.size_mm.x for item in placements), y=max(item.position_mm.y + item.size_mm.y for item in placements), z=max(item.position_mm.z + item.size_mm.z for item in placements)))
    if not has_errors and len(placements) == len(expected_ids):
        reviewed = {item.id: item for item in review.components}
        confirmed_ids = {item.id for item in review.occurrences}
        scene = GeneralScene(status="mounted_hypothesis", items=tuple(GeneralSceneItem(id=f"scene:{item.occurrence_id}", component_id=item.component_id, occurrence_ids=(item.occurrence_id,) if item.occurrence_id in confirmed_ids else (), scenario_occurrence_ids=() if item.occurrence_id in confirmed_ids else (item.occurrence_id,), occurrence_status="confirmed" if item.occurrence_id in confirmed_ids else "provisional", length=reviewed[item.component_id].length, width=reviewed[item.component_id].width, thickness=reviewed[item.component_id].thickness, position_mm=item.position_mm, size_mm=item.size_mm, occurrence_id=item.occurrence_id, occurrence_index=item.occurrence_index, orientation=item.orientation, status="placed_hypothesis") for item in placements), warnings=("Hipótesis geométrica validada; no constituye aprobación de fabricación.",))
    return GeneralAssemblyValidationReport(status="rejected" if has_errors else "accepted", issues=tuple(issues), placements=tuple(placements), scene=scene, global_bounds_mm=bounds, max_penetration_mm=max_penetration)


__all__ = ["build_assembly_context", "validate_assembly"]
