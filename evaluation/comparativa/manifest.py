"""Corpus manifest readers: public side and (gated) private reference side.

``ManifestReader`` is the adaptation seam.  A new corpus format only needs a
subclass that implements ``public_cases``, ``case_meta``, ``corpus_info`` and
``_read_private``; the freeze gate in ``load_references`` is inherited and the
private side is reached through ``_read_private`` only.
"""

from __future__ import annotations

import json
import re
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .freeze import FreezeToken, sha256_bytes, verify_freeze
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
        public = self.public_dir.resolve()
        private = self.private_dir.resolve()
        if public == private or private in public.parents or public in private.parents:
            raise ComparisonError("public and private directories must be separate")

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
            for key in ("split", "family_hash"):
                if not isinstance(row.get(key), str) or not row[key]:
                    raise ComparisonError(f"public case {case_id} lacks {key}")
            if row.get("sha256") != case.sha256:
                raise ComparisonError(f"public case {case_id}: cases.json hash differs from the bundle")
            cases.append(case)
            self._meta[case_id] = CaseMeta(
                case_id=case_id,
                family=f"plankassembly:{case.view_kind}",
                split=row["split"],
                partition_id=row["family_hash"],
                development=row["split"] != "holdout",
            )
        self._cases = cases

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
                metadata = json.loads(archive.read("case.json").decode("utf-8"))
                data = archive.read("input.dxf")
        except (OSError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
            raise ComparisonError(f"bundle {case_id} unreadable: {exc}") from exc
        if not isinstance(metadata, dict) or set(metadata) != set(PUBLIC_PAYLOAD_KEYS):
            raise ComparisonError(f"bundle {case_id}: metadata keys differ from the public whitelist")
        if metadata["id"] != case_id or sha256_bytes(data) != metadata["sha256"]:
            raise ComparisonError(f"bundle {case_id}: id or hash mismatch")
        target = self.staging_dir / f"{case_id}.dxf"
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
        for row in rows:
            case_id = row.get("id")
            meta = self._meta.get(case_id)
            if meta is None:
                raise ComparisonError(f"reference {case_id!r} has no public case")
            if row.get("family_hash") != meta.partition_id:
                raise ComparisonError(f"reference {case_id}: family hash differs from the public side")
            result[case_id] = _plank_reference(case_id, row, self.quantity_identifiable)
        return result


def _plank_reference(case_id: str, row: dict[str, Any], quantity_identifiable: bool | None) -> ReferenceCase:
    """Group planks of identical dimensions into component types with a count."""

    groups: dict[tuple[float, float, float], int] = {}
    for component in row["components"]:
        bounds = component["bounds_mm"]
        sizes = sorted((round(bounds[i + 3] - bounds[i], 3) for i in range(3)), reverse=True)
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

    def __init__(self, demo_dir: Path, reference_dir: Path) -> None:
        self.demo_dir = Path(demo_dir)
        self.reference_dir = Path(reference_dir)

    def public_cases(self) -> list[PublicCase]:
        cases = []
        for stem in (*_DEV_WITH_REFERENCE, *_DEV_WITHOUT_REFERENCE):
            path = self.demo_dir / f"{stem}.dxf"
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise ComparisonError(f"development case missing: {path.name}") from exc
            cases.append(PublicCase(
                case_id=stem, path=path, sha256=sha256_bytes(data), format="dxf", unit="mm",
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

        result: dict[str, ReferenceCase | None] = {
            case: None for case in (*_DEV_WITH_REFERENCE, *_DEV_WITHOUT_REFERENCE)
        }
        # Abstention references are derived from the descriptor controls, not reviewed values.
        result["piezas_completo"] = build("piezas_completo", None)
        result["piezas_qty_desconocida"] = build("piezas_qty_desconocida", "quantity")
        result["piezas_espesor_desconocido"] = build("piezas_espesor_desconocido", "thickness")
        return result
