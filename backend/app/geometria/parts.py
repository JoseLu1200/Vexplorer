from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from math import hypot

from backend.app.contratos.modelos import (
    Bounds2D, DrawingContour, DrawingExtraction, ObservedPartDimension,
    ObservedQuantity, PartDimensions, PartViewReference, Point2D,
    SeparatedPartObservation, SeparatedPartsExtraction,
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


def _resolve_dimension(candidates: list[tuple[float, str, tuple[str, ...]]]) -> ObservedPartDimension:
    if not candidates:
        return ObservedPartDimension(value_mm=None, state="unknown")
    ordered = sorted(candidates, key=lambda item: item[1])
    view_ids = tuple(item[1] for item in ordered)
    evidence_ids = tuple(sorted({evidence_id for item in ordered for evidence_id in item[2]}))
    values = [item[0] for item in ordered]
    if max(values) - min(values) > DIMENSION_TOLERANCE_MM:
        return ObservedPartDimension(value_mm=None, state="conflict", view_ids=view_ids, evidence_ids=evidence_ids)
    return ObservedPartDimension(value_mm=values[0], state="observed", view_ids=view_ids, evidence_ids=evidence_ids)


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


def _distance_to_bounds(point: Point2D, bounds: Bounds2D) -> float:
    dx = max(bounds.min_x - point.x, 0.0, point.x - bounds.max_x)
    dy = max(bounds.min_y - point.y, 0.0, point.y - bounds.max_y)
    return hypot(dx, dy)


def extract_separated_parts(extraction: DrawingExtraction) -> SeparatedPartsExtraction:
    if extraction.input_kind != "separated_part_views":
        raise ValueError("separated_part_views input_kind required")

    labels_by_key: dict[str, dict[str, str]] = defaultdict(dict)
    quantities_by_key: dict[str, list[tuple[int, str]]] = defaultdict(list)
    text_evidence = {item.source_entity_id: f"evidence-text-{item.source_entity_id}" for item in extraction.texts}
    for text in extraction.texts:
        part_match = PART_LABEL.fullmatch(text.text.strip())
        if part_match:
            key = part_match.group("key")
            labels_by_key[key][part_match.group("role").upper()] = text.view_id
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

    observations: list[SeparatedPartObservation] = []
    extraction_warnings: list[str] = []
    for key in sorted(labels_by_key, key=str.casefold):
        view_refs: list[PartViewReference] = []
        dimension_candidates: dict[str, list[tuple[float, str, tuple[str, ...]]]] = defaultdict(list)
        source_entity_ids: set[str] = set()
        observation_evidence: set[str] = set()
        warnings: list[str] = []
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
                    dimension_candidates[axis].append((extents[coordinate], view_id, evidence_ids))

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
        for name, dimension in dimensions:
            if dimension.state == "conflict":
                warnings.append(f"dimension_conflict:{key}:{name}")
        complete = quantity.state == "observed" and all(dimension.state == "observed" for _, dimension in dimensions)
        ambiguous = quantity.state == "ambiguous" or any(dimension.state == "conflict" for _, dimension in dimensions)
        observations.append(SeparatedPartObservation(
            id=f"part-observation-{key.lower()}", part_key=key,
            association_basis="ambiguous" if ambiguous else "explicit_key",
            views=tuple(sorted(view_refs, key=lambda item: item.role)), dimensions=dimensions,
            quantity=quantity, status="ambiguous" if ambiguous else "complete" if complete else "partial",
            source_entity_ids=tuple(sorted(source_entity_ids)), evidence_ids=tuple(sorted(observation_evidence)),
            warnings=tuple(warnings),
        ))
        extraction_warnings.extend(warnings)

    if not labels_by_key:
        role_labels = [
            (text.text.strip().upper(), text)
            for text in extraction.texts
            if text.text.strip().upper() in AXES_BY_ROLE
        ]
        unused_label_ids = {text.id for _, text in role_labels}
        unknown_contours = tuple(sorted(
            (contour for contour in extraction.contours if contour.view_id == "view-unknown"),
            key=lambda item: item.id,
        ))
        for index, contour in enumerate(unknown_contours, start=1):
            source_bounds = _bounds((contour,), metric=False)
            metric_bounds = _bounds((contour,), metric=True)
            if source_bounds is None:
                continue
            available_labels = [(role, text) for role, text in role_labels if text.id in unused_label_ids]
            if not available_labels:
                continue
            role, label = min(
                available_labels,
                key=lambda item: (_distance_to_bounds(item[1].position_source, source_bounds), item[0], item[1].id),
            )
            unused_label_ids.remove(label.id)
            view_id = f"part-view-{contour.id}"
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
