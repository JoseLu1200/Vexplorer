from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from itertools import permutations

from backend.app.contratos.modelos import (
    AssemblyCandidate, AssemblyConstraint, AssemblyPartUse, Bounds2D,
    DerivedAssemblyDimension, DrawingContour, DrawingExtraction,
    ObservedPartDimension, ObservedQuantity, PartDimensions, PartViewReference,
    Point2D, ResolvedPiece, SeparatedPartObservation, SeparatedPartsExtraction,
)


PART_LABEL = re.compile(
    r"^PART\s+(?P<key>[A-Za-z0-9_-]+)\s+(?P<role>FRONT|TOP|SIDE)(?:\s+QTY\s+(?P<quantity>[1-9]\d*))?$",
    re.IGNORECASE,
)
QUANTITY_LABEL = re.compile(
    r"^QTY\s+(?P<key>[A-Za-z0-9_-]+)\s+(?P<quantity>[1-9]\d*)$", re.IGNORECASE,
)
LOOSE_QUANTITY_LABEL = re.compile(r"^QTY\s+[1-9]\d*$", re.IGNORECASE)
AXES_BY_ROLE = {
    "FRONT": (("length", "x"), ("width", "y")),
    "TOP": (("length", "x"), ("thickness", "y")),
    "SIDE": (("thickness", "x"), ("width", "y")),
}
DIMENSION_TOLERANCE_MM = 0.1


def _bounds(contours: tuple[DrawingContour, ...], *, metric: bool) -> Bounds2D | None:
    points = [point for contour in contours for point in ((contour.points_mm if metric else contour.points_source) or ())]
    if not points:
        return None
    return Bounds2D(
        min_x=min(point.x for point in points), min_y=min(point.y for point in points),
        max_x=max(point.x for point in points), max_y=max(point.y for point in points),
    )


def _local_bounds(bounds: Bounds2D) -> Bounds2D:
    return Bounds2D(min_x=0, min_y=0, max_x=bounds.max_x - bounds.min_x, max_y=bounds.max_y - bounds.min_y)


def _resolve_dimension(candidates: list[tuple[float, str, tuple[str, ...], tuple[str, ...]]]) -> ObservedPartDimension:
    if not candidates:
        return ObservedPartDimension(value_mm=None, state="unknown")
    ordered = sorted(candidates, key=lambda item: item[1])
    view_ids = tuple(item[1] for item in ordered)
    evidence_ids = tuple(sorted({evidence_id for item in ordered for evidence_id in item[2]}))
    measurement_ids = tuple(sorted({measurement_id for item in ordered for measurement_id in item[3]}))
    values = [item[0] for item in ordered]
    if max(values) - min(values) > DIMENSION_TOLERANCE_MM:
        if measurement_ids:
            return ObservedPartDimension(
                value_mm=None, state="conflict", measurement_ids=measurement_ids,
                view_ids=view_ids, evidence_ids=evidence_ids,
            )
        return ObservedPartDimension(value_mm=None, state="unknown")
    return ObservedPartDimension(
        value_mm=values[0], state="observed", measurement_ids=measurement_ids,
        view_ids=view_ids, evidence_ids=evidence_ids,
    )


def _candidate_revision(observations: tuple[SeparatedPartObservation, ...]) -> str:
    payload = [{
        "key": item.part_key,
        "association": item.association_basis,
        "views": [view.role for view in item.views],
        "dimensions": {name: {"value_mm": dimension.value_mm, "state": dimension.state} for name, dimension in item.dimensions},
        "quantity": {"value": item.quantity.value, "state": item.quantity.state},
        "status": item.status,
    } for item in observations]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"parts-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def extract_separated_parts(extraction: DrawingExtraction) -> SeparatedPartsExtraction:
    if extraction.input_kind != "separated_part_views":
        raise ValueError("separated_part_views input_kind required")

    labels_by_key: dict[str, dict[str, str]] = defaultdict(dict)
    duplicate_part_views: set[tuple[str, str]] = set()
    quantities_by_key: dict[str, list[tuple[int, str]]] = defaultdict(list)
    text_evidence = {item.source_entity_id: f"evidence-text-{item.source_entity_id}" for item in extraction.texts}
    for text in extraction.texts:
        part_match = PART_LABEL.fullmatch(text.text.strip())
        if part_match:
            key = part_match.group("key")
            role = part_match.group("role").upper()
            if role in labels_by_key[key]:
                duplicate_part_views.add((key, role))
            labels_by_key[key][role] = text.view_id
            if part_match.group("quantity"):
                quantities_by_key[key].append((int(part_match.group("quantity")), text_evidence[text.source_entity_id]))
            continue
        quantity_match = QUANTITY_LABEL.fullmatch(text.text.strip())
        if quantity_match:
            quantities_by_key[quantity_match.group("key")].append(
                (int(quantity_match.group("quantity")), text_evidence[text.source_entity_id])
            )

    contours_by_view = {
        view.id: tuple(sorted((contour for contour in extraction.contours if contour.view_id == view.id), key=lambda item: item.id))
        for view in extraction.views
    }
    evidence_by_entity: dict[str, set[str]] = defaultdict(set)
    for evidence in extraction.evidence:
        for entity_id in evidence.source_entity_ids:
            evidence_by_entity[entity_id].add(evidence.id)
    graphics_by_id = {item.id: item for item in extraction.dimension_graphics}
    dimensions_by_view: dict[str, list[tuple[str, object]]] = defaultdict(list)
    for dimension in extraction.dimensions:
        graphic = graphics_by_id.get(dimension.graphic_id or "")
        if dimension.view_id is not None and graphic is not None:
            dx = abs(graphic.extension_start_b_source.x - graphic.extension_start_a_source.x)
            dy = abs(graphic.extension_start_b_source.y - graphic.extension_start_a_source.y)
            dimensions_by_view[dimension.view_id].append(("x" if dx >= dy else "y", dimension))

    observations: list[SeparatedPartObservation] = []
    extraction_warnings: list[str] = []
    for key in sorted(labels_by_key, key=str.casefold):
        view_refs: list[PartViewReference] = []
        dimension_candidates: dict[str, list[tuple[float, str, tuple[str, ...], tuple[str, ...]]]] = defaultdict(list)
        dimension_conflicts: dict[str, tuple[set[str], set[str], set[str]]] = {}
        source_entity_ids: set[str] = set()
        observation_evidence: set[str] = set()
        warnings: list[str] = []
        duplicate_roles = sorted(role for duplicate_key, role in duplicate_part_views if duplicate_key == key)
        warnings.extend(f"duplicate_part_view:{key}:{role}" for role in duplicate_roles)
        for role, view_id in sorted(labels_by_key[key].items()):
            contours = contours_by_view.get(view_id, ())
            if not contours:
                warnings.append(f"view_geometry_missing:{key}:{role}")
                continue
            source_bounds = _bounds(contours, metric=False)
            metric_bounds = _bounds(contours, metric=True)
            if source_bounds is None:
                continue
            contour_ids = tuple(item.id for item in contours)
            contour_entity_ids = {entity_id for item in contours for entity_id in item.source_entity_ids}
            evidence_ids = tuple(sorted({evidence_id for entity_id in contour_entity_ids for evidence_id in evidence_by_entity[entity_id]}))
            source_entity_ids.update(contour_entity_ids)
            observation_evidence.update(evidence_ids)
            view_refs.append(PartViewReference(
                view_id=view_id, role=role, contour_ids=contour_ids,
                local_origin_source=Point2D(x=source_bounds.min_x, y=source_bounds.min_y),
                local_origin_mm=Point2D(x=metric_bounds.min_x, y=metric_bounds.min_y) if metric_bounds else None,
                local_bounds_source=_local_bounds(source_bounds),
                local_bounds_mm=_local_bounds(metric_bounds) if metric_bounds else None,
            ))
            if metric_bounds:
                extents = {"x": metric_bounds.max_x - metric_bounds.min_x, "y": metric_bounds.max_y - metric_bounds.min_y}
                for axis, coordinate in AXES_BY_ROLE[role]:
                    annotations = [item for annotation_axis, item in dimensions_by_view.get(view_id, ()) if annotation_axis == coordinate]
                    annotation_evidence = tuple(sorted({
                        evidence_id for item in annotations for evidence_id in item.evidence_ids
                    }))
                    dimension_candidates[axis].append((
                        extents[coordinate], view_id,
                        tuple(sorted(set(evidence_ids) | set(annotation_evidence))),
                        tuple(sorted(item.id for item in annotations)),
                    ))
                    if annotations and any(
                        item.value_mm is None or abs(item.value_mm - extents[coordinate]) > DIMENSION_TOLERANCE_MM
                        for item in annotations
                    ):
                        views, measurements, conflict_evidence = dimension_conflicts.setdefault(axis, (set(), set(), set()))
                        views.add(view_id)
                        measurements.update(item.id for item in annotations)
                        conflict_evidence.update(evidence_ids)
                        conflict_evidence.update(evidence_id for item in annotations for evidence_id in item.evidence_ids)

        quantities = quantities_by_key.get(key, [])
        if not quantities:
            quantity = ObservedQuantity(value=None, state="unknown")
        elif len({item[0] for item in quantities}) == 1:
            quantity = ObservedQuantity(value=quantities[0][0], state="observed", evidence_ids=tuple(sorted({item[1] for item in quantities})))
        else:
            quantity = ObservedQuantity(value=None, state="ambiguous", evidence_ids=tuple(sorted({item[1] for item in quantities})))
            warnings.append(f"quantity_conflict:{key}")
        observation_evidence.update(quantity.evidence_ids)
        dimensions = PartDimensions(
            length=_resolve_dimension(dimension_candidates["length"]),
            width=_resolve_dimension(dimension_candidates["width"]),
            thickness=_resolve_dimension(dimension_candidates["thickness"]),
        )
        dimension_values = dict(dimensions)
        for axis, (views, measurements, conflict_evidence) in dimension_conflicts.items():
            dimension_values[axis] = ObservedPartDimension(
                value_mm=None, state="conflict", measurement_ids=tuple(sorted(measurements)),
                view_ids=tuple(sorted(views)), evidence_ids=tuple(sorted(conflict_evidence)),
            )
            warnings.append(f"dimension_annotation_conflict:{key}:{axis}")
        dimensions = PartDimensions(**dimension_values)
        for name, dimension in dimensions:
            if dimension.state == "conflict":
                warnings.append(f"dimension_conflict:{key}:{name}")
        complete = quantity.state == "observed" and all(dimension.state == "observed" for _, dimension in dimensions)
        ambiguous = bool(duplicate_roles) or quantity.state == "ambiguous" or any(dimension.state == "conflict" for _, dimension in dimensions)
        observations.append(SeparatedPartObservation(
            id=f"part-observation-{key.lower()}", part_key=key,
            association_basis="ambiguous" if ambiguous else "explicit_key",
            views=tuple(sorted(view_refs, key=lambda item: item.role)), dimensions=dimensions,
            quantity=quantity, status="ambiguous" if ambiguous else "complete" if complete else "partial",
            source_entity_ids=tuple(sorted(source_entity_ids)), evidence_ids=tuple(sorted(observation_evidence)),
            warnings=tuple(warnings),
        ))
        extraction_warnings.extend(warnings)

    if any(contour.view_id.startswith("view-unassociated-") for contour in extraction.contours):
        views_by_id = {view.id: view for view in extraction.views}
        labels_by_view = {
            text.view_id: text for text in extraction.texts if text.text.strip().upper() in AXES_BY_ROLE
        }
        unassociated_contours = tuple(sorted(
            (contour for contour in extraction.contours if contour.view_id.startswith("view-unassociated-")),
            key=lambda item: item.id,
        ))
        for index, contour in enumerate(unassociated_contours, start=1):
            source_bounds = _bounds((contour,), metric=False)
            metric_bounds = _bounds((contour,), metric=True)
            if source_bounds is None:
                continue
            view = views_by_id.get(contour.view_id)
            label = labels_by_view.get(contour.view_id)
            if view is None or label is None:
                continue
            role = view.label
            view_id = view.id
            contour_evidence = tuple(sorted({
                evidence_id for entity_id in contour.source_entity_ids for evidence_id in evidence_by_entity[entity_id]
            }))
            label_evidence = text_evidence[label.source_entity_id]
            evidence_ids = tuple(sorted(set(contour_evidence) | {label_evidence}))
            dimensions_by_name: dict[str, ObservedPartDimension] = {
                "length": ObservedPartDimension(value_mm=None, state="unknown"),
                "width": ObservedPartDimension(value_mm=None, state="unknown"),
                "thickness": ObservedPartDimension(value_mm=None, state="unknown"),
            }
            if metric_bounds:
                extents = {"x": metric_bounds.max_x - metric_bounds.min_x, "y": metric_bounds.max_y - metric_bounds.min_y}
                for axis, coordinate in AXES_BY_ROLE[role]:
                    dimensions_by_name[axis] = ObservedPartDimension(
                        value_mm=extents[coordinate], state="observed",
                        view_ids=(view_id,), evidence_ids=contour_evidence,
                    )
            warning = f"missing_part_key:{view_id}"
            observations.append(SeparatedPartObservation(
                id=f"part-observation-unassociated-{index}", part_key=None,
                association_basis="unassociated",
                views=(PartViewReference(
                    view_id=view_id, role=role, contour_ids=(contour.id,),
                    local_origin_source=Point2D(x=source_bounds.min_x, y=source_bounds.min_y),
                    local_origin_mm=Point2D(x=metric_bounds.min_x, y=metric_bounds.min_y) if metric_bounds else None,
                    local_bounds_source=_local_bounds(source_bounds),
                    local_bounds_mm=_local_bounds(metric_bounds) if metric_bounds else None,
                ),),
                dimensions=PartDimensions(**dimensions_by_name),
                quantity=ObservedQuantity(value=None, state="unknown"), status="ambiguous",
                source_entity_ids=tuple(sorted(set(contour.source_entity_ids) | {label.source_entity_id})),
                evidence_ids=evidence_ids, warnings=(warning,),
            ))
            extraction_warnings.append(warning)
        for text in extraction.texts:
            if LOOSE_QUANTITY_LABEL.fullmatch(text.text.strip()):
                extraction_warnings.append(f"unassociated_quantity_annotation:{text.id}")

    result = tuple(sorted(observations, key=lambda item: item.id))
    return SeparatedPartsExtraction(
        drawing_id=extraction.drawing_id, candidate_revision=_candidate_revision(result),
        observations=result, warnings=tuple(extraction_warnings),
    )


def derive_assembly_candidates(parts: SeparatedPartsExtraction) -> tuple[AssemblyCandidate, ...]:
    observations = tuple(sorted(parts.observations, key=lambda item: item.id))
    if len(observations) != 3 or any(item.association_basis != "explicit_key" for item in observations):
        return ()

    def use(
        observation: SeparatedPartObservation,
        role: str,
        occurrence_indices: tuple[int, ...] | None,
    ) -> AssemblyPartUse:
        source_quantity = observation.quantity.value
        if observation.quantity.state != "observed" or source_quantity is None or occurrence_indices is None:
            return AssemblyPartUse(
                id=f"use-{observation.id}-{role}", part_observation_id=observation.id,
                role=role, source_quantity=None, allocated_quantity=None, occurrence_indices=(),
                quantity_source="unknown", evidence_ids=observation.quantity.evidence_ids,
            )
        return AssemblyPartUse(
            id=f"use-{observation.id}-{role}", part_observation_id=observation.id,
            role=role, source_quantity=source_quantity, allocated_quantity=len(occurrence_indices),
            occurrence_indices=occurrence_indices, quantity_source="observed_annotation",
            evidence_ids=observation.quantity.evidence_ids,
        )

    def constraint(
        candidate_id: str,
        name: str,
        kind: str,
        operation: str,
        dimension: str,
        operands: tuple[tuple[str, ObservedPartDimension], ...],
        result: float | None,
    ) -> AssemblyConstraint:
        refs = tuple(ref for ref, _ in operands)
        evidence = tuple(sorted({evidence_id for _, value in operands for evidence_id in value.evidence_ids}))
        states = {value.state for _, value in operands}
        status = "pass" if result is not None and states == {"observed"} else "conflict" if "conflict" in states else "unknown"
        return AssemblyConstraint(
            id=f"constraint-{candidate_id}-{name}", kind=kind, operation=operation,
            dimension=dimension, operand_refs=refs, result_mm=result if status == "pass" else None,
            status=status, evidence_ids=evidence,
        )

    candidates = []
    for side, horizontal, shelf in permutations(observations):
        for layout in ("between_sides", "cap_sides"):
            candidate_id = f"assembly-{layout}-{side.id}-{horizontal.id}-{shelf.id}"
            if horizontal.quantity.state == "observed" and horizontal.quantity.value == 2:
                uses = (
                    use(side, "side_panel", tuple(range(1, (side.quantity.value or 0) + 1)) if side.quantity.state == "observed" else None),
                    use(horizontal, "top_panel", (1,)), use(horizontal, "base_panel", (2,)),
                    use(shelf, "shelf", tuple(range(1, (shelf.quantity.value or 0) + 1)) if shelf.quantity.state == "observed" else None),
                )
            else:
                uses = (
                    use(side, "side_panel", tuple(range(1, (side.quantity.value or 0) + 1)) if side.quantity.state == "observed" else None),
                    use(horizontal, "unknown", None),
                    use(shelf, "shelf", tuple(range(1, (shelf.quantity.value or 0) + 1)) if shelf.quantity.state == "observed" else None),
                )

            depth_values = [item.dimensions.width.value_mm for item in (side, horizontal, shelf)]
            thickness_values = [item.dimensions.thickness.value_mm for item in (side, horizontal, shelf)]
            horizontal_length = horizontal.dimensions.length.value_mm
            shelf_length = shelf.dimensions.length.value_mm
            common_depth = depth_values[0] if all(value is not None and abs(value - depth_values[0]) <= DIMENSION_TOLERANCE_MM for value in depth_values) else None
            common_thickness = thickness_values[0] if all(value is not None and abs(value - thickness_values[0]) <= DIMENSION_TOLERANCE_MM for value in thickness_values) else None
            if all(value is not None for value in depth_values) and common_depth is None:
                continue
            if all(value is not None for value in thickness_values) and common_thickness is None:
                continue
            if side.quantity.state == "observed" and side.quantity.value != 2:
                continue
            if horizontal.quantity.state == "observed" and horizontal.quantity.value != 2:
                continue
            expected_shelf_length = (
                horizontal_length if layout == "between_sides"
                else horizontal_length - 2 * common_thickness
                if horizontal_length is not None and common_thickness is not None else None
            )
            if shelf_length is not None and expected_shelf_length is not None and abs(shelf_length - expected_shelf_length) > DIMENSION_TOLERANCE_MM:
                continue
            compatible_horizontal = horizontal_length if shelf_length is not None and expected_shelf_length is not None else None
            side_length = side.dimensions.length.value_mm
            exterior_width = (
                horizontal_length + 2 * common_thickness
                if layout == "between_sides" and horizontal_length is not None and common_thickness is not None
                else horizontal_length if layout == "cap_sides" else None
            )
            exterior_height = (
                side_length if layout == "between_sides"
                else side_length + 2 * common_thickness
                if side_length is not None and common_thickness is not None else None
            )
            horizontal_constraint_operands = (
                (f"{horizontal.id}.dimensions.length", horizontal.dimensions.length),
                (f"{shelf.id}.dimensions.length", shelf.dimensions.length),
            ) if layout == "between_sides" else (
                (f"{horizontal.id}.dimensions.length", horizontal.dimensions.length),
                (f"{horizontal.id}.dimensions.thickness", horizontal.dimensions.thickness),
                (f"{horizontal.id}.dimensions.thickness", horizontal.dimensions.thickness),
                (f"{shelf.id}.dimensions.length", shelf.dimensions.length),
            )
            width_operands = (
                (f"{horizontal.id}.dimensions.length", horizontal.dimensions.length),
                (f"{side.id}.dimensions.thickness", side.dimensions.thickness),
                (f"{side.id}.dimensions.thickness", side.dimensions.thickness),
            ) if layout == "between_sides" else (
                (f"{horizontal.id}.dimensions.length", horizontal.dimensions.length),
            )
            height_operands = (
                (f"{side.id}.dimensions.length", side.dimensions.length),
            ) if layout == "between_sides" else (
                (f"{side.id}.dimensions.length", side.dimensions.length),
                (f"{horizontal.id}.dimensions.thickness", horizontal.dimensions.thickness),
                (f"{horizontal.id}.dimensions.thickness", horizontal.dimensions.thickness),
            )
            constraints = (
                constraint(candidate_id, "depth", "equal_dimensions", "equal", "width", tuple(
                    (f"{item.id}.dimensions.width", item.dimensions.width) for item in (side, horizontal, shelf)
                ), common_depth),
                constraint(candidate_id, "thickness", "equal_dimensions", "equal", "thickness", tuple(
                    (f"{item.id}.dimensions.thickness", item.dimensions.thickness) for item in (side, horizontal, shelf)
                ), common_thickness),
                constraint(candidate_id, "horizontal", "role_compatibility", "equal" if layout == "between_sides" else "difference", "length", horizontal_constraint_operands, compatible_horizontal),
                constraint(candidate_id, "assembled-width", "exterior_from_parts", "sum" if layout == "between_sides" else "equal", "assembled_width", width_operands, exterior_width),
                constraint(candidate_id, "assembled-height", "exterior_from_parts", "equal" if layout == "between_sides" else "sum", "assembled_height", height_operands, exterior_height),
            )
            width_constraint = next(item for item in constraints if item.dimension == "assembled_width")
            height_constraint = next(item for item in constraints if item.dimension == "assembled_height")
            depth_constraint = constraints[0]
            derived = (
                DerivedAssemblyDimension(axis="width", value_mm=exterior_width, state="derived", operand_refs=width_constraint.operand_refs, constraint_id=width_constraint.id) if exterior_width is not None else DerivedAssemblyDimension(axis="width", value_mm=None, state="unknown", operand_refs=width_constraint.operand_refs),
                DerivedAssemblyDimension(axis="height", value_mm=exterior_height, state="derived", operand_refs=height_constraint.operand_refs, constraint_id=height_constraint.id) if exterior_height is not None else DerivedAssemblyDimension(axis="height", value_mm=None, state="unknown", operand_refs=height_constraint.operand_refs),
                DerivedAssemblyDimension(axis="depth", value_mm=common_depth, state="derived", operand_refs=depth_constraint.operand_refs, constraint_id=depth_constraint.id) if common_depth is not None else DerivedAssemblyDimension(axis="depth", value_mm=None, state="unknown", operand_refs=depth_constraint.operand_refs),
            )
            unknown_fields = tuple(sorted(
                [f"uses.{item.id}.quantity" for item in uses if item.quantity_source == "unknown"]
                + [f"dimensions.{item.axis}" for item in derived if item.state != "derived"]
                + (["roles.top_panel", "roles.base_panel"] if any(item.role == "unknown" for item in uses) else [])
            ))
            evidence_ids = tuple(sorted({evidence_id for item in observations for evidence_id in item.evidence_ids}))
            candidates.append(AssemblyCandidate(
                id=candidate_id, family="rectangular_shelving", layout=layout, uses=uses,
                constraints=constraints, derived_dimensions=derived, unknown_fields=unknown_fields,
                assumptions=(
                    "Role allocation is a dimensional hypothesis; opaque part keys carry no role semantics.",
                    "Assembly layout is not observed and requires human review.",
                    "No back, hardware, material, or manufacturing detail is inferred.",
                ), evidence_ids=evidence_ids,
            ))
    return tuple(sorted(candidates, key=lambda item: item.id))


def recompute_reviewed_assembly_candidate(
    candidate: AssemblyCandidate,
    parts: SeparatedPartsExtraction,
    pieces: tuple[ResolvedPiece, ...],
    *,
    result_revision: int,
) -> AssemblyCandidate:
    if result_revision < 1:
        raise ValueError("result_revision must be positive")
    observation_ids = {item.id for item in parts.observations}
    if not {item.part_observation_id for item in candidate.uses} <= observation_ids:
        raise ValueError("candidate references an unknown part observation")

    pieces_by_use = {item.proposal_id: item for item in pieces}
    role_pieces: dict[str, list[ResolvedPiece]] = defaultdict(list)
    for use in candidate.uses:
        piece = pieces_by_use.get(use.id)
        if piece is not None:
            role_pieces[piece.role].append(piece)

    def operand(piece: ResolvedPiece | None, field: str) -> tuple[str, float | None, tuple[str, ...]]:
        if piece is None:
            return (f"review:{result_revision}:missing.{field}", None, ())
        return (
            f"review:{result_revision}:piece:{piece.id}.{field}",
            getattr(piece, field),
            piece.evidence_ids,
        )

    def one(role: str) -> ResolvedPiece | None:
        values = role_pieces.get(role, [])
        return values[0] if len(values) == 1 else None

    side, top, base, shelf = one("side_panel"), one("top_panel"), one("base_panel"), one("shelf")

    def constraint_id(dimension: str, kind: str) -> str:
        existing = next(
            (item.id for item in candidate.constraints if item.dimension == dimension and item.kind == kind),
            None,
        )
        return existing or f"constraint-{candidate.id}-reviewed-{dimension}"

    def make_constraint(
        *,
        dimension: str,
        kind: str,
        operation: str,
        operands: tuple[tuple[str, float | None, tuple[str, ...]], ...],
        compatible_result: float | None,
        incompatible: bool = False,
    ) -> AssemblyConstraint:
        refs = tuple(item[0] for item in operands)
        evidence = tuple(sorted({evidence_id for item in operands for evidence_id in item[2]}))
        if incompatible:
            status = "conflict"
            if len(evidence) < 2:
                evidence = tuple(sorted(set(evidence) | set(candidate.evidence_ids)))
        elif compatible_result is None or any(item[1] is None for item in operands):
            status = "unknown"
        else:
            status = "pass"
        return AssemblyConstraint(
            id=constraint_id(dimension, kind), kind=kind, operation=operation,
            dimension=dimension, operand_refs=refs,
            result_mm=compatible_result if status == "pass" else None,
            status=status, evidence_ids=evidence,
        )

    depth_operands = tuple(operand(piece, "width_mm") for piece in (side, top, base, shelf))
    depth_values = [item[1] for item in depth_operands]
    depth_conflict = all(value is not None for value in depth_values) and max(depth_values) - min(depth_values) > DIMENSION_TOLERANCE_MM
    common_depth = depth_values[0] if depth_values and all(value is not None for value in depth_values) and not depth_conflict else None

    thickness_operands = tuple(operand(piece, "thickness_mm") for piece in (side, top, base, shelf))
    thickness_values = [item[1] for item in thickness_operands]
    thickness_conflict = all(value is not None for value in thickness_values) and max(thickness_values) - min(thickness_values) > DIMENSION_TOLERANCE_MM
    common_thickness = thickness_values[0] if thickness_values and all(value is not None for value in thickness_values) and not thickness_conflict else None

    horizontal_operands = tuple(operand(piece, "length_mm") for piece in (top, base, shelf))
    horizontal_values = [item[1] for item in horizontal_operands]
    horizontal_result = None
    horizontal_conflict = False
    if all(value is not None for value in horizontal_values):
        top_length, base_length, shelf_length = horizontal_values
        assert top_length is not None and base_length is not None and shelf_length is not None
        if candidate.layout == "between_sides":
            horizontal_conflict = max(horizontal_values) - min(horizontal_values) > DIMENSION_TOLERANCE_MM
            horizontal_result = top_length if not horizontal_conflict else None
        elif candidate.layout == "cap_sides" and common_thickness is not None:
            expected_shelf = top_length - 2 * common_thickness
            horizontal_conflict = abs(top_length - base_length) > DIMENSION_TOLERANCE_MM or abs(shelf_length - expected_shelf) > DIMENSION_TOLERANCE_MM
            horizontal_result = shelf_length if not horizontal_conflict else None

    if candidate.layout == "between_sides":
        width_operands = (operand(top, "length_mm"), operand(side, "thickness_mm"), operand(side, "thickness_mm"))
        width_value = top.length_mm + 2 * side.thickness_mm if top and side and top.length_mm is not None and side.thickness_mm is not None else None
        height_operands = (operand(side, "length_mm"),)
        height_value = side.length_mm if side else None
        width_operation, height_operation = "sum", "equal"
    elif candidate.layout == "cap_sides":
        width_operands = (operand(top, "length_mm"),)
        width_value = top.length_mm if top else None
        height_operands = (operand(side, "length_mm"), operand(top, "thickness_mm"), operand(top, "thickness_mm"))
        height_value = side.length_mm + 2 * top.thickness_mm if side and top and side.length_mm is not None and top.thickness_mm is not None else None
        width_operation, height_operation = "equal", "sum"
    else:
        width_operands = (operand(top, "length_mm"),)
        height_operands = (operand(side, "length_mm"),)
        width_value = height_value = None
        width_operation = height_operation = "compatibility"

    constraints = (
        make_constraint(dimension="width", kind="equal_dimensions", operation="equal", operands=depth_operands, compatible_result=common_depth, incompatible=depth_conflict),
        make_constraint(dimension="thickness", kind="equal_dimensions", operation="equal", operands=thickness_operands, compatible_result=common_thickness, incompatible=thickness_conflict),
        make_constraint(dimension="length", kind="role_compatibility", operation="equal" if candidate.layout == "between_sides" else "difference", operands=horizontal_operands, compatible_result=horizontal_result, incompatible=horizontal_conflict),
        make_constraint(dimension="assembled_width", kind="exterior_from_parts", operation=width_operation, operands=width_operands, compatible_result=width_value),
        make_constraint(dimension="assembled_height", kind="exterior_from_parts", operation=height_operation, operands=height_operands, compatible_result=height_value),
    )
    width_constraint = next(item for item in constraints if item.dimension == "assembled_width")
    height_constraint = next(item for item in constraints if item.dimension == "assembled_height")
    depth_constraint = constraints[0]

    def derived(axis: str, value: float | None, source: AssemblyConstraint) -> DerivedAssemblyDimension:
        if source.status == "pass" and value is not None:
            return DerivedAssemblyDimension(
                axis=axis, value_mm=value, state="derived",
                operand_refs=source.operand_refs, constraint_id=source.id,
            )
        return DerivedAssemblyDimension(
            axis=axis, value_mm=None,
            state="conflict" if source.status == "conflict" else "unknown",
            operand_refs=source.operand_refs,
        )

    derived_dimensions = (
        derived("width", width_value, width_constraint),
        derived("height", height_value, height_constraint),
        derived("depth", common_depth, depth_constraint),
    )
    unknown_fields = [
        item for item in candidate.unknown_fields
        if not item.startswith("dimensions.")
    ]
    unknown_fields.extend(
        f"dimensions.{item.axis}" for item in derived_dimensions if item.state != "derived"
    )
    used_human_values = any(
        piece.field_states.get(field) == "confirmed"
        for piece in pieces
        for field in ("length_mm", "width_mm", "thickness_mm", "quantity")
    )
    assumptions = candidate.assumptions + (("human_confirmed_operands_used",) if used_human_values and "human_confirmed_operands_used" not in candidate.assumptions else ())
    return candidate.model_copy(update={
        "constraints": constraints,
        "derived_dimensions": derived_dimensions,
        "unknown_fields": tuple(sorted(set(unknown_fields))),
        "assumptions": assumptions,
    })
