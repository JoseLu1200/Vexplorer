"""Prepare a tiny, offline PlankAssembly development sample.

The public side contains only assembled orthographic DXF views.  Source
programs and component references remain in a physically separate private
directory.  This is dataset adaptation, not an inference benchmark result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import zipfile

import ezdxf


GENERATOR_VERSION = "plankassembly-adapter-2"
PUBLIC_INSTRUCTION = (
    "Use only geometry visible in the assembled orthographic views. "
    "Keep unsupported identity, dimensions, roles and quantities unknown."
)
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_split_name(split: str) -> str:
    if not split or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in split):
        raise ValueError("invalid source split")
    return split


def _load_model(source: Path, filename: str) -> tuple[dict[str, object], bytes]:
    if Path(filename).name != filename or not filename.endswith(".json"):
        raise ValueError(f"unsafe model filename: {filename!r}")
    model_path = source / "extracted" / "data" / "model" / filename
    data = model_path.read_bytes()
    model = json.loads(data)
    planks = model.get("planks")
    attach = model.get("attach")
    if not isinstance(planks, list) or len(planks) < 2 or not isinstance(attach, list):
        raise ValueError(f"invalid plank model: {filename}")
    if len(attach) != len(planks):
        raise ValueError(f"attach/planks length mismatch: {filename}")
    for bounds in planks:
        if (
            not isinstance(bounds, list)
            or len(bounds) != 6
            or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in bounds)
            or not all(bounds[index] < bounds[index + 3] for index in range(3))
        ):
            raise ValueError(f"invalid plank bounds: {filename}")
    normal = model.get("normal")
    if normal is not None and (not isinstance(normal, list) or len(normal) != len(planks)):
        raise ValueError(f"normal/planks length mismatch: {filename}")
    return model, data


def _family_hash(planks: list[list[float]]) -> str:
    dimensions = sorted(
        tuple(round(bounds[index + 3] - bounds[index], 6) for index in range(3))
        for bounds in planks[1:]
    )
    canonical = json.dumps(dimensions, separators=(",", ":")).encode("ascii")
    return _digest(canonical)[:16]


def _add_rectangle(modelspace, layer: str, x0: float, y0: float, x1: float, y1: float) -> None:
    points = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    for start, end in zip(points, points[1:] + points[:1]):
        modelspace.add_line(start, end, dxfattribs={"layer": layer})


def _write_assembled_dxf(path: Path, physical_planks: list[list[float]]) -> None:
    document = ezdxf.new("R2010", setup=False)
    document.units = ezdxf.units.MM
    # Eliminate clock- and host-derived header values so equal inputs are byte-identical.
    document.header["$TDCREATE"] = 0.0
    document.header["$TDUPDATE"] = 0.0
    document.header["$FINGERPRINTGUID"] = "{00000000-0000-0000-0000-000000000001}"
    document.header["$VERSIONGUID"] = "{00000000-0000-0000-0000-000000000002}"
    document.ezdxf_metadata()["CREATED_BY_EZDXF"] = "fixed adapter metadata"
    layers = ("ORTHO_FRONT", "ORTHO_TOP", "ORTHO_SIDE")
    for layer in layers:
        document.layers.add(layer, color=7)
    origin = [min(bounds[axis] for bounds in physical_planks) for axis in range(3)]
    width = max(bounds[3] for bounds in physical_planks) - origin[0]
    # Front and top both occupy width, while side occupies depth.
    offsets = (0.0, width + 100.0, 2 * width + 200.0)
    modelspace = document.modelspace()
    for bounds in physical_planks:
        xmin, ymin, zmin, xmax, ymax, zmax = [
            value - origin[index % 3] for index, value in enumerate(bounds)
        ]
        _add_rectangle(modelspace, layers[0], offsets[0] + xmin, zmin, offsets[0] + xmax, zmax)
        _add_rectangle(modelspace, layers[1], offsets[1] + xmin, ymin, offsets[1] + xmax, ymax)
        _add_rectangle(modelspace, layers[2], offsets[2] + ymin, zmin, offsets[2] + ymax, zmax)
    previous_fixed_metadata = ezdxf.options.write_fixed_meta_data_for_testing
    try:
        # ezdxf otherwise refreshes $VERSIONGUID, timestamps and EZDXF_META at write time.
        ezdxf.options.write_fixed_meta_data_for_testing = True
        document.saveas(path, encoding="utf-8", fmt="asc")
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = previous_fixed_metadata


def _archive_case(input_path: Path, metadata: dict[str, object], destination: Path) -> None:
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in (
            ("input.dxf", input_path.read_bytes()),
            ("case.json", (json.dumps({**metadata, "file": "input.dxf"}, indent=2, sort_keys=True) + "\n").encode()),
        ):
            info = zipfile.ZipInfo(name, _ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, data)


def _write_hashes(root: Path) -> None:
    lines = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append(f"{_digest(path.read_bytes())}  {path.relative_to(root).as_posix()}\n")
    (root / "SHA256SUMS").write_text("".join(lines), encoding="utf-8")


def prepare_plankassembly(
    source: Path,
    public_destination: Path,
    private_destination: Path,
    *,
    split: str = "valid",
    offset: int = 0,
    limit: int = 6,
) -> dict[str, object]:
    """Prepare 1–50 consecutive cases without loading the full source corpus."""
    source = source.resolve()
    public_destination = public_destination.resolve()
    private_destination = private_destination.resolve()
    split = _safe_split_name(split)
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if public_destination == private_destination or public_destination.is_relative_to(private_destination) or private_destination.is_relative_to(public_destination):
        raise ValueError("public and private destinations must be separate")
    if public_destination.exists() or private_destination.exists():
        raise ValueError("destination exists")
    split_path = source / "extracted" / "data" / "splits" / f"{split}.txt"
    filenames = [line.strip() for line in split_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(filenames) < offset + limit:
        raise ValueError("source split has fewer models than requested offset and limit")

    public_destination.parent.mkdir(parents=True, exist_ok=True)
    private_destination.parent.mkdir(parents=True, exist_ok=True)
    public_stage = Path(tempfile.mkdtemp(prefix=public_destination.name + ".partial-", dir=public_destination.parent))
    private_stage = Path(tempfile.mkdtemp(prefix=private_destination.name + ".partial-", dir=private_destination.parent))
    try:
        (public_stage / "agent_cases").mkdir()
        cases: list[dict[str, object]] = []
        references: list[dict[str, object]] = []
        for position, filename in enumerate(filenames[offset:offset + limit], offset + 1):
            model, source_bytes = _load_model(source, filename)
            planks = model["planks"]
            normal = model.get("normal")
            family_hash = _family_hash(planks)
            case_id = f"plank-{position:03d}"
            file_name = case_id + ".dxf"
            _write_assembled_dxf(public_stage / file_name, planks[1:])
            input_hash = _digest((public_stage / file_name).read_bytes())
            case_split = "holdout" if int(family_hash[:2], 16) % 5 == 0 else "development"
            metadata = {
                "id": case_id,
                "file": file_name,
                "format": "dxf",
                "unit": "mm",
                "view_kind": "assembled_orthographic",
                "split": case_split,
                "family_hash": family_hash,
                "instruction": PUBLIC_INSTRUCTION,
                "sha256": input_hash,
            }
            cases.append(metadata)
            agent_metadata = {
                key: metadata[key]
                for key in (
                    "id", "file", "format", "unit", "view_kind", "instruction", "sha256"
                )
            }
            _archive_case(
                public_stage / file_name,
                agent_metadata,
                public_stage / "agent_cases" / f"{case_id}.zip",
            )
            references.append({
                "id": case_id,
                "public_dxf_sha256": input_hash,
                "source_file": filename,
                "source_sha256": _digest(source_bytes),
                "family_hash": family_hash,
                "split": case_split,
                "envelope_source_index": 0,
                "components": [
                    {
                        "source_index": source_index,
                        "bounds_mm": bounds,
                        "normal": normal[source_index] if normal is not None else None,
                    }
                    for source_index, bounds in enumerate(planks[1:], 1)
                ],
                # Association values remain in the publisher's original index space.
                "source_attach_indices": model["attach"],
            })
        manifest = {
            "generator_version": GENERATOR_VERSION,
            "case_count": len(cases),
            "source_split": split,
            "source_offset": offset,
            "selection": "consecutive_range_in_publisher_split_for_local_adapter_trial",
            "inference_evaluated": False,
            "redistribution_authorized": False,
        }
        _write_json(public_stage / "cases.json", cases)
        _write_json(public_stage / "manifest.json", manifest)
        _write_json(private_stage / "references.json", references)
        _write_json(private_stage / "manifest.json", manifest)
        _write_hashes(public_stage)
        _write_hashes(private_stage)
        public_stage.rename(public_destination)
        private_stage.rename(private_destination)
        return manifest
    except Exception:
        shutil.rmtree(public_stage, ignore_errors=True)
        shutil.rmtree(private_stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--split", default="valid")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()
    try:
        result = prepare_plankassembly(
            args.source,
            args.public_output,
            args.private_output,
            split=args.split,
            offset=args.offset,
            limit=args.limit,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Preparation failed: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
