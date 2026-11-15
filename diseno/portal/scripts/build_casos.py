"""Genera los casos congelados de src/casos/datos/*.json desde archivos versionados en git de Vexplorer.

Solo lee el repo de Vexplorer. Uso:

    C:/Users/marti/Proyectos/Vexplorer/.venv/Scripts/python.exe -B scripts/build_casos.py [ruta-vexplorer]

Cada JSON conserva las formas del contrato del backend, sin traducir, para que el mismo adaptador
(src/general/adaptador.ts) sirva para el caso congelado y para la respuesta en vivo:

  vía general (F01-F03, pipeline con modelo):
    drawing          DrawingExtraction de extract_drawing(F0x.dxf, input_kind="general_furniture"),
                     el mismo extractor que usa el servidor, así que los ids de contorno coinciden.
    construction     derived.package.construction del outcome (piezas, láminas con primitivas,
                     colocaciones, decisiones, avisos).
    validation       latest.review.construction_validation.
    artifacts        metadatos de artefactos derivados. El contenido (SVG/DXF/CSV) no está en git.
    evaluation       *.evaluation.json, evaluador estricto offline.

  vía legacy (data/muebles_procesados_demo, geometry_only, sintéticos):
    drawing          drawing.json (DrawingExtraction).
    result, scene, explanations, estimate   de resultado.json (revisión del manifest).

  pipeline guardado (data/plank_pipeline_demo/runs/<run_id>, ejecuciones reales):
    general plank-030 y plank-016: drawing, record (general.json), derived (derived.json, con el
                     contenido de los artefactos), assembly (assembly.json), events (events.json).
    tabla, mesa con coste: drawing, run, table, scene, table_drawings con el SVG/DXF de cada lámina
                     (table-artifacts/rN), table_costs, events.

  Todos los casos llevan `original`: el DXF de entrada tal cual, para «Abrir en CAD».
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "src" / "casos" / "datos"
VEXPLORER = Path(sys.argv[1] if len(sys.argv) > 1 else "C:/Users/marti/Proyectos/Vexplorer").resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(VEXPLORER))
os.chdir(VEXPLORER)

from backend.app.geometria.extraction import extract_drawing  # noqa: E402

RESULTS = Path("evaluation/results/cad_completion_live_2026-11-14")
CONTROLS = Path("data/cad_completion_controls/public")
DEMO = Path("data/muebles_procesados_demo")
DOC_CAD = "docs/VERIFICACION_CAD_COMPLETION_2026-11-14.md"
PLANK = Path("data/plank_pipeline_demo")
PLANK_ATTRIBUTION = "PlankAssembly, manycore-research, CC BY-NC-ND 4.0"
FULL = Path("data/full_app_demo")
# Construcción 3D (data/full_app_demo/reconstruction): GLB e imagen fuente a public/local/reconstruccion/<job>/,
# carpeta ignorada por git; el resto de cada trabajo, en el JSON del caso. Versiones de padre a hija.
LOCAL = HERE.parent / "public" / "local" / "reconstruccion"
PARTS_CASES = [
    {"id": "piezas_6ddf", "label": "Piezas separadas, revisión 2", "run": "run-6ddf07a4229b40949f5b8d1b1b128e31"},
    {"id": "piezas_c321", "label": "Piezas separadas, otra ejecución", "run": "run-c321bf839d8c4dda9e279b172c10992d"},
]
PDF_CASE = {"id": "pdf_raster", "label": "Tornillo de banco (PDF raster)", "run": "run-7267675e450042d7af5ad956fdc0593b",
            "preview": "documents/doc-586b1d861e3345678b2f3ed36698262c/1-preview.png"}
RECON_CASES = [
    {"id": "recon_mesa", "label": "Mesa de trabajo", "jobs": ["3894284a17bb46dbbcc0766766f4195a", "a174a6e50eab4111858b22f3b800d0f9"]},
    {"id": "recon_caso01", "label": "Mesa con bastidor", "jobs": ["00dbf06fac402177f21a35d2a2e31ecc"]},
    {"id": "recon_caso02", "label": "Estantería de tres huecos", "jobs": ["00ba57224b3b00a78fc9a2bbdb6f3405"]},
    {"id": "recon_caso03", "label": "Mueble bajo con dos huecos", "jobs": ["bf71e068fc4fe922fdfb1acb3c13d3d0"]},
    {"id": "recon_caso04", "label": "Escritorio con armario", "jobs": ["1e6593f569fecccdb2686854e8b0407e"]},
    {"id": "recon_caso05", "label": "Envolvente alta", "jobs": ["cd930a4a45e18ce6f37e681a5a6b4ec5"]},
    {"id": "recon_caso06", "label": "Mueble bajo con puerta", "jobs": ["1012f4bbc85cb4c4767ef50d33d28f1f"]},
    {"id": "recon_control", "label": "Mesa sin escala", "jobs": ["07f54e99bbf44b4ea75f4577f6fc5aba", "69f635e5a57b48c4b7856fa437bf6644"]},
]

PLANK_CASES = [
    {
        "id": "plank_030", "label": "Armario plank-030", "run": "run-9eb5e3aca8a04331ac0b0d3e5e2f2f40", "lane": "general",
        "notes": [
            "Ejecución recomendada de la demo guardada. El primer intento, incompleto (run-e6ab7332), no se incluye.",
            "Propuesta de gpt-6.1-sol y autorrevisión de gpt-6-astra, sin confirmación humana.",
        ],
    },
    {
        "id": "plank_016", "label": "Mueble plank-016", "run": "run-dbf758e4fbcd4b19bff8552201a48d4a", "lane": "general",
        "notes": ["Propuesta de gpt-6.1-sol y autorrevisión de gpt-6-astra, sin confirmación humana."],
    },
    {
        "id": "mesa_coste", "label": "Mesa con revisión y coste", "run": "run-161fc0b9bf7c46f499ddf84abe105d9b", "lane": "tabla",
        "notes": [
            "Vía de vistas montadas de mesa, sin modelo. La revisión la firma «Demo automatizada».",
            "Coste con las tarifas sintéticas del catálogo de la demo.",
        ],
    },
    {
        "id": "mesa_002", "label": "Mesa de dimensiones distintas", "run": "run-d5b7fce18fee4c699bc49a5110c75240", "lane": "tabla",
        "notes": ["Vía de vistas montadas de mesa, sin modelo. Sin láminas ni coste guardados en esta ejecución."],
    },
]

GENERAL_CASES = [
    {
        "id": "F02",
        "label": "Cajonera de tres cajones",
        "outcome": "F02.repaired.outcome.json",
        "evaluation": "F02.repaired.evaluation.json",
        "notes": [
            "Las guías de cajón quedan sin medida: el modelo se abstiene en largo, ancho y grueso.",
            "En la evaluación inicial (P1/R1), dos de las cinco cotas fallidas venían de intercambiar los ejes de la trasera; la P3 mostrada sigue con 16/21 cotas correctas y deja la trasera en ≈862×762×6 mm, estimada.",
            "Otra cota fallida de esa evaluación es el testero de 802 mm, que responde a una unión alternativa coherente con laterales de 18 mm.",
            "Los gruesos de las piezas ocultas se marcan como estimados.",
            "La propuesta P2 quedó en conflicto (polilínea de conjunto fuera de límites); la P3 revisada es la que se muestra.",
        ],
    },
    {
        "id": "F03",
        "label": "Estantería de cuatro baldas",
        "outcome": "F03.repaired.outcome.json",
        "evaluation": "F03.repaired.evaluation.json",
        "notes": [
            "El anclaje a pared con cuatro escuadras es una propuesta sin comprobación de la pared.",
            "Las cotas trasladadas a otras piezas se declaran estimadas; la referencia esperaba deducidas (2/9 bases coinciden).",
        ],
    },
    {
        "id": "F01",
        "label": "Mesa con bastidor",
        "outcome": "F01.outcome.json",
        "evaluation": "F01.evaluation.json",
        "notes": [
            "El grueso de los faldones es estimado (22 mm, rango 18-30 mm).",
            "El escenario no declara posiciones, así que no hay montaje 3D.",
        ],
    },
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def original(path: Path, filename: str) -> dict:
    """DXF de entrada tal cual. newline="" conserva los finales de línea del archivo."""
    with open(path, encoding="utf-8", errors="strict", newline="") as handle:
        content = handle.read()
    return {"filename": filename, "media_type": "application/dxf", "sha256": sha256(path), "content": content}


def unwrap(value):
    """Los exports HTTP guardan el sobre {schema_version, data}."""
    return value["data"] if isinstance(value, dict) and set(value) >= {"data", "schema_version"} else value


def events(path: Path) -> list[dict]:
    """events.json guarda payload como texto JSON; aquí queda con la forma de GET /events (data como objeto)."""
    out = []
    for item in read_json(path):
        payload = item.get("payload", item.get("data"))
        out.append({"sequence": item["sequence"], "event_type": item["event_type"], "data": json.loads(payload) if isinstance(payload, str) else payload})
    return out


def write(case_id: str, payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{case_id}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
    print(f"{target.name}: {target.stat().st_size // 1024} KB")


def build_general(case: dict) -> dict:
    dxf = CONTROLS / f"{case['id']}.dxf"
    outcome = read_json(RESULTS / case["outcome"])
    evaluation = read_json(RESULTS / case["evaluation"])
    if outcome["fixture"]["sha256"] != sha256(dxf):
        raise SystemExit(f"{case['id']}: el DXF no coincide con fixture.sha256 del outcome")
    drawing = extract_drawing(dxf, input_kind="general_furniture").model_dump(mode="json")
    package = outcome["derived"]["package"]
    job = outcome.get("job") or outcome.get("original_job")
    dims = evaluation["dimensions"]
    return {
        "schema": "vexplorer-caso-1",
        "id": case["id"],
        "label": case["label"],
        "lane": "general",
        "synthetic": True,
        "control_kind": evaluation.get("control_kind"),
        "sources": {
            "dxf": dxf.as_posix(),
            "dxf_sha256": outcome["fixture"]["sha256"],
            "outcome": (RESULTS / case["outcome"]).as_posix(),
            "evaluation": (RESULTS / case["evaluation"]).as_posix(),
            "doc": DOC_CAD,
        },
        "execution": {
            "job_id": job["id"] if job else None,
            "run_id": job["run_id"] if job else None,
            "job_state": job["state"] if job else None,
            **(outcome.get("execution") or {}),
            "proposal_revision": package["construction"]["proposal_revision"],
            "review_revision": package["construction"]["review_revision"],
        },
        "evaluation": {
            "utility_pass": evaluation["utility_pass"],
            "dimensions_correct": dims["correct"],
            "dimensions_basis_correct": dims["basis_correct"],
            "dimensions_required": dims["required"],
            "estimates_declared": evaluation["estimates"]["declared_with_range_and_premise"],
            "estimates_required": evaluation["estimates"]["required"],
            "piece_types_matched": evaluation["necessary_piece_types"]["matched"],
            "piece_types_required": evaluation["necessary_piece_types"]["required"],
            "unmatched_predicted_piece_types": evaluation["unmatched_predicted_piece_types"],
            "construction_missing": evaluation["construction_requirements"]["missing"],
            "server_validation": evaluation["closure"]["server_validation"],
            "limitations": evaluation["limitations"],
        },
        "notes": case["notes"],
        "drawing": drawing,
        "construction": package["construction"],
        "validation": outcome["latest"]["review"]["construction_validation"],
        "artifacts": [{k: v for k, v in a.items() if k != "content"} for a in package["artifacts"]],
        "original": original(dxf, dxf.name),
    }


def build_legacy(entry: dict, manifest: dict) -> dict:
    folder = DEMO / entry["id"]
    resultado = read_json(folder / "resultado.json")
    if resultado["result_revision"] != entry["result_revision"] or resultado["result"]["run_id"] != entry["run_id"]:
        raise SystemExit(f"{entry['id']}: resultado.json no coincide con el manifest")
    return {
        "schema": "vexplorer-caso-1",
        "id": entry["id"],
        "label": entry["label"],
        "lane": "legacy",
        "synthetic": bool(manifest.get("synthetic", True)),
        "control_kind": "processed_demo_fixture",
        "sources": {
            "dxf": (folder / "fuente.dxf").as_posix(),
            "dxf_sha256": sha256(folder / "fuente.dxf"),
            "drawing": (folder / "drawing.json").as_posix(),
            "resultado": (folder / "resultado.json").as_posix(),
            "doc": "docs/DEMO_DATOS_PROCESADOS.md",
        },
        "execution": {
            "run_id": entry["run_id"],
            "mode": manifest.get("mode"),
            "result_revision": entry["result_revision"],
            "state": entry["state"],
        },
        "notes": [
            "Fixture propio sintético procesado sin modelo (geometry_only); revisión y tarifas de ensayo.",
            *(["Sin piezas resueltas: el grueso no está en el plano y el caso sigue en revisión."] if entry["state"] == "needs_review" else []),
        ],
        "drawing": read_json(folder / "drawing.json"),
        "result": resultado["result"],
        "scene": resultado["scene"],
        "explanations": resultado.get("explanations"),
        "estimate": resultado.get("estimate"),
        "original": original(folder / "fuente.dxf", Path(entry["source"]).name),
    }


def build_plank(case: dict) -> dict:
    folder = PLANK / "runs" / case["run"]
    run = unwrap(read_json(folder / "run.json"))
    document = unwrap(read_json(folder / "document.json"))
    source = folder / "source.dxf"
    if document["sha256"] != sha256(source):
        raise SystemExit(f"{case['id']}: source.dxf no coincide con document.json")
    base = {
        "schema": "vexplorer-caso-1",
        "id": case["id"],
        "label": case["label"],
        "lane": case["lane"],
        "synthetic": False,
        "control_kind": "plank_pipeline_demo",
        "attribution": PLANK_ATTRIBUTION if case["lane"] == "general" else None,
        "sources": {
            "run": folder.as_posix(),
            "readme": (PLANK / "README.md").as_posix(),
            "doc": "docs/PLANKASSEMBLY.md" if case["lane"] == "general" else (PLANK / "README.md").as_posix(),
        },
        "execution": {
            "run_id": case["run"], "mode": run["run"]["mode"], "input_kind": run["run"]["input_kind"],
            "state": run["run"]["state"], "result_revision": run["run"]["result_revision"],
        },
        "notes": case["notes"],
        "drawing": unwrap(read_json(folder / "drawing.json")),
        "events": events(folder / "events.json"),
        "original": original(source, document["original_filename"]),
    }
    if case["lane"] == "general":
        record = unwrap(read_json(folder / "general.json"))
        base["execution"].update({"proposal_revision": record["proposal_revision"], "review_revision": record["review_revision"]})
        return {**base, "record": record, "derived": unwrap(read_json(folder / "derived.json")), "assembly": read_json(folder / "assembly.json")}
    revision = run["run"]["result_revision"]
    manifest = unwrap(read_json(folder / "table-drawings.json")) if (folder / "table-drawings.json").exists() else None
    for sheet in (manifest or {}).get("sheets", []):
        for fmt in sheet["formats"]:
            path = folder / "table-artifacts" / f"r{sheet['result_revision']}" / f"{sheet['sheet_id']}-r{sheet['result_revision']}.{fmt['format']}"
            with open(path, encoding="utf-8", newline="") as handle:
                fmt["content"] = handle.read()
            fmt["filename"] = path.name
    return {
        **base,
        "run": run["run"], "result": run["result"],
        "table": unwrap(read_json(folder / "table.json")),
        "scene": unwrap(read_json(folder / "scene.json")),
        "table_drawings": manifest,
        "table_costs": unwrap(read_json(folder / "table-costs.json")) if (folder / "table-costs.json").exists() else None,
        "result_revision": revision,
    }


def build_recon(case: dict) -> dict:
    import shutil
    jobs = []
    for job_id in case["jobs"]:
        folder = FULL / "reconstruction" / job_id
        status = read_json(folder / "status.json")
        outcome = status.get("outcome") or {}
        target = LOCAL / job_id
        target.mkdir(parents=True, exist_ok=True)
        art = folder / "artifacts"
        copiados = ["source.png", "artifacts/assembly.glb", "artifacts/exploded.png", "artifacts/bom.csv",
                    *[f"artifacts/{f.name}" for f in sorted(art.glob("view-*.png"))], *[f"artifacts/{f.name}" for f in sorted(art.glob("mask-*.png"))]]
        for name in copiados:
            if (folder / name).exists():
                shutil.copyfile(folder / name, target / Path(name).name)
        (target / "parts").mkdir(exist_ok=True)
        for svg in sorted((art / "parts").glob("*.svg")) if (art / "parts").exists() else []:
            shutil.copyfile(svg, target / "parts" / svg.name)
        import base64
        import csv
        media = {}
        for name in copiados:
            ruta = folder / name
            if ruta.exists():
                tipo = "model/gltf-binary" if ruta.suffix == ".glb" else "image/png" if ruta.suffix == ".png" else "text/csv"
                media[ruta.name] = f"data:{tipo};base64,{base64.b64encode(ruta.read_bytes()).decode('ascii')}"
        bom = []
        if (art / "bom.csv").exists():
            with open(art / "bom.csv", encoding="utf-8", newline="") as handle:
                bom = list(csv.DictReader(handle))
        jobs.append({
            "job_id": job_id,
            "run_id": status.get("run_id"),
            "status": status.get("status"),
            "revision": status.get("revision") or 1,
            "parent_job_id": status.get("parent_job_id"),
            "unit": status.get("unit"),
            "intended_use_from_user": status.get("intended_use_from_user"),
            "geometry_provenance": "generated_design_hypothesis",
            "proposal": outcome.get("proposal"),
            "checks": outcome.get("checks"),
            "has_glb": (folder / "artifacts" / "assembly.glb").exists(),
            "models": sorted({t.get("model") for t in outcome.get("trace", []) if t.get("model")}),
            "source_sha256": sha256(folder / "source.png") if (folder / "source.png").exists() else None,
            "files": {
                "views": [f.name for f in sorted(art.glob("view-*.png"))],
                "masks": [f.name for f in sorted(art.glob("mask-*.png"))],
                "exploded": "exploded.png" if (art / "exploded.png").exists() else None,
                "bom": "bom.csv" if (art / "bom.csv").exists() else None,
                "parts": [f"parts/{f.name}" for f in sorted((art / "parts").glob("*.svg"))] if (art / "parts").exists() else [],
            },
            "bom_rows": bom,
            # Los archivos del pipeline viajan con el caso: funcionan también en el HTML de un solo archivo.
            "media": media,
            "glb_sha256": sha256(folder / "artifacts" / "assembly.glb") if (folder / "artifacts" / "assembly.glb").exists() else None,
        })
    return {
        "schema": "vexplorer-caso-1",
        "id": case["id"],
        "label": case["label"],
        "lane": "reconstruccion",
        "synthetic": False,
        "control_kind": "full_app_demo_reconstruction",
        "sources": {"jobs": ", ".join(case["jobs"]), "readme": (FULL / "README.md").as_posix(), "doc": "docs/RECONSTRUCCION_3D_RESULTADOS.md"},
        "execution": {"run_id": jobs[0]["run_id"], "jobs": case["jobs"]},
        "notes": [],
        "jobs": jobs,
    }


def build_parts(case: dict) -> dict:
    folder = FULL / "runs" / case["run"]
    export = unwrap(read_json(folder / "export.json"))
    return {
        "schema": "vexplorer-caso-1", "id": case["id"], "label": case["label"], "lane": "legacy", "synthetic": True,
        "control_kind": "full_app_demo_parts", "sources": {"run": folder.as_posix(), "readme": (FULL / "README.md").as_posix()},
        "execution": {"run_id": case["run"], "result_revision": export["result_revision"]},
        "notes": ["Vía de piezas separadas, revisada; fixture propio sintético."],
        "drawing": unwrap(read_json(folder / "drawing.json")),
        "result": export["result"], "scene": export["scene"], "explanations": export.get("explanations"), "estimate": None,
    }


def build_pdf(case: dict) -> dict:
    import shutil
    folder = FULL / "runs" / case["run"]
    target = HERE.parent / "public" / "local" / "documentos"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FULL / case["preview"], target / f"{case['id']}.png")
    record = unwrap(read_json(folder / "general.json"))
    return {
        "schema": "vexplorer-caso-1", "id": case["id"], "label": case["label"], "lane": "general", "synthetic": False,
        "control_kind": "full_app_demo_pdf_raster", "sources": {"run": folder.as_posix(), "readme": (FULL / "README.md").as_posix()},
        "execution": {"run_id": case["run"], "proposal_revision": record["proposal_revision"], "review_revision": record["review_revision"]},
        "notes": ["PDF raster sin geometría métrica: la propuesta parte de la imagen de la página."],
        "drawing": None, "record": record, "preview": f"./local/documentos/{case['id']}.png",
    }


def main() -> None:
    index = []
    for case in PARTS_CASES:
        payload = build_parts(case)
        write(case["id"], payload)
        index.append(payload["id"])
    payload = build_pdf(PDF_CASE)
    write(PDF_CASE["id"], payload)
    index.append(payload["id"])
    for case in RECON_CASES:
        payload = build_recon(case)
        write(case["id"], payload)
        index.append(payload["id"])
    for case in PLANK_CASES:
        payload = build_plank(case)
        write(case["id"], payload)
        index.append(payload["id"])
    for case in GENERAL_CASES:
        payload = build_general(case)
        write(case["id"], payload)
        index.append(payload["id"])
    manifest = read_json(DEMO / "manifest.json")
    for entry in manifest["cases"]:
        payload = build_legacy(entry, manifest)
        write(entry["id"], payload)
        index.append(payload["id"])
    print("casos:", ", ".join(index))


main()
