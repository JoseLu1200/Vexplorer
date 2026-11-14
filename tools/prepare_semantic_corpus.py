"""Generate a private-reference semantic furniture corpus from owned synthetic designs.

The public output contains opaque strict-runner ZIP bundles only.  Project,
split, component, occurrence, role, mounting and alternative data remain in a
physically separate reference directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import zipfile

import ezdxf


GENERATOR_VERSION = "semantic-furniture-corpus-1"
SCHEMA_VERSION = "1.0"
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


def _development_designs() -> tuple[dict[str, Any], ...]:
    """Return public development projects; dimensions are millimetres."""

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
    )


def _load_private_designs(path: Path) -> tuple[dict[str, Any], ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid private design spec") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "semantic-private-design/v1":
        raise ValueError("invalid private design spec schema")
    designs = payload.get("designs")
    if not isinstance(designs, list) or not designs:
        raise ValueError("private design spec requires designs")
    required = {
        "project_id", "product_family", "split", "variants", "occurrences",
        "relations", "alternative_relation",
    }
    for design in designs:
        if not isinstance(design, dict) or set(design) != required or design.get("split") != "reserved":
            raise ValueError("invalid reserved design")
        if not isinstance(design.get("variants"), list) or not design["variants"]:
            raise ValueError("reserved design requires variants")
        if not isinstance(design.get("occurrences"), list) or not design["occurrences"]:
            raise ValueError("reserved design requires occurrences")
        if not isinstance(design.get("relations"), list) or not design["relations"]:
            raise ValueError("reserved design requires relations")
    return tuple(designs)


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


def _relations(design: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "subject_role": subject,
            "relation": relation,
            "object_role": target,
            "required": True,
        }
        for subject, relation, target in design["relations"]
    ]


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


def _write_dxf(path: Path, design: dict[str, Any], view_profile: str) -> None:
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
    offsets = (0.0, width + 100.0, width + depth + 200.0)
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
        document.saveas(path, encoding="utf-8", fmt="asc")
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
    (root / "SHA256SUMS").write_text("".join(lines), encoding="utf-8")


def prepare_semantic_corpus(
    public_destination: Path,
    private_destination: Path,
    *,
    private_design_spec: Path,
) -> dict[str, Any]:
    """Generate 12 development and 6 reserved cases into separate new directories."""

    public_destination = public_destination.resolve()
    private_destination = private_destination.resolve()
    private_design_spec = private_design_spec.resolve()
    designs = _development_designs() + _load_private_designs(private_design_spec)
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
                _write_dxf(dxf_path, design, view_profile)
                metadata = _write_bundle(dxf_path, case_id, public_stage / f"{case_id}.zip")
                dxf_path.unlink()
                split_counts[design["split"]] += 1
                base_relations = _relations(design)
                subject, relation, target = design["alternative_relation"]
                alternative_relations = [
                    item for item in base_relations
                    if (item["subject_role"], item["object_role"]) != (subject, target)
                ] + [{
                    "subject_role": subject,
                    "relation": relation,
                    "object_role": target,
                    "required": True,
                }]
                scenarios.append({
                    "schema_version": SCHEMA_VERSION,
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
                        "ambiguity": [{
                            "scope": "assembly_relations",
                            "reason": "orthographic outlines do not expose the join hardware",
                            "acceptable_values": ["supported_by", "fixed_to"],
                        }],
                    },
                    "design_geometry": {
                        "units": "mm",
                        "envelope_mm": _envelope(design["occurrences"]),
                        "occurrences": list(design["occurrences"]),
                    },
                })

        public_manifest = {
            "generator_version": GENERATOR_VERSION,
            "schema_version": SCHEMA_VERSION,
            "dataset_id": "semantic-furniture-synthetic-v1",
            "case_count": len(scenarios),
            "input_kind": "assembled_orthographic_dxf",
            "reference_included": False,
            "origin": "owned_synthetic_designs",
        }
        public_manifest_sha = _write_json(public_stage / "manifest.json", public_manifest)
        _write_hashes(public_stage)
        references_sha = _write_json(
            private_stage / "references.json",
            {"schema_version": SCHEMA_VERSION, "scenarios": scenarios},
        )
        private_manifest = {
            "generator_version": GENERATOR_VERSION,
            "schema_version": SCHEMA_VERSION,
            "dataset_id": "semantic-furniture-synthetic-v1",
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


def seal_semantic_reference(private_destination: Path, predictions_path: Path) -> Path:
    """Bind an evaluator-only envelope to a complete frozen prediction manifest."""

    private_destination = private_destination.resolve()
    predictions_path = predictions_path.resolve()
    target = private_destination / "evaluation-reference.json"
    if target.exists():
        raise ValueError("private reference already sealed")
    references_path = private_destination / "references.json"
    manifest_path = private_destination / "manifest.json"
    if not references_path.is_file() or not manifest_path.is_file():
        raise ValueError("invalid private reference directory")
    try:
        references = json.loads(references_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        prediction_bytes = predictions_path.read_bytes()
        predictions = json.loads(prediction_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid reference or prediction JSON") from exc
    scenarios = references.get("scenarios")
    prediction_cases = predictions.get("cases") if isinstance(predictions, dict) else None
    if not isinstance(scenarios, list) or not isinstance(prediction_cases, list):
        raise ValueError("reference and predictions require case lists")
    scenario_ids = [item.get("scenario_id") for item in scenarios if isinstance(item, dict)]
    prediction_ids = [
        item.get("scenario_id", item.get("id")) for item in prediction_cases if isinstance(item, dict)
    ]
    if (
        len(scenario_ids) != len(scenarios)
        or len(prediction_ids) != len(prediction_cases)
        or len(set(scenario_ids)) != len(scenario_ids)
        or len(set(prediction_ids)) != len(prediction_ids)
        or set(scenario_ids) != set(prediction_ids)
    ):
        raise ValueError("prediction case ids do not match private reference case ids")
    dataset_id = manifest.get("dataset_id")
    if predictions.get("dataset_id") != dataset_id:
        raise ValueError("prediction dataset id does not match private reference")
    envelope = {
        "schema_version": "semantic-evaluation/v1",
        "dataset": {
            "id": dataset_id,
            "predictions_sha256": _digest(prediction_bytes),
            "frozen_before_evaluation": True,
            "partition_policy": "project_and_family",
            "partition_unit": "project_id+structural_signature",
            "reference_visibility": "evaluator_only",
        },
        "cases": scenarios,
    }
    encoded = _json_bytes(envelope)
    with target.open("xb") as stream:
        stream.write(encoded)
    _write_hashes(private_destination)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-output", type=Path)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--private-design-spec", type=Path)
    parser.add_argument("--seal-predictions", type=Path)
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
            if args.public_output is None or args.private_design_spec is None:
                parser.error("--public-output and --private-design-spec are required while generating")
            result = prepare_semantic_corpus(
                args.public_output,
                args.private_output,
                private_design_spec=args.private_design_spec,
            )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Preparation failed: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
