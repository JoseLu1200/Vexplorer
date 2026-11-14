from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    label: str = Field(min_length=1, max_length=160)
    size_mm: list[float] = Field(min_length=3, max_length=3)
    origin_mm: list[float] = Field(min_length=3, max_length=3)
    source_refs: list[str] = Field(min_length=1, max_length=16)
    assumptions: list[str] = Field(min_length=1, max_length=16)

    @field_validator("size_mm", "origin_mm")
    @classmethod
    def finite(cls, value, info):
        if any(not math.isfinite(v) or abs(v) > 100_000 for v in value):
            raise ValueError("coordinates_must_be_finite_and_bounded")
        if info.field_name == "size_mm" and any(v <= 0 for v in value):
            raise ValueError("dimensions_must_be_positive")
        return value

    @field_validator("source_refs", "assumptions")
    @classmethod
    def meaningful(cls, values):
        if any(not v.strip() or len(v) > 1000 for v in values):
            raise ValueError("empty_or_oversized_evidence")
        return values


class AssemblyProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["proposed", "insufficient_evidence", "unsupported"]
    intended_use: str = Field(min_length=1, max_length=240)
    unit: Literal["mm", "relative"]
    components: list[Component] = Field(default_factory=list, max_length=64)
    assumptions: list[str] = Field(default_factory=list, max_length=32)
    missing_information: list[str] = Field(default_factory=list, max_length=32)
    functional_notes: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("assumptions", "missing_information", "functional_notes")
    @classmethod
    def meaningful(cls, values):
        if any(not v.strip() or len(v) > 2000 for v in values):
            raise ValueError("empty_or_oversized_note")
        return values

    @model_validator(mode="after")
    def consistency(self):
        if len({p.id for p in self.components}) != len(self.components):
            raise ValueError("duplicate_component_id")
        if self.status == "proposed" and not self.components:
            raise ValueError("proposal_requires_components")
        if self.status != "proposed" and (
            self.components or not self.missing_information
        ):
            raise ValueError("abstention_requires_reason_and_no_parts")
        if self.status == "proposed" and not self.assumptions:
            raise ValueError("construction_requires_explicit_assumptions")
        return self
