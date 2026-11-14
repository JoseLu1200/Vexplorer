from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_MEMBERS = 2000
MAX_DIMENSIONS = 4096
MAX_IMAGE_BYTES = 2 * 1024 * 1024
Identifier = Annotated[
    str, Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_.:-]+$")
]


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Space(StrictModel):
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=240)
    revision: str = Field(min_length=1, max_length=160)
    mode: Literal["text", "image", "mixed", "geometry"]
    dimensions: int = Field(ge=1, le=MAX_DIMENSIONS)
    preprocessing: str = Field(min_length=1, max_length=160)
    precision: str = Field(default="float32", max_length=40)
    descriptor_version: str | None = Field(default=None, max_length=80)
    normalization: Literal["l2"] = "l2"

    @property
    def id(self) -> str:
        return digest(self.model_dump(mode="json"))


class Classification(StrictModel):
    label: str = Field(max_length=240)
    score: float = Field(ge=0, le=1)
    method: str = Field(max_length=80)
    artifact_id: str
    state: Literal["needs_review"] = "needs_review"
    calibrated: Literal[False] = False


class Entry(StrictModel):
    id: Identifier
    label: str = Field(min_length=1, max_length=300)
    vector: tuple[float, ...] = Field(min_length=1, max_length=MAX_DIMENSIONS)
    text: str = Field(default="", max_length=12000)
    category: str | None = Field(default=None, max_length=240)
    category_origin: Literal["editorial_proxy", "reviewed", "unknown"] = "unknown"
    split: str | None = Field(default=None, max_length=30)
    group_id: str | None = Field(default=None, max_length=160)
    run_id: Identifier | None = None
    result_revision: int | None = Field(default=None, ge=1)
    attributes: dict[str, str | float | None] = Field(
        default_factory=dict, max_length=60
    )
    features: dict[str, float] = Field(default_factory=dict, max_length=100)
    classification: Classification | None = None
    image_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    content_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def valid_vector(self):
        norm = math.hypot(*self.vector)
        if not math.isfinite(norm) or norm == 0:
            raise ValueError("invalid_vector")
        return self


class Bundle(StrictModel):
    schema_version: Literal[1] = 1
    space: Space
    entries: tuple[Entry, ...] = Field(max_length=MAX_MEMBERS)
    provenance: str = Field(default="", max_length=2000)
    synthetic: bool = False

    @model_validator(mode="after")
    def consistent(self):
        if len({e.id for e in self.entries}) != len(self.entries):
            raise ValueError("duplicate_ids")
        if any(len(e.vector) != self.space.dimensions for e in self.entries):
            raise ValueError("embedding_space_incompatible")
        return self


class SearchRequest(StrictModel):
    space: str = Field(min_length=1, max_length=200)
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    member_id: Identifier
    limit: int = Field(default=10, ge=1, le=50)
    category: str | None = Field(default=None, max_length=240)
    exclude_group: bool = False


class ReviewRequest(StrictModel):
    space: str = Field(min_length=1, max_length=200)
    snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    member_id: Identifier
