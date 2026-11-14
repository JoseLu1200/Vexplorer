"""Genera src/api/general.gen.ts desde los modelos Pydantic reales de Vexplorer.

Solo lee el repo de Vexplorer: importa los modelos y llama a model_json_schema().
Uso (desde cualquier carpeta):

    C:/Users/marti/Proyectos/Vexplorer/.venv/Scripts/python.exe -B scripts/gen_general_types.py [ruta-vexplorer]

Reglas de emisión:
- Las clases alcanzables desde una respuesta se emiten en modo serialización y con todos los
  campos obligatorios, porque model_dump() los devuelve siempre.
- Las clases que solo aparecen en peticiones se emiten en modo validación: un campo con valor
  por defecto queda opcional.
- Las tuplas Python se emiten como arrays; bytes como string (pydantic serializa en utf8).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "src" / "api" / "general.gen.ts"
VEXPLORER = Path(sys.argv[1] if len(sys.argv) > 1 else "C:/Users/marti/Proyectos/Vexplorer").resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(VEXPLORER))
os.chdir(VEXPLORER)

from pydantic import BaseModel  # noqa: E402
from pydantic.json_schema import models_json_schema  # noqa: E402

from backend.app.contratos import modelos as M  # noqa: E402
from backend.app.reconstruction3d import models as R  # noqa: E402
from backend.app.reconstruction3d.router import ReconstructionRequest  # noqa: E402

RESPONSE_ROOTS: list[type[BaseModel]] = [
    M.GeneralFurnitureEnvelope,
    M.GeneralDerivedEnvelope,
    M.GeneralAssemblyState,
    M.DrawingExtraction,
    M.ReconstructionScene,
    R.AssemblyProposal,
]
REQUEST_ROOTS: list[type[BaseModel]] = [
    M.RunRequest,
    M.GeneralProposalRequest,
    M.GeneralFurnitureReviewRequest,
    M.GeneralAutoReviewRequest,
    ReconstructionRequest,
    R.RefinementRequest,
]


def collect(roots, mode):
    _, schema = models_json_schema([(m, mode) for m in roots], ref_template="#/$defs/{model}")
    return schema.get("$defs", {})


resp_defs = collect(RESPONSE_ROOTS, "serialization")
req_defs = collect(REQUEST_ROOTS, "validation")


def ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def ts(node: dict, optional_defaults: bool) -> str:
    if "$ref" in node:
        return ref_name(node["$ref"])
    if "allOf" in node and len(node["allOf"]) == 1:
        return ts(node["allOf"][0], optional_defaults)
    if "anyOf" in node or "oneOf" in node:
        parts = [ts(item, optional_defaults) for item in node.get("anyOf", node.get("oneOf", []))]
        seen: list[str] = []
        for part in parts:
            if part not in seen:
                seen.append(part)
        return " | ".join(seen)
    if "const" in node:
        return json.dumps(node["const"], ensure_ascii=False)
    if "enum" in node:
        return " | ".join(json.dumps(v, ensure_ascii=False) for v in node["enum"])
    kind = node.get("type")
    if isinstance(kind, list):
        return " | ".join(ts({**node, "type": k}, optional_defaults) for k in kind)
    if kind == "string":
        return "string"
    if kind in ("number", "integer"):
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "null":
        return "null"
    if kind == "array":
        if "prefixItems" in node:
            return "[" + ", ".join(ts(i, optional_defaults) for i in node["prefixItems"]) + "]"
        item = ts(node.get("items", {}), optional_defaults)
        return f"({item})[]" if "|" in item else f"{item}[]"
    if kind == "object":
        if "properties" in node:
            return inline_object(node, optional_defaults)
        extra = node.get("additionalProperties")
        value = ts(extra, optional_defaults) if isinstance(extra, dict) else "unknown"
        return f"Record<string, {value}>"
    return "unknown"


def inline_object(node: dict, optional_defaults: bool) -> str:
    required = set(node.get("required", []))
    fields = []
    for name, prop in node.get("properties", {}).items():
        opt = optional_defaults and name not in required
        fields.append(f"{name}{'?' if opt else ''}: {ts(prop, optional_defaults)}")
    return "{ " + "; ".join(fields) + " }"


def emit(name: str, node: dict, optional_defaults: bool) -> str:
    doc = (node.get("description") or "").strip().splitlines()
    head = f"/** {name}{' · ' + doc[0][:160] if doc else ''} */\n"
    if node.get("type") == "object" and "properties" in node:
        required = set(node.get("required", []))
        lines = []
        for field, prop in node["properties"].items():
            opt = optional_defaults and field not in required
            lines.append(f"  {field}{'?' if opt else ''}: {ts(prop, optional_defaults)};")
        return head + f"export interface {name} {{\n" + "\n".join(lines) + "\n}\n"
    return head + f"export type {name} = {ts(node, optional_defaults)};\n"


chunks = [
    "/* Archivo generado por scripts/gen_general_types.py. No editar a mano. */\n"
    "/* Fuente: backend/app/contratos/modelos.py y backend/app/reconstruction3d de Vexplorer. */\n"
    "/* Respuestas en modo serialización (todos los campos presentes); peticiones en modo validación. */\n"
]
emitted = set()
for name in sorted(resp_defs):
    chunks.append(emit(name, resp_defs[name], optional_defaults=False))
    emitted.add(name)
for name in sorted(req_defs):
    if name in emitted:
        continue
    chunks.append(emit(name, req_defs[name], optional_defaults=True))
    emitted.add(name)

OUT.write_text("\n".join(chunks), encoding="utf-8", newline="\n")
print(f"{OUT}: {len(emitted)} tipos")
