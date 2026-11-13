"""Offline preparation of development inputs; never an inference benchmark result."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import tempfile
import zipfile

import fitz


@dataclass(frozen=True)
class Audit:
    verified_files: int
    indexed_cases: int
    indexed_paths: int
    manifest_sha256: str


@dataclass(frozen=True)
class VisualCase:
    case_id: str
    source: str
    source_sha256: str
    crops: tuple[tuple[float, float, float, float], ...]
    task: str
    unit: str | None
    limitation: str


VISUAL_CASES = (
    VisualCase(
        "visual-001", "conjuntos/bench_vise/Mechanical Bench Vise.pdf",
        "39287a411617b2ee0677c1ff953482c118229f22373e934c15df1c3cde803c32",
        ((290, 170, 1040, 680),), "propose_components", None,
        "One assembled orthographic view. No dimensions or scale available; hidden components and quantities are ambiguous.",
    ),
    VisualCase(
        "visual-002", "conjuntos/bench_vise/Jaw Pad.pdf",
        "74d010275e3499850e53ea29b6bdc750c0a3e9c6830d92517e0ce40c0201fa61",
        ((70, 30, 540, 290), (275, 250, 395, 465)), "read_dimensions", "mm",
        "Annotated single-part control. Two cropped views do not establish assembly quantity. Unit comes from original title block.",
    ),
    VisualCase(
        "visual-003", "conjuntos/bench_vise/Jaw Pad.pdf",
        "74d010275e3499850e53ea29b6bdc750c0a3e9c6830d92517e0ce40c0201fa61",
        ((70, 30, 385, 240),), "read_dimensions_with_abstention", "mm",
        "Front view only. Thickness and assembly quantity are unknown. Unit comes from original title block.",
    ),
)

PUBLIC_INPUT_INSTRUCTION = (
    "Use only evidence visible in this input. Keep unsupported dimensions, identity, and quantity unknown."
)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_source(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError(f"unsafe path: {name!r}")
    relative = Path(name)
    if relative.is_absolute() or PureWindowsPath(name).is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe path: {name!r}")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"escaping path: {name!r}")
    return path


def _parse_manifest(source: Path, data: bytes) -> dict[str, str]:
    entries = {}
    for line in data.decode("utf-8").splitlines():
        if not line.strip():
            continue
        fields = line.split(maxsplit=1)
        if len(fields) != 2 or not re.fullmatch(r"[0-9a-f]{64}", fields[0]):
            raise ValueError("invalid hash manifest line")
        digest, name = fields
        name = name.removeprefix("*")
        safe_source(source, name)
        if name in entries:
            raise ValueError(f"duplicate manifest path: {name}")
        entries[name] = digest
    if "index.json" not in entries:
        raise ValueError("index.json missing from manifest")
    return entries


def read_manifest_snapshot(source: Path) -> tuple[dict[str, str], str]:
    data = (source / "SHA256SUMS").read_bytes()
    return _parse_manifest(source, data), hashlib.sha256(data).hexdigest()


def read_manifest(source: Path) -> dict[str, str]:
    return read_manifest_snapshot(source)[0]


def read_verified(source: Path, entries: dict[str, str], name: str) -> bytes:
    if name not in entries:
        raise ValueError(f"source path missing from manifest: {name}")
    path = safe_source(source, name)
    if not path.is_file():
        raise ValueError(f"missing source: {name}")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entries[name]:
        raise ValueError(f"hash mismatch: {name}")
    return data


def public_input_metadata(*, case_id: str, file: str, task: str, split: str,
                          format: str, unit: str | None, digest: str) -> dict[str, object]:
    public_task = task.removesuffix("_with_abstention")
    return {"id": case_id, "file": file, "task": public_task, "split": split, "format": format,
            "unit": unit, "limitation": PUBLIC_INPUT_INSTRUCTION, "sha256": digest}


def audit_dataset(source: Path, manifest_snapshot: tuple[dict[str, str], str] | None = None) -> Audit:
    source = source.resolve()
    entries, manifest_digest = manifest_snapshot or read_manifest_snapshot(source)
    for name, expected in entries.items():
        read_verified(source, entries, name)
    cases = json.loads(read_verified(source, entries, "index.json"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("index must contain cases")
    paths = 0
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or case["id"] in ids:
            raise ValueError("invalid or duplicate case id")
        ids.add(case["id"])
        found = False
        for field in ("input", "dxf", "dwg", "dimension_records"):
            if field not in case:
                continue
            name = case[field]
            safe_source(source, name)
            if name not in entries:
                raise ValueError(f"indexed path missing from manifest: {name}")
            paths += 1
            found = True
        if not found:
            raise ValueError(f"case has no indexed paths: {case['id']}")
    return Audit(len(entries), len(cases), paths, manifest_digest)


def render_crops(source: Path | bytes, destination: Path, crops: tuple[tuple[float, float, float, float], ...]) -> None:
    """Rebuild from pixels, not PDF clipping (which can retain hidden objects)."""
    if destination.exists():
        raise ValueError(f"destination exists: {destination}")
    if not crops:
        raise ValueError("no crops")
    original_document = fitz.open(source) if isinstance(source, Path) else fitz.open(stream=source, filetype="pdf")
    with original_document as original, fitz.open() as output:
        for crop in crops:
            rect = fitz.Rect(crop)
            if rect.is_empty or rect.is_infinite or not original[0].rect.contains(rect):
                raise ValueError("crop outside source page")
            pixels = original[0].get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
            page = output.new_page(width=rect.width, height=rect.height)
            page.insert_image(page.rect, stream=pixels.tobytes("png"))
        output.set_metadata({})
        output.save(destination, garbage=4, deflate=True, no_new_id=True)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def archive_tree(root: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())


def archive_case(root: Path, case: dict[str, object], destination: Path) -> None:
    path = safe_source(root, case["file"])
    if sha256(path) != case["sha256"]:
        raise ValueError("case input hash mismatch")
    name = "input" + path.suffix
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(path, name)
        archive.writestr("case.json", json.dumps({**case, "file": name}, indent=2))
    with zipfile.ZipFile(destination) as archive:
        if set(archive.namelist()) != {name, "case.json"} or archive.testzip() is not None:
            raise ValueError("case archive verification failed")


def prepare_dataset(source: Path, destination: Path) -> Audit:
    source, destination = source.resolve(), destination.resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("source/output overlap")
    if destination.exists():
        raise ValueError(f"output exists: {destination}")
    manifest_snapshot = read_manifest_snapshot(source)
    entries = manifest_snapshot[0]
    audit = audit_dataset(source, manifest_snapshot)
    for case in VISUAL_CASES:
        if entries.get(case.source) != case.source_sha256:
            raise ValueError(f"source revision differs from reviewed crop: {case.case_id}")
    catalog = json.loads(read_verified(source, entries, "index.json"))
    cad = sorted((c for c in catalog if c.get("track") == "single_part_cad_dimension_extraction"), key=lambda c: c["id"])
    if len(cad) != 14:
        raise ValueError("expected 14 admitted CAD extraction cases")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # An interrupted build remains explicitly partial; never overwrite the source or a prior pack.
    staging = Path(tempfile.mkdtemp(prefix=destination.name + ".partial-", dir=destination.parent))
    agent = staging / "agent_inputs"
    evaluator = staging / "evaluator_reference"
    agent.mkdir()
    evaluator.mkdir()
    isolated_cases = staging / "agent_cases"
    isolated_cases.mkdir()
    inputs, private = [], []
    for case in VISUAL_CASES:
        name = case.case_id + ".pdf"
        render_crops(read_verified(source, entries, case.source), agent / name, case.crops)
        inputs.append(public_input_metadata(
            case_id=case.case_id, file=name, task=case.task, split="development",
            format="raster_pdf", unit=case.unit, digest=sha256(agent / name),
        ))
        private.append({**asdict(case), "source_page": 1, "crop_units": "PDF points", "raster_scale": 2,
                        "family_id": "bench_vise", "split": "development"})
    for number, case in enumerate(cad, 1):
        case_id = f"cad-{number:03d}"
        name = case_id + ".dxf"
        (agent / name).write_bytes(read_verified(source, entries, case["dxf"]))
        ref = case.get("dimension_records")
        if ref:
            (evaluator / (case_id + "-publisher-dimensions.json")).write_bytes(
                read_verified(source, entries, ref)
            )
        inputs.append(public_input_metadata(
            case_id=case_id, file=name, task="extract_annotated_cad", split="development",
            format="dxf", unit=None, digest=sha256(agent / name),
        ))
        private.append({"id": case_id, "family_id": case["id"], "source": case["dxf"],
                        "source_sha256": entries[case["dxf"]], "publisher_reference": ref,
                        "reference_status": "publisher annotation, not independently certified gold",
                        "limitation": "Single component, annotations retained; not a blind despiece test."})
    # Only audited reference files are copied, never source scripts or a whole directory tree.
    for name in entries:
        if name.startswith("conjuntos/bench_vise/") and name.endswith((".pdf", "README.md", "source_manifest.json")):
            (evaluator / Path(name).name).write_bytes(read_verified(source, entries, name))
    (evaluator / "bench_vise_reference.json").write_bytes(
        read_verified(source, entries, "bench_vise_reference.json")
    )
    write_json(evaluator / "cases.json", private)
    write_json(evaluator / "audit.json", asdict(audit))
    write_json(evaluator / "expectations.json", {
        "visual-001": {"reference_unique_parts": 12, "reference_total_quantity": 22,
                       "dimension_target": None, "grading": "Hypotheses and abstention; exact BOM not identifiable from single view."},
        "visual-002": {"width_mm": 69.85, "height_mm": 44.45, "thickness_mm": 5.0, "quantity_from_input": None},
        "visual-003": {"width_mm": 69.85, "height_mm": 44.45, "thickness_from_input": None, "quantity_from_input": None},
        "notes": "Cases 001-003 share family and MUST NOT cross development/test splits. Pixel geometry is not a metric oracle. No inference has been evaluated."})
    write_json(agent / "cases.json", inputs)
    for item in inputs:
        if sha256(agent / item["file"]) != item["sha256"]:
            raise ValueError("generated input hash mismatch")
    for item in inputs:
        archive_case(agent, item, isolated_cases / (item["id"] + ".zip"))
    archive_tree(agent, staging / "agent_inputs.zip")
    archive_tree(evaluator, staging / "evaluator_reference.zip")
    with zipfile.ZipFile(staging / "agent_inputs.zip") as archive:
        expected = {item["file"] for item in inputs} | {"cases.json"}
        if set(archive.namelist()) != expected or archive.testzip() is not None:
            raise ValueError("agent archive verification failed")
    (staging / "README.md").write_text(
        "# Piloto local de desarrollo\n\n"
        "Entregar al agente SOLO un ZIP de agent_cases por ejecucion, con contexto y herramientas aislados.\n"
        "agent_inputs.zip es un archivo de transporte de TODAS las variantes: no debe exponerse a una ejecucion individual.\n"
        "evaluator_reference.zip contiene las respuestas y los originales; solo para el evaluador.\n"
        "La separacion de carpetas no limita los permisos del proceso: el futuro harness debe montar solo las entradas.\n"
        "17 casos: 14 DXF anotados de extraccion y 3 PDF rasterizados de vistas 2D. No son 17 despieces ni un test ciego.\n"
        "Los 50 conjuntos Julius quedan en el corpus original, verificados pero pendientes de anotacion/admission.\n"
        "Los PDF no tienen geometria CAD editable. No deducir escala de sus pixeles. El control conserva cotas, la variante pobre omite espesor.\n"
        "No se han ejecutado inferencias, medido precision ni estimado presupuestos. Conservar licencias del corpus fuente.\n",
        encoding="utf-8")
    files = sorted(p for p in staging.rglob("*") if p.is_file())
    (staging / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.relative_to(staging).as_posix()}\n" for p in files), encoding="utf-8")
    staging.rename(destination)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    if not args.audit_only and args.output is None:
        parser.error("--output is required unless --audit-only")
    try:
        result = audit_dataset(args.source) if args.audit_only else prepare_dataset(args.source, args.output)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Preparation failed: {exc}\n")
    print(json.dumps(asdict(result), indent=2))
    if not args.audit_only:
        print(f"Prepared: {args.output.resolve()}")


if __name__ == "__main__":
    main()
