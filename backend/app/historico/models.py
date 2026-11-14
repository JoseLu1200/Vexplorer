from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EconomicScope = str


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )


class HistoricalProvenance(StrictModel):
    source: str = Field(min_length=1, max_length=500)
    source_date: date
    imported_by: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, min_length=1, max_length=2000)


class HistoricalConcept(StrictModel):
    concept_id: str = Field(min_length=1, max_length=100)
    kind: EconomicScope
    driver: Literal["fixed", "item", "length", "area", "volume"]
    cost: float | None = Field(default=None, ge=0)
    hours: float | None = Field(default=None, ge=0)
    material: str | None = Field(default=None, min_length=1, max_length=200)
    finish: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def has_economic_value(self) -> "HistoricalConcept":
        if self.cost is None and self.hours is None:
            raise ValueError("concept requires cost or hours")
        return self


class HistoricalRecord(StrictModel):
    record_id: str = Field(min_length=1, max_length=200)
    project_id: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=1, max_length=100)
    family: str | None = Field(default=None, min_length=1, max_length=200)
    width_mm: float | None = Field(default=None, gt=0)
    depth_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    area_mm2: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)
    volume_mm3: float | None = Field(default=None, gt=0)
    quantity: int | None = Field(default=None, gt=0)
    material: str | None = Field(default=None, min_length=1, max_length=200)
    finish: str | None = Field(default=None, min_length=1, max_length=200)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    actual_cost: float | None = Field(default=None, ge=0)
    cost_basis: Literal["actual", "quote", "budget"] | None = None
    manufacturing_hours: float | None = Field(default=None, ge=0)
    origin: Literal["actual", "published", "synthetic"]
    provenance: HistoricalProvenance
    concepts: tuple[HistoricalConcept, ...] = ()
    components: tuple["HistoricalComponentSummary", ...] = ()
    included_scope: tuple[EconomicScope, ...] = ()
    cost_scope: tuple[EconomicScope, ...] = ()
    hours_scope: tuple[EconomicScope, ...] = ()

    @model_validator(mode="after")
    def validate_economic_consistency(self) -> "HistoricalRecord":
        if self.actual_cost is not None and self.currency is None:
            raise ValueError("currency is required when actual_cost is present")
        if (self.actual_cost is None) != (self.cost_basis is None):
            raise ValueError("cost_basis is required exactly when actual_cost is present")
        ids = [item.concept_id for item in self.concepts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate concept_id")
        concept_costs = [item.cost for item in self.concepts if item.cost is not None]
        if self.actual_cost is not None and concept_costs:
            if abs(sum(concept_costs) - self.actual_cost) > 0.01:
                raise ValueError("concept costs must sum to actual_cost")
        concept_hours = [item.hours for item in self.concepts if item.hours is not None]
        if self.manufacturing_hours is not None and concept_hours:
            if abs(sum(concept_hours) - self.manufacturing_hours) > 0.001:
                raise ValueError("concept hours must sum to manufacturing_hours")
        if self.actual_cost is None and self.manufacturing_hours is None:
            raise ValueError("record requires actual_cost or manufacturing_hours")
        inferred_cost_scope = {
            item.kind for item in self.concepts if item.cost is not None
        }
        inferred_hours_scope = {
            item.kind for item in self.concepts if item.hours is not None
        }
        if self.actual_cost is not None and not self.cost_scope:
            raise ValueError("cost_scope is required when actual_cost is present")
        if self.actual_cost is None and self.cost_scope:
            raise ValueError("cost_scope must be empty when actual_cost is absent")
        if self.manufacturing_hours is not None and not self.hours_scope:
            raise ValueError(
                "hours_scope is required when manufacturing_hours is present"
            )
        if self.manufacturing_hours is None and self.hours_scope:
            raise ValueError(
                "hours_scope must be empty when manufacturing_hours is absent"
            )
        if self.concepts and inferred_cost_scope != set(self.cost_scope):
            raise ValueError("cost_scope must exactly match cost-bearing concept kinds")
        if self.concepts and inferred_hours_scope != set(self.hours_scope):
            raise ValueError("hours_scope must exactly match hours-bearing concept kinds")
        combined_scope = set(self.cost_scope) | set(self.hours_scope)
        if not self.included_scope:
            raise ValueError("included_scope is required")
        if not combined_scope.issubset(self.included_scope):
            raise ValueError("included_scope must cover every historical concept kind")
        for name, values in (
            ("included_scope", self.included_scope),
            ("cost_scope", self.cost_scope),
            ("hours_scope", self.hours_scope),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {name} entry")
            if any(not item.strip() for item in values):
                raise ValueError(f"blank {name} entry")
        component_ids = [item.component_id for item in self.components]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("duplicate historical component_id")
        return self


class HistoricalComponentSummary(StrictModel):
    component_id: str = Field(min_length=1, max_length=200)
    kind: str | None = Field(default=None, min_length=1, max_length=100)
    quantity: int | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)
    width_mm: float | None = Field(default=None, gt=0)
    thickness_mm: float | None = Field(default=None, gt=0)
    area_mm2: float | None = Field(default=None, gt=0)
    volume_mm3: float | None = Field(default=None, gt=0)
    material: str | None = Field(default=None, min_length=1, max_length=200)
    finish: str | None = Field(default=None, min_length=1, max_length=200)


class HistoricalImport(StrictModel):
    records: tuple[HistoricalRecord, ...] = Field(min_length=1, max_length=10_000)


class ImportErrorItem(StrictModel):
    row: int
    error: str


class ImportResult(StrictModel):
    import_id: str
    dry_run: bool
    accepted: int
    unchanged: int
    rejected: int
    errors: tuple[ImportErrorItem, ...] = ()


class HistoricalRecordPage(StrictModel):
    items: tuple[HistoricalRecord, ...]
    total: int
    limit: int
    offset: int


class HistoricalTarget(StrictModel):
    family: str | None = Field(default=None, min_length=1, max_length=200)
    width_mm: float | None = Field(default=None, gt=0)
    depth_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    area_mm2: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)
    volume_mm3: float | None = Field(default=None, gt=0)
    quantity: int | None = Field(default=None, gt=0)
    material: str | None = Field(default=None, min_length=1, max_length=200)
    finish: str | None = Field(default=None, min_length=1, max_length=200)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    basis_revision: str = Field(min_length=1, max_length=200)
    exclude_project_id: str | None = Field(default=None, min_length=1, max_length=200)
    exclude_record_ids: tuple[str, ...] = ()
    required_cost_scope: tuple[EconomicScope, ...] = ()
    required_hours_scope: tuple[EconomicScope, ...] = ()

    @model_validator(mode="after")
    def scope_entries_are_unique(self) -> "HistoricalTarget":
        if len(self.required_cost_scope) != len(set(self.required_cost_scope)):
            raise ValueError("duplicate required_cost_scope entry")
        if len(self.required_hours_scope) != len(set(self.required_hours_scope)):
            raise ValueError("duplicate required_hours_scope entry")
        if any(not item.strip() for item in self.required_cost_scope):
            raise ValueError("blank required_cost_scope entry")
        if any(not item.strip() for item in self.required_hours_scope):
            raise ValueError("blank required_hours_scope entry")
        return self


class EmbeddingSpace(StrictModel):
    model: str
    dimensions: int = Field(gt=0)


class HistoricalComparable(StrictModel):
    record: HistoricalRecord
    score: float = Field(ge=-1, le=1)
    score_components: dict[str, float]
    differences: tuple[str, ...]
    missing_fields: tuple[str, ...]


class ComparableResponse(StrictModel):
    retrieval_method: Literal["attribute", "semantic"]
    items: tuple[HistoricalComparable, ...]
    embedding_space: EmbeddingSpace | None = None


class ComparableRequest(StrictModel):
    target: HistoricalTarget
    limit: int = Field(default=5, ge=1, le=50)
    retrieval_method: Literal["attribute", "semantic"] = "attribute"
    include_synthetic: bool = False


class EstimateRequest(StrictModel):
    target: HistoricalTarget
    comparable_ids: tuple[str, ...] = ()
    include_synthetic: bool = False


class EstimateContributor(StrictModel):
    concept_id: str
    kind: str
    comparable_ids: tuple[str, ...]
    formula: str
    base_cost: float | None
    base_hours: float | None
    quantity_factor: float | None
    consumption_factor: float | None
    unit_rate_factor: float | None
    estimated_cost: float | None
    estimated_hours: float | None
    evidence: Literal["concept_breakdown", "global_analogy"]
    missing_data: tuple[str, ...] = ()


class EstimateProvenance(StrictModel):
    record_id: str
    origin: Literal["actual", "published", "synthetic"]
    source: str
    source_date: date
    cost_basis: Literal["actual", "quote", "budget"] | None
    contributes_cost: bool
    contributes_hours: bool
    cost_scope: tuple[str, ...]
    hours_scope: tuple[str, ...]


class HistoricalEstimateScenario(StrictModel):
    record_id: str
    weight: float = Field(gt=0)
    contributors: tuple[EstimateContributor, ...]
    cost_total: float | None
    hours_total: float | None


class HistoricalEstimate(StrictModel):
    basis_revision: str
    currency: str | None
    effective_cost_scope: tuple[str, ...]
    effective_hours_scope: tuple[str, ...]
    comparable_ids: tuple[str, ...]
    result_provenance: tuple[EstimateProvenance, ...]
    contributors: tuple[EstimateContributor, ...]
    scenarios: tuple[HistoricalEstimateScenario, ...]
    cost_subtotal: float | None
    manufacturing_hours: float | None
    cost_range: tuple[float, float] | None
    hours_range: tuple[float, float] | None
    uncertainty: Literal["low", "medium", "high", "not_estimable"]
    cost_uncertainty: Literal["low", "medium", "high", "not_estimable"]
    hours_uncertainty: Literal["low", "medium", "high", "not_estimable"]
    missing_data: tuple[str, ...]
    assumptions: tuple[str, ...]


class ProvisionalDimension(StrictModel):
    value_mm: float | None = Field(default=None, gt=0)
    state: Literal["observed", "derived", "hypothesis", "unknown", "conflict"]
    review_status: Literal["accepted", "rejected", "conflict", "abstained"]
    check_ids: tuple[str, ...] = ()
    dependency_refs: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def evidence_matches_state(self) -> "ProvisionalDimension":
        if self.state in {"unknown", "conflict"}:
            if self.value_mm is not None:
                raise ValueError("unknown or conflict dimension must not carry a value")
        elif self.value_mm is None:
            raise ValueError("resolved provisional dimension requires a value")
        if self.state == "hypothesis" and not (
            self.dependency_refs or self.evidence_ids
        ):
            raise ValueError("hypothesis dimension requires dependency or source evidence")
        if self.review_status == "accepted" and not self.check_ids:
            raise ValueError("accepted dimension requires review check IDs")
        return self


class ProvisionalText(StrictModel):
    value: str | None = Field(default=None, min_length=1, max_length=300)
    state: Literal["observed", "derived", "hypothesis", "unknown", "conflict"]
    review_status: Literal["accepted", "rejected", "conflict", "abstained"]
    check_ids: tuple[str, ...] = ()
    dependency_refs: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def evidence_matches_state(self) -> "ProvisionalText":
        if self.state in {"unknown", "conflict"}:
            if self.value is not None:
                raise ValueError("unknown or conflict text must not carry a value")
        elif self.value is None:
            raise ValueError("resolved provisional text requires a value")
        if self.state == "hypothesis" and not (
            self.dependency_refs or self.evidence_ids
        ):
            raise ValueError("hypothesis text requires dependency or source evidence")
        if self.review_status == "accepted" and not self.check_ids:
            raise ValueError("accepted text requires review check IDs")
        return self


class ProvisionalQuantity(StrictModel):
    value: int | None = Field(default=None, gt=0, le=1000)
    state: Literal["hypothesis", "unknown", "conflict"]
    review_status: Literal["accepted", "rejected", "conflict", "abstained"]
    check_ids: tuple[str, ...] = ()
    check_kinds: tuple[
        Literal[
            "geometry_match",
            "cross_view_identity",
            "duplicate_scan",
            "quantity_basis",
            "dimension_binding",
            "visual_consistency",
        ],
        ...,
    ] = ()
    premise_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def accepted_hypothesis_has_closed_evidence(self) -> "ProvisionalQuantity":
        if self.state in {"unknown", "conflict"}:
            if self.value is not None:
                raise ValueError("unknown or conflict quantity must not carry a value")
            return self
        if self.value is None:
            raise ValueError("hypothesis quantity requires a value")
        if self.review_status == "accepted" and (
            not self.check_ids
            or len(self.check_ids) != len(set(self.check_ids))
            or not {"quantity_basis", "duplicate_scan"}.issubset(self.check_kinds)
            or not self.premise_refs
            or not self.source_refs
        ):
            raise ValueError("accepted quantity evidence is incomplete")
        return self


class ProvisionalScenarioRow(StrictModel):
    component_id: str = Field(min_length=1, max_length=200)
    occurrence_status: Literal["confirmed", "provisional", "unknown"]
    scenario_occurrence_ids: tuple[str, ...] = ()
    quantity: ProvisionalQuantity
    length: ProvisionalDimension
    width: ProvisionalDimension
    thickness: ProvisionalDimension
    material: ProvisionalText
    finish: ProvisionalText
    source_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def occurrences_match_quantity(self) -> "ProvisionalScenarioRow":
        if len(self.scenario_occurrence_ids) != len(
            set(self.scenario_occurrence_ids)
        ):
            raise ValueError("duplicate scenario occurrence ID")
        if (
            self.quantity.value is not None
            and len(self.scenario_occurrence_ids) != self.quantity.value
        ):
            raise ValueError("scenario occurrence count must equal quantity value")
        return self


class ProvisionalScenarioSnapshot(StrictModel):
    run_id: str = Field(min_length=1, max_length=200)
    proposal_revision: int = Field(gt=0)
    review_revision: int = Field(gt=0)
    auto_review_status: Literal["accepted", "incomplete", "conflict", "abstained"]
    rows: tuple[ProvisionalScenarioRow, ...] = Field(max_length=256)

    @model_validator(mode="after")
    def mapper_output_is_unique(self) -> "ProvisionalScenarioSnapshot":
        component_ids = [row.component_id for row in self.rows]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("duplicate provisional component_id")
        occurrence_ids = [
            occurrence
            for row in self.rows
            for occurrence in row.scenario_occurrence_ids
        ]
        if len(occurrence_ids) != len(set(occurrence_ids)):
            raise ValueError("duplicate provisional scenario occurrence ID")
        return self


class ProvisionalScenarioRequest(StrictModel):
    run_id: str = Field(min_length=1, max_length=200)
    proposal_revision: int = Field(gt=0)
    review_revision: int = Field(gt=0)
    limit: int = Field(default=3, ge=1, le=10)
    retrieval_method: Literal["attribute", "semantic"] = "attribute"


class ProvisionalAssumption(StrictModel):
    code: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    detail: str = Field(min_length=1, max_length=1000)
    state: Literal["conditional", "provisional"]


class ProvisionalScenarioCondition(StrictModel):
    furniture_quantity: Literal[1] = 1
    family: str = Field(min_length=1, max_length=200)
    material: str = Field(min_length=1, max_length=200)
    finish: str = Field(min_length=1, max_length=200)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    cost_scope: tuple[EconomicScope, ...]
    hours_scope: tuple[EconomicScope, ...]


class ProvisionalScalingBasis(StrictModel):
    component_ids: tuple[str, ...] = Field(min_length=1)
    scenario_occurrence_ids: tuple[str, ...] = Field(min_length=1)
    length_mm: float = Field(gt=0)
    area_mm2: float = Field(gt=0)
    volume_mm3: float | None = Field(default=None, gt=0)
    units: Literal["mm_mm2_mm3"] = "mm_mm2_mm3"
    source_refs: tuple[str, ...] = Field(min_length=1)


class ProvisionalHistoricalScenario(StrictModel):
    scenario_id: str = Field(min_length=1, max_length=300)
    label: Literal["conditional_provisional_not_quote"] = (
        "conditional_provisional_not_quote"
    )
    comparable_id: str = Field(min_length=1, max_length=200)
    source_effective_date: date
    condition: ProvisionalScenarioCondition
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    scaling_basis: ProvisionalScalingBasis
    assumptions: tuple[ProvisionalAssumption, ...] = Field(min_length=1)
    contributors: tuple[EstimateContributor, ...]
    result_provenance: tuple[EstimateProvenance, ...] = Field(min_length=1)
    cost_subtotal: float | None
    manufacturing_hours: float | None
    cost_range: tuple[float, float] | None
    hours_range: tuple[float, float] | None
    cost_uncertainty: Literal["low", "medium", "high", "not_estimable"]
    hours_uncertainty: Literal["low", "medium", "high", "not_estimable"]
    missing_data: tuple[str, ...]


class ProvisionalScenarioResponse(StrictModel):
    run_id: str
    proposal_revision: int = Field(gt=0)
    review_revision: int = Field(gt=0)
    status: Literal["provisional", "not_estimable"]
    label: Literal["conditional_provisional_not_quote"] = (
        "conditional_provisional_not_quote"
    )
    assumptions: tuple[ProvisionalAssumption, ...]
    scenarios: tuple[ProvisionalHistoricalScenario, ...]
    missing_data: tuple[str, ...]
