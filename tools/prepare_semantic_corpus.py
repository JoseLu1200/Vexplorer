"""Generate a private-reference semantic furniture corpus from owned synthetic designs.

The public output contains opaque strict-runner ZIP bundles only.  Project,
split, component, occurrence, role, mounting and alternative data remain in a
physically separate reference directory.
"""
from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import zipfile

import ezdxf

from tools.semantic_corpus_v2 import V2_VIEW_PROFILES, additional_designs_v2
from tools.seal_semantic_reference import seal_semantic_reference


GENERATOR_VERSION = "semantic-furniture-corpus-2"
SCHEMA_VERSION = "2.0"
PUBLIC_INSTRUCTION = (
    "Use only geometry visible in the assembled orthographic views. "
    "Keep unsupported identity, dimensions, roles and quantities unknown."
)
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _write_json(path: Path, value: object) -> str:
    encoded = _json_bytes(value)
    path.write_bytes(encoded)
    return _digest(encoded)


def _occurrence(identifier: str, role: str, bounds: tuple[float, ...]) -> dict[str, Any]:
    if len(bounds) != 6 or any(bounds[index] >= bounds[index + 3] for index in range(3)):
        raise ValueError(f"invalid occurrence bounds: {identifier}")
    return {"occurrence_id": identifier, "role": role, "bounds_mm": list(bounds)}


def _designs_v1() -> tuple[dict[str, Any], ...]:
    """Return six manually specified projects; dimensions are millimetres."""

    return (
        {
            "project_id": "dev-open-bay",
            "product_family": "shelving",
            "split": "development",
            "variants": ("full_three_view", "missing_side", "missing_top", "occluded_front"),
            "occurrences": (
                _occurrence("o1", "side_panel", (0, 0, 0, 18, 320, 900)),
                _occurrence("o2", "side_panel", (782, 0, 0, 800, 320, 900)),
                _occurrence("o3", "top_panel", (18, 0, 882, 782, 320, 900)),
                _occurrence("o4", "bottom_panel", (18, 0, 0, 782, 320, 18)),
                _occurrence("o5", "shelf", (18, 0, 294, 391, 320, 312)),
                _occurrence("o6", "shelf", (409, 0, 294, 782, 320, 312)),
                _occurrence("o7", "shelf", (18, 0, 588, 391, 320, 606)),
                _occurrence("o8", "shelf", (409, 0, 588, 782, 320, 606)),
                _occurrence("o9", "divider", (391, 0, 18, 409, 320, 882)),
            ),
            "relations": (
                ("top_panel", "fixed_to", "side_panel"),
                ("bottom_panel", "fixed_to", "side_panel"),
                ("shelf", "supported_by", "side_panel"),
                ("shelf", "fixed_to", "divider"),
                ("divider", "fixed_to", "top_panel"),
                ("divider", "fixed_to", "bottom_panel"),
            ),
            "alternative_relation": ("shelf", "fixed_to", "side_panel"),
        },
        {
            "project_id": "dev-trestle",
            "product_family": "table",
            "split": "development",
            "variants": ("full_three_view", "missing_side", "missing_top", "occluded_front"),
            "occurrences": (
                _occurrence("o1", "tabletop", (0, 0, 720, 1400, 700, 750)),
                _occurrence("o2", "leg_frame", (150, 100, 0, 220, 600, 720)),
                _occurrence("o3", "leg_frame", (1180, 100, 0, 1250, 600, 720)),
                _occurrence("o4", "stretcher", (220, 320, 300, 1180, 380, 390)),
            ),
            "relations": (
                ("tabletop", "supported_by", "leg_frame"),
                ("stretcher", "fixed_to", "leg_frame"),
            ),
            "alternative_relation": ("tabletop", "fixed_to", "leg_frame"),
        },
        {
            "project_id": "dev-double-front",
            "product_family": "cabinetry",
            "split": "development",
            "variants": ("full_three_view", "missing_side", "missing_top", "occluded_front"),
            "occurrences": (
                _occurrence("o1", "side_panel", (0, 0, 0, 18, 560, 720)),
                _occurrence("o2", "side_panel", (882, 0, 0, 900, 560, 720)),
                _occurrence("o3", "top_panel", (18, 0, 702, 882, 560, 720)),
                _occurrence("o4", "bottom_panel", (18, 0, 0, 882, 560, 18)),
                _occurrence("o5", "back_panel", (18, 542, 18, 882, 560, 702)),
                _occurrence("o6", "shelf", (18, 0, 230, 882, 542, 248)),
                _occurrence("o7", "shelf", (18, 0, 472, 882, 542, 490)),
                _occurrence("o8", "door", (18, -20, 18, 445, 0, 702)),
                _occurrence("o9", "door", (455, -20, 18, 882, 0, 702)),
            ),
            "relations": (
                ("top_panel", "fixed_to", "side_panel"),
                ("bottom_panel", "fixed_to", "side_panel"),
                ("back_panel", "fixed_to", "side_panel"),
                ("shelf", "supported_by", "side_panel"),
                ("door", "hinged_to", "side_panel"),
            ),
            "alternative_relation": ("shelf", "fixed_to", "side_panel"),
        },
        {
            "project_id": "hold-ladder",
            "product_family": "shelving",
            "split": "reserved",
            "variants": ("missing_side", "occluded_front"),
            "occurrences": (
                _occurrence("o1", "upright", (0, 0, 0, 45, 45, 1600)),
                _occurrence("o2", "upright", (755, 0, 0, 800, 45, 1600)),
                _occurrence("o3", "upright", (0, 305, 0, 45, 350, 1600)),
                _occurrence("o4", "upright", (755, 305, 0, 800, 350, 1600)),
                _occurrence("o5", "shelf", (45, 0, 220, 755, 350, 245)),
                _occurrence("o6", "shelf", (45, 0, 600, 755, 350, 625)),
                _occurrence("o7", "shelf", (45, 0, 980, 755, 350, 1005)),
                _occurrence("o8", "shelf", (45, 0, 1360, 755, 350, 1385)),
                _occurrence("o9", "rear_rail", (45, 315, 1500, 755, 350, 1545)),
            ),
            "relations": (
                ("shelf", "supported_by", "upright"),
                ("rear_rail", "fixed_to", "upright"),
            ),
            "alternative_relation": ("shelf", "fixed_to", "upright"),
        },
        {
            "project_id": "hold-pedestal",
            "product_family": "table",
            "split": "reserved",
            "variants": ("missing_top", "occluded_front"),
            "occurrences": (
                _occurrence("o1", "tabletop", (0, 0, 700, 1000, 1000, 745)),
                _occurrence("o2", "pedestal", (430, 430, 80, 570, 570, 700)),
                _occurrence("o3", "base", (250, 250, 0, 750, 750, 80)),
            ),
            "relations": (
                ("tabletop", "supported_by", "pedestal"),
                ("pedestal", "fixed_to", "base"),
            ),
            "alternative_relation": ("tabletop", "fixed_to", "pedestal"),
        },
        {
            "project_id": "hold-wall-single",
            "product_family": "cabinetry",
            "split": "reserved",
            "variants": ("missing_side", "missing_top"),
            "occurrences": (
                _occurrence("o1", "side_panel", (0, 0, 0, 16, 320, 700)),
                _occurrence("o2", "side_panel", (584, 0, 0, 600, 320, 700)),
                _occurrence("o3", "top_panel", (16, 0, 684, 584, 320, 700)),
                _occurrence("o4", "bottom_panel", (16, 0, 0, 584, 320, 16)),
                _occurrence("o5", "back_panel", (16, 304, 16, 584, 320, 684)),
                _occurrence("o6", "shelf", (16, 0, 342, 584, 304, 358)),
                _occurrence("o7", "door", (16, -18, 16, 584, 0, 684)),
                _occurrence("o8", "mounting_rail", (80, 290, 590, 520, 304, 630)),
                _occurrence("o9", "mounting_rail", (80, 290, 80, 520, 304, 120)),
            ),
            "relations": (
                ("top_panel", "fixed_to", "side_panel"),
                ("bottom_panel", "fixed_to", "side_panel"),
                ("back_panel", "fixed_to", "side_panel"),
                ("shelf", "supported_by", "side_panel"),
                ("door", "hinged_to", "side_panel"),
                ("mounting_rail", "fixed_to", "back_panel"),
            ),
            "alternative_relation": ("shelf", "fixed_to", "side_panel"),
        },
    )


def _designs_v2() -> tuple[dict[str, Any], ...]:
    """Return 16 independent topologies; view profiles are not new designs."""

    inherited = tuple(
        # All v1 projects, including its old reserved cohort, are regression
        # material in v2 and therefore development-only.
        {**design, "split": "development", "variants": V2_VIEW_PROFILES}
        for design in _designs_v1()
    )
    designs = inherited + additional_designs_v2()
    signatures = [_structure_signature(design) for design in designs]
    if len(signatures) != len(set(signatures)):
        raise ValueError("v2 designs require distinct structural signatures")
    return designs


def _structure_signature(design: dict[str, Any]) -> str:
    roles = Counter(item["role"] for item in design["occurrences"])
    canonical = {
        "roles": sorted(roles.items()),
        "relations": sorted(design["relations"]),
    }
    return _digest(json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode())[:20]


def _validate_no_positive_volume_overlap(design: dict[str, Any]) -> None:
    occurrences = design["occurrences"]
    for index, first in enumerate(occurrences):
        a = first["bounds_mm"]
        for second in occurrences[index + 1:]:
            b = second["bounds_mm"]
            overlap = all(min(a[axis + 3], b[axis + 3]) > max(a[axis], b[axis]) for axis in range(3))
            if overlap:
                raise ValueError(
                    f"positive-volume overlap in {design['project_id']}: "
                    f"{first['occurrence_id']} / {second['occurrence_id']}"
                )


def _components(design: dict[str, Any]) -> list[dict[str, Any]]:
    counts = Counter(item["role"] for item in design["occurrences"])
    return [
        {
            "label": role.replace("_", " "),
            "role": role,
            "quantity": quantity,
            "required": True,
            "aliases": [role.replace("_", "-")],
        }
        for role, quantity in sorted(counts.items())
    ]


def _relations(design: dict[str, Any], *, observable_semantics: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "subject_role": subject,
            "relation": relation,
            "object_role": target,
            # Orthographic contact cannot establish glue, screws, hinges or
            # other hidden join hardware. Keep design truth while only
            # requiring the directly support-like relation from predictions.
            "required": relation == "supported_by" if observable_semantics else True,
        }
        for subject, relation, target in design["relations"]
    ]


def _relation_ambiguity(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ambiguous = []
    for item in relations:
        if item["required"]:
            continue
        ambiguous.append({
            "scope": f"assembly_relation:{item['subject_role']}:{item['object_role']}",
            "reason": "orthographic outlines do not expose the joint method or hardware",
            "acceptable_values": [item["relation"], "unknown"],
        })
    return ambiguous


def _evaluation_annotations(design: dict[str, Any], view_profile: str) -> dict[str, Any]:
    complexity = len(design["occurrences"]) + len(design["relations"])
    if view_profile == "full_three_view" and complexity <= 12:
        difficulty = "easy"
    elif view_profile in {"occluded_front", "missing_front"} or complexity >= 17:
        difficulty = "hard"
    else:
        difficulty = "medium"
    unknowns = ["assembly_joint_method"]
    if view_profile.startswith("missing_"):
        unknowns.append("identity_across_missing_projection")
    if view_profile == "occluded_front":
        unknowns.append("occluded_component_identity_or_quantity")
    return {
        "difficulty": difficulty,
        "expected_unknowns": unknowns,
        "evidence_scope": "orthographic_outlines_only",
    }


def _envelope(occurrences: tuple[dict[str, Any], ...]) -> list[float]:
    return [
        min(item["bounds_mm"][axis] for item in occurrences)
        for axis in range(3)
    ] + [
        max(item["bounds_mm"][axis] for item in occurrences)
        for axis in range(3, 6)
    ]


def _add_rectangle(modelspace: Any, layer: str, box: tuple[float, float, float, float]) -> None:
    x0, y0, x1, y1 = box
    points = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    for start, end in zip(points, points[1:] + points[:1]):
        modelspace.add_line(start, end, dxfattribs={"layer": layer})


def _write_dxf(
    path: Path,
    design: dict[str, Any],
    view_profile: str,
    *,
    separate_views: bool = False,
) -> None:
    document = ezdxf.new("R2010", setup=False)
    document.units = ezdxf.units.MM
    document.header["$TDCREATE"] = 0.0
    document.header["$TDUPDATE"] = 0.0
    document.header["$FINGERPRINTGUID"] = "{00000000-0000-0000-0000-000000000001}"
    document.header["$VERSIONGUID"] = "{00000000-0000-0000-0000-000000000002}"
    document.ezdxf_metadata()["CREATED_BY_EZDXF"] = "fixed synthetic corpus metadata"
    for layer in ("V0", "V1", "V2", "N0"):
        document.layers.add(layer, color=7)
    modelspace = document.modelspace()
    envelope = _envelope(design["occurrences"])
    xmin, ymin, zmin, xmax, ymax, _ = envelope
    width = xmax - xmin
    depth = ymax - ymin
    offsets = (
        (-xmin, width + 100.0 - xmin, 2.0 * width + 200.0 - ymin)
        if separate_views
        else (0.0, width + 100.0, width + depth + 200.0)
    )
    visible = {
        "V0": view_profile != "missing_front",
        "V1": view_profile != "missing_top",
        "V2": view_profile != "missing_side",
    }
    for index, item in enumerate(design["occurrences"]):
        x0, y0, z0, x1, y1, z1 = item["bounds_mm"]
        projections = {
            "V0": (offsets[0] + x0, z0, offsets[0] + x1, z1),
            "V1": (offsets[1] + x0, y0, offsets[1] + x1, y1),
            "V2": (offsets[2] + y0, z0, offsets[2] + y1, z1),
        }
        for layer, rectangle in projections.items():
            if not visible[layer]:
                continue
            if view_profile == "occluded_front" and layer == "V0" and index % 3 == 1:
                continue
            _add_rectangle(modelspace, layer, rectangle)
    if view_profile == "occluded_front":
        # Unlabelled scan-like fragments create a controlled imperfect view.
        modelspace.add_line((width * 0.19, 17), (width * 0.23, 17), dxfattribs={"layer": "N0"})
        modelspace.add_line((width * 0.71, 31), (width * 0.76, 31), dxfattribs={"layer": "N0"})
    previous = ezdxf.options.write_fixed_meta_data_for_testing
    try:
        ezdxf.options.write_fixed_meta_data_for_testing = True
        if separate_views:
            # ezdxf discovers some CLASS records through a set, so insertion
            # order otherwise varies with PYTHONHASHSEED and changes DXF/ZIP
            # bytes despite identical geometry.  v1 intentionally keeps its
            # historical serialization; v2 canonicalizes before export.
            document.classes.add_required_classes(document.dxfversion)
            document.classes.classes = OrderedDict(
                sorted(document.classes.classes.items())
            )
        # Preserve the original Windows byte format on every host.
        document.filename = str(path)
        with path.open("w", encoding="utf-8", errors="dxfreplace", newline="\r\n") as stream:
            document.write(stream, fmt="asc")
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = previous


def _write_bundle(dxf_path: Path, case_id: str, destination: Path) -> dict[str, Any]:
    raw = dxf_path.read_bytes()
    metadata = {
        "id": case_id,
        "file": "input.dxf",
        "format": "dxf",
        "unit": "mm",
        "view_kind": "assembled_orthographic",
        "instruction": PUBLIC_INSTRUCTION,
        "sha256": _digest(raw),
    }
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in (("input.dxf", raw), ("case.json", _json_bytes(metadata))):
            info = zipfile.ZipInfo(name, _ZIP_DATE)
            info.create_system = 0  # Frozen DOS ZIP metadata, independent of host OS.
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)
    return metadata


def _write_hashes(root: Path) -> None:
    lines = [
        f"{_digest(path.read_bytes())}  {path.relative_to(root).as_posix()}\n"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    (root / "SHA256SUMS").write_text("".join(lines), encoding="utf-8", newline="\r\n")


def prepare_semantic_corpus(
    public_destination: Path,
    private_destination: Path,
    *,
    corpus_version: str = "v2",
) -> dict[str, Any]:
    """Generate a selected corpus version into physically separate new directories."""

    if corpus_version not in {"v1", "v2"}:
        raise ValueError("corpus_version must be v1 or v2")
    is_v2 = corpus_version == "v2"
    designs = _designs_v2() if is_v2 else _designs_v1()
    schema_version = SCHEMA_VERSION if is_v2 else "1.0"
    generator_version = GENERATOR_VERSION if is_v2 else "semantic-furniture-corpus-1"
    dataset_id = f"semantic-furniture-synthetic-{corpus_version}"

    public_destination = public_destination.resolve()
    private_destination = private_destination.resolve()
    if (
        public_destination == private_destination
        or public_destination.is_relative_to(private_destination)
        or private_destination.is_relative_to(public_destination)
    ):
        raise ValueError("public and private destinations must be separate")
    if public_destination.exists() or private_destination.exists():
        raise ValueError("destination exists")
    public_destination.parent.mkdir(parents=True, exist_ok=True)
    private_destination.parent.mkdir(parents=True, exist_ok=True)
    public_stage = Path(tempfile.mkdtemp(prefix=public_destination.name + ".partial-", dir=public_destination.parent))
    private_stage = Path(tempfile.mkdtemp(prefix=private_destination.name + ".partial-", dir=private_destination.parent))
    try:
        scenarios: list[dict[str, Any]] = []
        split_counts: Counter[str] = Counter()
        case_number = 0
        for design in designs:
            _validate_no_positive_volume_overlap(design)
            signature = _structure_signature(design)
            for view_profile in design["variants"]:
                case_number += 1
                case_id = f"sx-{case_number:03d}"
                dxf_path = public_stage / f".{case_id}.dxf"
                _write_dxf(
                    dxf_path,
                    design,
                    view_profile,
                    separate_views=is_v2,
                )
                metadata = _write_bundle(dxf_path, case_id, public_stage / f"{case_id}.zip")
                dxf_path.unlink()
                split_counts[design["split"]] += 1
                base_relations = _relations(design, observable_semantics=is_v2)
                subject, relation, target = design["alternative_relation"]
                added_relation = {
                    "subject_role": subject,
                    "relation": relation,
                    "object_role": target,
                    "required": relation == "supported_by" if is_v2 else True,
                }
                alternative_relations = (
                    [*base_relations, added_relation]
                    if is_v2
                    else [
                        item for item in base_relations
                        if (item["subject_role"], item["object_role"]) != (subject, target)
                    ] + [added_relation]
                )
                ambiguity = (
                    _relation_ambiguity(base_relations)
                    if is_v2
                    else [{
                        "scope": "assembly_relations",
                        "reason": "orthographic outlines do not expose the join hardware",
                        "acceptable_values": ["supported_by", "fixed_to"],
                    }]
                )
                scenarios.append({
                    "schema_version": schema_version,
                    "scenario_id": case_id,
                    "split": design["split"],
                    "project_id": design["project_id"],
                    "product_family": design["product_family"],
                    "structural_signature": signature,
                    "view_profile": view_profile,
                    "input_sha256": metadata["sha256"],
                    "reference": {
                        "certification": "design_known_synthetic",
                        "components": _components(design),
                        "assembly_relations": base_relations,
                        "valid_alternatives": [{
                            "id": "visually_indistinguishable_join_method",
                            "assembly_relations": alternative_relations,
                        }],
                        "ambiguity": ambiguity,
                    },
                    "design_geometry": {
                        "units": "mm",
                        "envelope_mm": _envelope(design["occurrences"]),
                        "occurrences": list(design["occurrences"]),
                        **({
                            "evaluation_annotations": _evaluation_annotations(
                                design, view_profile
                            )
                        } if is_v2 else {}),
                    },
                })

        public_manifest = {
            "generator_version": generator_version,
            "schema_version": schema_version,
            "dataset_id": dataset_id,
            "case_count": len(scenarios),
            "input_kind": "assembled_orthographic_dxf",
            "reference_included": False,
            "origin": "owned_synthetic_designs",
        }
        public_manifest_sha = _write_json(public_stage / "manifest.json", public_manifest)
        _write_hashes(public_stage)
        references_sha = _write_json(
            private_stage / "references.json",
            {"schema_version": schema_version, "scenarios": scenarios},
        )
        private_manifest = {
            "generator_version": generator_version,
            "schema_version": schema_version,
            "dataset_id": dataset_id,
            "case_count": len(scenarios),
            "split_counts": dict(sorted(split_counts.items())),
            "certification": "design_known_synthetic",
            "public_manifest_sha256": public_manifest_sha,
            "references_sha256": references_sha,
        }
        private_manifest_sha = _write_json(private_stage / "manifest.json", private_manifest)
        _write_hashes(private_stage)
        public_stage.rename(public_destination)
        private_stage.rename(private_destination)
        return {
            "case_count": len(scenarios),
            "split_counts": dict(sorted(split_counts.items())),
            "public_manifest_sha256": public_manifest_sha,
            "private_manifest_sha256": private_manifest_sha,
        }
    except Exception:
        shutil.rmtree(public_stage, ignore_errors=True)
        shutil.rmtree(private_stage, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-output", type=Path)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--seal-predictions", type=Path)
    parser.add_argument("--corpus-version", choices=("v1", "v2"), default="v2")
    args = parser.parse_args(argv)
    try:
        if args.seal_predictions is not None:
            if args.public_output is not None:
                parser.error("--public-output cannot be used while sealing")
            result: Any = {
                "sealed_reference": str(
                    seal_semantic_reference(args.private_output, args.seal_predictions)
                )
            }
        else:
            if args.public_output is None:
                parser.error("--public-output is required while generating")
            result = prepare_semantic_corpus(
                args.public_output,
                args.private_output,
                corpus_version=args.corpus_version,
            )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Preparation failed: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
