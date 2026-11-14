"""Corpus manifest readers: public side and (gated) private reference side.

``ManifestReader`` is the adaptation seam.  A new corpus format only needs a
subclass that implements ``public_cases``, ``case_meta``, ``corpus_info`` and
``_read_private``; the freeze gate in ``load_references`` is inherited and the
private side is reached through ``_read_private`` only.
"""

from __future__ import annotations

import json
import math
import re
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .freeze import FreezeToken, load_freeze_record, sha256_bytes, verify_freeze
from .model import (
    DIMENSION_FIELDS,
    PUBLIC_INSTRUCTION,
    PUBLIC_PAYLOAD_KEYS,
    CaseMeta,
    ComparisonError,
    PublicCase,
    RefComponent,
    ReferenceCase,
    ReferenceNotFrozen,
    RefField,
)

_CASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
_MAX_DXF_BYTES = 20 * 1024 * 1024


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComparisonError(f"cannot read {label}: {exc}") from exc


def _assert_disjoint(dir_a: Path, dir_b: Path, label_a: str, label_b: str) -> None:
    a = dir_a.resolve()
    b = dir_b.resolve()
    if a == b or a in b.parents or b in a.parents:
        raise ComparisonError(f"{label_a} and {label_b} directories must be disjoint")


class ManifestReader(ABC):
    corpus_id: str

    @abstractmethod
    def public_cases(self) -> list[PublicCase]:
        """Method-visible cases.  Must never touch the private side."""

    @abstractmethod
    def case_meta(self) -> dict[str, CaseMeta]:
        """Harness-only grouping data derived from the public side."""

    @abstractmethod
    def corpus_info(self) -> dict[str, Any]:
        """Public provenance for the report (no reference values)."""

    @abstractmethod
    def _read_private(self) -> dict[str, ReferenceCase | None]:
        """Single entry point to the private reference.  Do not call directly."""

    def load_references(self, token: FreezeToken) -> dict[str, ReferenceCase | None]:
        """Return the private reference iff the run is verifiably frozen."""

        if not isinstance(token, FreezeToken) or not token.is_genuine():
            raise ReferenceNotFrozen("a verified freeze token is required")
        current = verify_freeze(token.run_dir)
        if current.outputs_digest != token.outputs_digest:
            raise ReferenceNotFrozen("freeze token does not match the frozen run")
        record = load_freeze_record(token.run_dir)
        if record.get("inputs") != {c.case_id: c.sha256 for c in self.public_cases()}:
            raise ReferenceNotFrozen("inputs mismatch with frozen run")
        if record.get("corpus") != json.loads(json.dumps(self.corpus_info())):
            raise ReferenceNotFrozen("corpus mismatch with frozen run")
        return self._read_private()


# --------------------------------------------------------------------------- #
# PlankAssembly adapter output (tools/prepare_plankassembly.py)
# --------------------------------------------------------------------------- #

class PlankAssemblyManifestReader(ManifestReader):
    """Reads the public/private pair written by ``tools/prepare_plankassembly.py``.

    Public: ``cases.json`` (harness metadata) + ``agent_cases/<id>.zip`` (the only
    thing a method receives).  Private: ``references.json`` with ``bounds_mm``.
    Plank quantities are identical-dimension counts; by project policy the views
    do not establish them, so they are annotated ``identifiable=False`` unless
    ``quantity_identifiable`` says otherwise.
    """

    corpus_id = "plankassembly"

    def __init__(
        self,
        public_dir: Path,
        private_dir: Path,
        staging_dir: Path,
        *,
        quantity_identifiable: bool | None = False,
    ) -> None:
        self.public_dir = Path(public_dir)
        self.private_dir = Path(private_dir)
        self.staging_dir = Path(staging_dir)
        self.quantity_identifiable = quantity_identifiable
        self._cases: list[PublicCase] | None = None
        self._meta: dict[str, CaseMeta] = {}
        self._manifest: dict[str, Any] = {}
        _assert_disjoint(self.public_dir, self.private_dir, "public", "private")
        _assert_disjoint(self.staging_dir, self.private_dir, "staging", "private")

    def _load_public(self) -> None:
        if self._cases is not None:
            return
        rows = _read_json(self.public_dir / "cases.json", "public cases.json")
        if not isinstance(rows, list) or not rows:
            raise ComparisonError("public cases.json must be a non-empty array")
        self._manifest = _read_json(self.public_dir / "manifest.json", "public manifest.json")
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        cases: list[PublicCase] = []
        for row in rows:
            case_id = row.get("id") if isinstance(row, dict) else None
            if not isinstance(case_id, str) or not _CASE_ID_RE.fullmatch(case_id):
                raise ComparisonError("invalid public case id")
            if case_id in self._meta:
                raise ComparisonError(f"duplicate case id {case_id!r}")
            case = self._read_bundle(case_id)
            if row.get("sha256") != case.sha256:
                raise ComparisonError(f"public case {case_id}: cases.json hash differs from the bundle")
            cases.append(case)
            self._meta[case_id] = self._case_meta(row, case)
        self._cases = cases

    def _case_meta(self, row: dict[str, Any], case: PublicCase) -> CaseMeta:
        """Harness-only grouping of one public row (hook for other public layouts)."""
        for key in ("split", "family_hash"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ComparisonError(f"public case {case.case_id} lacks {key}")
        return CaseMeta(
            case_id=case.case_id,
            family=f"plankassembly:{case.view_kind}",
            split=row["split"],
            partition_id=row["family_hash"],
            development=row["split"] != "holdout",
        )

    def _read_bundle(self, case_id: str) -> PublicCase:
        bundle = self.public_dir / "agent_cases" / f"{case_id}.zip"
        try:
            with zipfile.ZipFile(bundle) as archive:
                names = [info.filename for info in archive.infolist()]
                if len(names) != len(set(names)) or set(names) != {"input.dxf", "case.json"}:
                    raise ComparisonError(f"bundle {case_id}: unexpected members")
                for info in archive.infolist():
                    if info.is_dir() or info.file_size > _MAX_DXF_BYTES:
                        raise ComparisonError(f"bundle {case_id}: unsafe member")
                with archive.open("case.json") as fp:
                    raw_json = fp.read(_MAX_DXF_BYTES + 1)
                    if len(raw_json) > _MAX_DXF_BYTES:
                        raise ComparisonError(f"bundle {case_id}: member exceeds maximum size")
                    metadata = json.loads(raw_json.decode("utf-8"))
                with archive.open("input.dxf") as fp:
                    data = fp.read(_MAX_DXF_BYTES + 1)
                    if len(data) > _MAX_DXF_BYTES:
                        raise ComparisonError(f"bundle {case_id}: member exceeds maximum size")
        except (OSError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
            raise ComparisonError(f"bundle {case_id} unreadable: {exc}") from exc
        if not isinstance(metadata, dict) or set(metadata) != set(PUBLIC_PAYLOAD_KEYS):
            raise ComparisonError(f"bundle {case_id}: metadata keys differ from the public whitelist")
        if metadata["id"] != case_id or sha256_bytes(data) != metadata["sha256"]:
            raise ComparisonError(f"bundle {case_id}: id or hash mismatch")
        target = self.staging_dir / f"{case_id}.dxf"
        if target.is_symlink():
            raise ComparisonError(f"bundle target {target} is a symlink")
        target.write_bytes(data)
        return PublicCase(
            case_id=case_id,
            path=target,
            sha256=metadata["sha256"],
            format=metadata["format"],
            unit=metadata["unit"],
            view_kind=metadata["view_kind"],
            instruction=metadata["instruction"],
        )

    def public_cases(self) -> list[PublicCase]:
        self._load_public()
        assert self._cases is not None
        return list(self._cases)

    def case_meta(self) -> dict[str, CaseMeta]:
        self._load_public()
        return dict(self._meta)

    def corpus_info(self) -> dict[str, Any]:
        self._load_public()
        return {
            "id": self.corpus_id,
            "kind": "plankassembly_adapter_output",
            "generator_version": self._manifest.get("generator_version"),
            "source_split": self._manifest.get("source_split"),
            "case_count": len(self._meta),
            "public_cases_sha256": sha256_bytes((self.public_dir / "cases.json").read_bytes()),
            "quantity_identifiable": self.quantity_identifiable,
        }

    def _read_private(self) -> dict[str, ReferenceCase | None]:
        self._load_public()
        rows = _read_json(self.private_dir / "references.json", "private references.json")
        if not isinstance(rows, list):
            raise ComparisonError("private references.json must be an array")
        result: dict[str, ReferenceCase | None] = {case_id: None for case_id in self._meta}
        seen_ids: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ComparisonError("private reference row must be an object")
            case_id = row.get("id")
            if not isinstance(case_id, str):
                raise ComparisonError("private reference case id must be a string")
            if case_id in seen_ids:
                raise ComparisonError(f"duplicate reference case id {case_id!r}")
            seen_ids.add(case_id)
            meta = self._meta.get(case_id)
            if meta is None:
                raise ComparisonError(f"reference {case_id!r} has no public case")
            if row.get("family_hash") != meta.partition_id:
                raise ComparisonError(f"reference {case_id}: family hash differs from the public side")
            result[case_id] = _plank_reference(case_id, row, self.quantity_identifiable)
        return result


def _plank_reference(case_id: str, row: dict[str, Any], quantity_identifiable: bool | None) -> ReferenceCase:
    """Group planks of identical dimensions into component types with a count."""

    if not isinstance(row, dict):
        raise ComparisonError(f"case {case_id}: reference row must be an object")
    raw_components = row.get("components")
    if not isinstance(raw_components, list):
        raise ComparisonError(f"case {case_id}: components must be a list")
    groups: dict[tuple[float, float, float], int] = {}
    for idx, component in enumerate(raw_components):
        if not isinstance(component, dict):
            raise ComparisonError(f"case {case_id}.components[{idx}]: must be an object")
        bounds = component.get("bounds_mm")
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 6:
            raise ComparisonError(f"case {case_id}.components[{idx}]: bounds_mm must have 6 elements")
        for val in bounds:
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ComparisonError(f"case {case_id}.components[{idx}]: bounds_mm elements must be finite numbers")
        for i in range(3):
            if not bounds[i + 3] > bounds[i]:
                raise ComparisonError(f"case {case_id}.components[{idx}]: bounds_mm[{i+3}] must be > bounds_mm[{i}]")
        sizes = sorted((round(float(bounds[i + 3] - bounds[i]), 3) for i in range(3)), reverse=True)
        key = (sizes[0], sizes[1], sizes[2])
        groups[key] = groups.get(key, 0) + 1
    components = []
    for index, (dims, count) in enumerate(sorted(groups.items(), reverse=True), 1):
        components.append(RefComponent(
            key=f"R{index}",
            dimensions={name: RefField(value, True) for name, value in zip(DIMENSION_FIELDS, dims)},
            quantity=RefField(float(count), quantity_identifiable),
        ))
    return ReferenceCase(case_id, tuple(components))
    return ReferenceCase(case_id, tuple(components))


class PlankAssemblyCorpusReader(PlankAssemblyManifestReader):
    """Reads the public/private pair written by ``tools/plankassembly_corpus.py``.

    The public ``cases.json`` carries only the method-visible metadata plus the
    official ``partition`` (train/valid/test); it deliberately has no family or
    group identifier, and this reader neither needs nor looks for one.  The
    harness-side ``partition_id`` is derived from the public ``partition`` alone
    (coarse and opaque): near-duplicate groups never cross partitions in that
    corpus, so excluding precedents of the same partition removes every possible
    relative of a case without opening the private side.

    Private: ``references.json``.  Complete cases carry ``components`` with
    ``bounds_mm``; poor-view variants carry only ``variant_of`` and are scored
    against the complete reference of their base case.  The private side is
    reached only through ``_read_private`` (gated by ``load_references``).
    """

    corpus_id = "plankassembly-corpus"
    _PARTITIONS = ("train", "valid", "test")

    def _case_meta(self, row: dict[str, Any], case: PublicCase) -> CaseMeta:
        partition = row.get("partition")
        if partition not in self._PARTITIONS:
            raise ComparisonError(f"public case {case.case_id} lacks a valid partition")
        digest = sha256_bytes(f"{self.corpus_id}|{partition}".encode())[:12]
        return CaseMeta(
            case_id=case.case_id,
            family=f"{self.corpus_id}:{case.view_kind}",
            split=partition,
            partition_id=f"{self.corpus_id}-{digest}",
            development=partition != "test",
        )

    def _load_public(self) -> None:
        if self._cases is not None:
            return
        super()._load_public()
        expected = self._manifest.get("cases_sha256") if isinstance(self._manifest, dict) else None
        actual = sha256_bytes((self.public_dir / "cases.json").read_bytes())
        if expected is not None and expected != actual:
            self._cases = None
            self._meta = {}
            raise ComparisonError("public cases.json differs from its manifest hash")

    def corpus_info(self) -> dict[str, Any]:
        self._load_public()
        return {
            "id": self.corpus_id,
            "kind": "plankassembly_corpus_output",
            "generator_version": self._manifest.get("generator_version"),
            "partitions": self._manifest.get("partitions"),
            "case_count": len(self._meta),
            "public_cases_sha256": sha256_bytes((self.public_dir / "cases.json").read_bytes()),
            "quantity_identifiable": self.quantity_identifiable,
        }

    def _read_private(self) -> dict[str, ReferenceCase | None]:
        self._load_public()
        rows = _read_json(self.private_dir / "references.json", "private references.json")
        if not isinstance(rows, list):
            raise ComparisonError("private references.json must be an array")
        by_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ComparisonError("private reference row must be an object")
            case_id = row.get("id")
            if not isinstance(case_id, str):
                raise ComparisonError("private reference case id must be a string")
            meta = self._meta.get(case_id)
            if meta is None:
                raise ComparisonError(f"reference {case_id!r} has no public case")
            if case_id in by_id:
                raise ComparisonError(f"duplicate reference {case_id!r}")
            if row.get("partition") != meta.split:
                raise ComparisonError(f"reference {case_id}: partition differs from the public side")
            by_id[case_id] = row
        result: dict[str, ReferenceCase | None] = {case_id: None for case_id in self._meta}
        for case_id, row in by_id.items():
            variant_of = row.get("variant_of")
            if variant_of is not None:
                if not isinstance(variant_of, str):
                    raise ComparisonError(f"reference {case_id}: variant_of must be a string")
                if variant_of not in by_id:
                    raise ComparisonError(f"reference {case_id}: variant_of base {variant_of!r} does not exist")
                source = by_id[variant_of]
                if not isinstance(source, dict) or "components" not in source:
                    raise ComparisonError(f"reference {case_id}: variant_of base {variant_of!r} has no components")
            else:
                source = row
                if "components" not in source:
                    continue  # no reference available: counted in the sample, never scored
            result[case_id] = _plank_reference(case_id, source, self.quantity_identifiable)
        return result


# --------------------------------------------------------------------------- #
# Own development cases (data/planos_demo + evaluation/reference)
# --------------------------------------------------------------------------- #

# Cases whose reference the files support.  piezas_dimensiones_variante and
# piezas_espesor_36 have no reviewed values; estanteria_* carry alternative
# construction scenarios with unannotated identifiability; mesa_* needs the
# table-profile contract.  All of them are excluded on purpose.
_DEV_WITH_REFERENCE = (
    "piezas_completo",
    "piezas_qty_desconocida",
    "piezas_espesor_desconocido",
)
_DEV_WITHOUT_REFERENCE = ("piezas_dimensiones_variante", "piezas_espesor_36")
_DEV_EXCLUDED = {
    "estanteria_*": "reference holds alternative scenarios and unannotated identifiability",
    "mesa_*": "needs the rectangular_table_v1 contract, outside this comparison",
    "piezas_ids_trasladados, piezas_ambigua_sin_id": "descriptor controls, no reviewed component values",
}
_HIDDEN_PIECE = "K3"  # the control fixtures hide a field of the third piece


class DevelopmentManifestReader(ManifestReader):
    """Own synthetic development cases.  Every case is already inspected."""

    corpus_id = "development"

    def __init__(self, demo_dir: Path, reference_dir: Path, staging_dir: Path) -> None:
        self.demo_dir = Path(demo_dir)
        self.reference_dir = Path(reference_dir)
        self.staging_dir = Path(staging_dir)
        _assert_disjoint(self.staging_dir, self.reference_dir, "staging", "reference")
        stems = (*_DEV_WITH_REFERENCE, *_DEV_WITHOUT_REFERENCE)
        # Opaque ids: the method never sees the revealing file names or the source path.
        self.id_map: dict[str, str] = {f"dev-{n:03d}": stem for n, stem in enumerate(stems, 1)}

    def public_cases(self) -> list[PublicCase]:
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        cases = []
        for case_id, stem in self.id_map.items():
            source = self.demo_dir / f"{stem}.dxf"
            try:
                data = source.read_bytes()
            except OSError as exc:
                raise ComparisonError(f"development case missing: {case_id}") from exc
            target = self.staging_dir / f"{case_id}.dxf"
            target.write_bytes(data)
            cases.append(PublicCase(
                case_id=case_id, path=target, sha256=sha256_bytes(data), format="dxf", unit="mm",
                view_kind="separated_part_views", instruction=PUBLIC_INSTRUCTION,
            ))
        return cases

    def case_meta(self) -> dict[str, CaseMeta]:
        return {
            case.case_id: CaseMeta(
                case_id=case.case_id,
                family=f"development:{case.view_kind}",
                split="development_case",
                partition_id="piezas",
                development=True,
            )
            for case in self.public_cases()
        }

    def corpus_info(self) -> dict[str, Any]:
        return {
            "id": self.corpus_id,
            "kind": "own_synthetic_development_cases",
            "all_cases_inspected_during_development": True,
            "id_map": dict(self.id_map),
            "cases_with_reference": list(_DEV_WITH_REFERENCE),
            "cases_without_reference": list(_DEV_WITHOUT_REFERENCE),
            "excluded": dict(_DEV_EXCLUDED),
        }

    def _read_private(self) -> dict[str, ReferenceCase | None]:
        reference = _read_json(self.reference_dir / "piezas_reference.json", "piezas_reference.json")
        pieces = reference["reviewed_reference"]["pieces"]

        def build(case_id: str, hide: str | None) -> ReferenceCase:
            components = []
            for piece in pieces:
                hidden = piece["public_key"] == _HIDDEN_PIECE
                dims = {
                    name: RefField(float(value), not (hide == "thickness" and hidden and name == "thickness"))
                    for name, value in zip(DIMENSION_FIELDS, piece["dimensions_mm"])
                }
                components.append(RefComponent(
                    key=piece["public_key"],
                    dimensions=dims,
                    quantity=RefField(float(piece["quantity"]), not (hide == "quantity" and hidden)),
                ))
            return ReferenceCase(case_id, tuple(components))

        by_stem = {stem: case_id for case_id, stem in self.id_map.items()}
        result: dict[str, ReferenceCase | None] = dict.fromkeys(self.id_map)
        # Abstention references are derived from the descriptor controls, not reviewed values.
        for stem, hide in (
            ("piezas_completo", None),
            ("piezas_qty_desconocida", "quantity"),
            ("piezas_espesor_desconocido", "thickness"),
        ):
            result[by_stem[stem]] = build(by_stem[stem], hide)
        return result
