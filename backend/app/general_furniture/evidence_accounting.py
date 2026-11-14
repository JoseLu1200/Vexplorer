from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Literal

from backend.app.contratos.modelos import (
    DrawingExtraction,
    GeneralFurnitureDraft,
    GeneralFurnitureProposal,
)
from backend.app.general_furniture.projection_hypotheses import ProjectionHypothesis


@dataclass(frozen=True)
class RelevantCandidateRegion:
    id: str
    view_id: str
    contour_ids: tuple[str, ...]
    bounds_source: tuple[float, float, float, float]
    authority: Literal["candidate_evidence_not_physical_piece"] = (
        "candidate_evidence_not_physical_piece"
    )


@dataclass(frozen=True)
class EvidenceAccountingReport:
    candidate_regions: tuple[RelevantCandidateRegion, ...]
    assigned_region_ids: tuple[str, ...]
    nonmaterial_region_ids: tuple[str, ...]
    duplicate_projection_region_ids: tuple[str, ...]
    unresolved_region_ids: tuple[str, ...]
    invalid_region_ids: tuple[str, ...]
    invalid_region_reasons: tuple[tuple[str, str], ...]
    panel_region_ids: tuple[str, ...]
    hardware_region_ids: tuple[str, ...]
    multi_region_component_ids: tuple[str, ...]
    required_existence_review_targets: tuple[str, ...]
    required_disposition_review_targets: tuple[str, ...]
    missing_dimension_targets: tuple[str, ...]
    untraceable_dimension_targets: tuple[str, ...]
    evidence_coverage: float
    reviewable: bool
    claims_physical_piece_recall: Literal[False]
    warnings: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


def derive_relevant_candidate_regions(
    extraction: DrawingExtraction,
) -> tuple[RelevantCandidateRegion, ...]:
    regions = []
    for contour in sorted(extraction.contours, key=lambda item: item.id):
        points = contour.points_source
        if not contour.closed or len(points) < 3:
            continue
        xs = tuple(float(point.x) for point in points)
        ys = tuple(float(point.y) for point in points)
        bounds = (min(xs), min(ys), max(xs), max(ys))
        if bounds[2] - bounds[0] <= 1e-9 or bounds[3] - bounds[1] <= 1e-9:
            continue
        digest = hashlib.sha256(
            f"{contour.view_id}\x00{contour.id}".encode("utf-8")
        ).hexdigest()[:16]
        regions.append(
            RelevantCandidateRegion(
                id=f"evidence-candidate:{digest}",
                view_id=contour.view_id,
                contour_ids=(contour.id,),
                bounds_source=bounds,
            )
        )
    return tuple(regions)


def _projection_supports_duplicate(
    candidate: RelevantCandidateRegion,
    original: RelevantCandidateRegion,
    hypotheses: tuple[ProjectionHypothesis, ...],
) -> bool:
    required = {*candidate.contour_ids, *original.contour_ids}
    return any(required <= set(item.source_contour_ids) for item in hypotheses)


def build_evidence_accounting_report(
    extraction: DrawingExtraction,
    proposal: GeneralFurnitureProposal,
    draft: GeneralFurnitureDraft,
    *,
    projection_hypotheses: tuple[ProjectionHypothesis, ...] = (),
) -> EvidenceAccountingReport:
    regions = derive_relevant_candidate_regions(extraction)
    region_by_id = {item.id: item for item in regions}
    components = {item.id: item for item in proposal.components}
    claims_by_contour: dict[str, list[str]] = {}
    for component in proposal.components:
        for contour_id in component.source_contour_ids:
            claims_by_contour.setdefault(contour_id, []).append(component.id)

    dispositions_by_region: dict[str, list] = {}
    for disposition in proposal.evidence_dispositions:
        dispositions_by_region.setdefault(disposition.candidate_region_id, []).append(
            disposition
        )

    assigned: list[str] = []
    nonmaterial: list[str] = []
    duplicate: list[str] = []
    unresolved: list[str] = []
    invalid: list[str] = []
    invalid_reasons: set[tuple[str, str]] = set()
    panel: list[str] = []
    hardware: list[str] = []
    disposition_targets: list[str] = []
    assigned_by_component: dict[str, list[str]] = {}
    warnings: set[str] = set()

    def invalidate(region_id: str, reason_code: str) -> None:
        invalid.append(region_id)
        invalid_reasons.add((region_id, reason_code))
        warnings.add(reason_code)

    allowed_nonmaterial_reasons = {
        "hole",
        "cutout",
        "rabbet",
        "groove",
        "annotation",
        "drawing_frame",
        "void",
    }
    for region in regions:
        region_dispositions = dispositions_by_region.get(region.id, ())
        claims = sorted(
            {
                component_id
                for contour_id in region.contour_ids
                for component_id in claims_by_contour.get(contour_id, ())
            }
        )
        if len(claims) > 1:
            invalidate(region.id, "candidate_region_reused_by_components")
            continue
        if len(region_dispositions) != 1:
            unresolved.append(region.id)
            warnings.add(
                "candidate_region_disposition_missing"
                if not region_dispositions
                else "candidate_region_disposition_duplicated"
            )
            continue
        disposition = region_dispositions[0]
        exact_sources = {f"contour:{item}" for item in region.contour_ids}
        if not exact_sources <= set(disposition.source_refs):
            invalidate(region.id, "candidate_region_disposition_missing_source")
            continue
        if disposition.kind == "assigned":
            component = components.get(disposition.component_id or "")
            if component is None or claims != [component.id]:
                invalidate(region.id, "assigned_disposition_component_mismatch")
                continue
            assigned.append(region.id)
            assigned_by_component.setdefault(component.id, []).append(region.id)
            (hardware if component.kind == "hardware" else panel).append(region.id)
        elif disposition.kind == "duplicate_projection":
            component = components.get(disposition.component_id or "")
            original = region_by_id.get(disposition.duplicate_of_region_id or "")
            if (
                component is None
                or original is None
                or not set(original.contour_ids) <= set(component.source_contour_ids)
                or not _projection_supports_duplicate(
                    region, original, projection_hypotheses
                )
            ):
                invalidate(
                    region.id, "duplicate_projection_without_supported_identity"
                )
                continue
            duplicate.append(region.id)
            disposition_targets.append(f"evidence_region:{region.id}")
        elif disposition.kind == "nonmaterial":
            if disposition.reason_code not in allowed_nonmaterial_reasons:
                invalidate(
                    region.id, "nonmaterial_disposition_requires_typed_reason"
                )
                continue
            nonmaterial.append(region.id)
            disposition_targets.append(f"evidence_region:{region.id}")
        else:
            unresolved.append(region.id)
            warnings.add("candidate_region_explicitly_unresolved")

    unknown_region_ids = sorted(set(dispositions_by_region) - set(region_by_id))
    if unknown_region_ids:
        for region_id in unknown_region_ids:
            invalidate(region_id, "disposition_references_unknown_candidate_region")

    multi_region_component_ids = tuple(sorted(
        component_id
        for component_id, region_ids in assigned_by_component.items()
        if len(region_ids) > 1
    ))
    if multi_region_component_ids:
        warnings.add(
            "component_claims_multiple_candidate_regions_requires_directed_review"
        )
        disposition_targets.extend(
            f"evidence_region:{region_id}"
            for component_id in multi_region_component_ids
            for region_id in assigned_by_component[component_id]
        )

    missing_dimensions: list[str] = []
    untraceable_dimensions: list[str] = []
    for component in draft.components:
        if component.kind == "hardware":
            continue
        for field in ("length", "width", "thickness"):
            target = f"component:{component.id}.{field}"
            value = getattr(component, field)
            if value.value_mm is None:
                missing_dimensions.append(target)
            elif not (
                value.dependency_refs or value.evidence_ids or value.dimension_ids
            ):
                untraceable_dimensions.append(target)

    settled_count = len(assigned) + len(nonmaterial) + len(duplicate)
    coverage = round(settled_count / len(regions), 6) if regions else 0.0
    reviewable = not invalid and (
        not regions
        or not (
            unresolved
            or missing_dimensions
            or untraceable_dimensions
        )
    )
    return EvidenceAccountingReport(
        candidate_regions=regions,
        assigned_region_ids=tuple(sorted(assigned)),
        nonmaterial_region_ids=tuple(sorted(nonmaterial)),
        duplicate_projection_region_ids=tuple(sorted(duplicate)),
        unresolved_region_ids=tuple(sorted(unresolved)),
        invalid_region_ids=tuple(sorted(set(invalid))),
        invalid_region_reasons=tuple(sorted(invalid_reasons)),
        panel_region_ids=tuple(sorted(panel)),
        hardware_region_ids=tuple(sorted(hardware)),
        multi_region_component_ids=multi_region_component_ids,
        required_existence_review_targets=tuple(
            sorted(f"component:{item.id}.existence" for item in draft.components)
        ),
        required_disposition_review_targets=tuple(sorted(set(disposition_targets))),
        missing_dimension_targets=tuple(sorted(missing_dimensions)),
        untraceable_dimension_targets=tuple(sorted(untraceable_dimensions)),
        evidence_coverage=coverage,
        reviewable=reviewable,
        claims_physical_piece_recall=False,
        warnings=tuple(sorted(warnings)),
    )


__all__ = [
    "EvidenceAccountingReport",
    "RelevantCandidateRegion",
    "build_evidence_accounting_report",
    "derive_relevant_candidate_regions",
]
