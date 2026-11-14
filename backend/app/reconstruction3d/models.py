from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
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
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
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


class ClarificationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=2000)


class EnvelopeConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    width: float | None = Field(default=None, gt=0, le=100_000)
    depth: float | None = Field(default=None, gt=0, le=100_000)
    height: float | None = Field(default=None, gt=0, le=100_000)


class RefinementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    answers: list[ClarificationAnswer] = Field(default_factory=list, max_length=32)
    intended_use: str | None = Field(default=None, min_length=1, max_length=240)
    envelope_mm: EnvelopeConstraints = Field(default_factory=EnvelopeConstraints)

    @model_validator(mode="after")
    def meaningful(self):
        if not (
            self.answers
            or self.intended_use
            or self.envelope_mm.model_dump(exclude_none=True)
        ):
            raise ValueError("refinement_requires_information")
        if len({a.question for a in self.answers}) != len(self.answers):
            raise ValueError("duplicate_question")
        return self
