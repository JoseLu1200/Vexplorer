"""Genera src/lib/caso.ts con el caso F02 (cajonera) a partir de origin/main del repo Vexplorer.

Uso, desde la raíz del worktree:  python -I scripts/caso_f02.py [ruta-al-repo-Vexplorer]

- Geometría: data/cad_completion_controls/public/F02.dxf, leído con un lector propio de pares de códigos DXF.
- Despiece: evaluation/results/cad_completion_live_2026-11-14/F02.repaired.outcome.json, en derived.package.construction.
- Precio: misma lógica que backend/app/estimacion/table_costs.py con el catálogo de demo de cost_catalog.py
  (preparación fija una vez, superficie × tarifa por componente, redondeo a céntimos half-up por línea).
"""
from __future__ import annotations

import json
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[4] / "Vexplorer"
REF = "origin/main"
DXF_PATH = "data/cad_completion_controls/public/F02.dxf"
OUTCOME_PATH = "evaluation/results/cad_completion_live_2026-11-14/F02.repaired.outcome.json"
OUT = Path(__file__).resolve().parents[1] / "src" / "lib" / "caso.ts"

# Catálogo de demo de backend/app/estimacion/cost_catalog.py (synthetic-table-costs-2026-11-14).
TARIFA_TABLERO = 42.0  # demo_board_area_v1, EUR/m2
PREPARACION = 25.0  # demo_preparation_fixed_v1, EUR/unit


def show(path: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), "show", f"{REF}:{path}"], capture_output=True, check=True).stdout.decode("utf-8")


def money(v: float) -> float:
    return float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def quantity(v: float) -> float:
    return float(Decimal(str(v)).quantize(Decimal("0.000000001")))


# ---------- DXF ----------

def pairs(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    return [(lines[i].strip(), lines[i + 1].strip()) for i in range(0, len(lines) - 1, 2)]


def sections(pp: list[tuple[str, str]]) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    i = 0
    while i < len(pp):
        if pp[i] == ("0", "SECTION"):
            name = pp[i + 1][1]
            j = i + 2
            while pp[j] != ("0", "ENDSEC"):
                j += 1
            out[name] = pp[i + 2 : j]
            i = j
        i += 1
    return out


def records(pp: list[tuple[str, str]]) -> list[tuple[str, list[tuple[str, str]]]]:
    recs: list[tuple[str, list[tuple[str, str]]]] = []
    for c, v in pp:
        if c == "0":
            recs.append((v, []))
        elif recs:
            recs[-1][1].append((c, v))
    return recs


def first(codes: list[tuple[str, str]], code: str, default: str | None = None) -> str | None:
    return next((v for c, v in codes if c == code), default)


def r(v: str | float) -> float:
    return round(float(v), 3)


def parse_entity(kind: str, codes: list[tuple[str, str]]) -> dict | None:
    layer = first(codes, "8")
    handle = first(codes, "5")
    if kind == "LWPOLYLINE":
        xs = [r(v) for c, v in codes if c == "10"]
        ys = [r(v) for c, v in codes if c == "20"]
        return {"h": handle, "layer": layer, "kind": "poly", "pts": list(zip(xs, ys)), "closed": int(first(codes, "70", "0")) & 1 == 1}
    if kind == "LINE":
        return {"h": handle, "layer": layer, "kind": "line", "pts": [(r(first(codes, "10")), r(first(codes, "20"))), (r(first(codes, "11")), r(first(codes, "21")))], "closed": False}
    if kind in ("TEXT", "MTEXT"):
        return {"h": handle, "layer": layer, "kind": "text", "x": r(first(codes, "10")), "y": r(first(codes, "20")), "height": r(first(codes, "40", "1")), "rot": r(first(codes, "50", "0")), "text": first(codes, "1")}
    if kind == "POINT":
        return {"h": handle, "layer": layer, "kind": "point", "x": r(first(codes, "10")), "y": r(first(codes, "20"))}
    if kind == "INSERT":
        return {"h": handle, "layer": layer, "kind": "arrow", "x": r(first(codes, "10")), "y": r(first(codes, "20")), "scale": r(first(codes, "41", "1")), "rot": r(first(codes, "50", "0"))}
    return None


def parse_dxf(text: str) -> dict:
    sec = sections(pairs(text))
    layers = {}
    for kind, codes in records(sec["TABLES"]):
        if kind == "LAYER" and first(codes, "2"):
            layers[first(codes, "2")] = {"aci": int(first(codes, "62", "7")), "ltype": first(codes, "6", "Continuous")}
    blocks: dict[str, list[dict]] = {}
    current = None
    for kind, codes in records(sec["BLOCKS"]):
        if kind == "BLOCK":
            current = first(codes, "2")
            blocks[current] = []
        elif kind == "ENDBLK":
            current = None
        elif current is not None:
            ent = parse_entity(kind, codes)
            if ent:
                blocks[current].append(ent)
    entities = []
    dims = []
    for kind, codes in records(sec["ENTITIES"]):
        if kind == "DIMENSION":
            block = first(codes, "2")
            dims.append({
                "h": first(codes, "5"),
                "layer": first(codes, "8"),
                "block": block,
                # Puntos de definición de la cota: extremos medidos (13/23 y 14/24) y línea de cota (10/20).
                "p1": (r(first(codes, "13")), r(first(codes, "23"))),
                "p2": (r(first(codes, "14")), r(first(codes, "24"))),
                "at": (r(first(codes, "10")), r(first(codes, "20"))),
                "rot": r(first(codes, "50", "0")),
                "parts": blocks.get(block, []),
            })
            continue
        ent = parse_entity(kind, codes)
        if ent:
            entities.append(ent)
    return {"layers": layers, "entities": entities, "dims": dims}


# ---------- despiece y precio ----------

NOMBRES = {
    "costados": "Costado",
    "horizontales": "Tapa y base",
    "frentes": "Frente",
    "trasera": "Trasera",
    "caja_lados": "Lado de cajón",
    "caja_testeros": "Testero de cajón",
    "caja_fondos": "Fondo de cajón",
    "guias": "Juego de guías",
}


def campo(f: dict | None) -> dict:
    if not f or f.get("value_mm") is None:
        return {"v": None, "est": False, "min": None, "max": None, "state": (f or {}).get("state", "unknown")}
    rng = f.get("range_mm") or {}
    return {"v": f["value_mm"], "est": f["state"] == "estimated", "min": rng.get("min_mm"), "max": rng.get("max_mm"), "state": f["state"]}


def build_pieces(outcome: dict) -> tuple[list[dict], dict]:
    cons = outcome["derived"]["package"]["construction"]
    pieces = []
    for p in cons["pieces"]:
        q = p["quantity"]
        L, Wd, T = campo(p.get("length")), campo(p.get("width")), campo(p.get("thickness"))
        area = amount = None
        if L["v"] is not None and Wd["v"] is not None:
            area = quantity(L["v"] * Wd["v"] * q["value"] / 1_000_000)
            amount = money(area * TARIFA_TABLERO)
        pieces.append({
            "id": p["piece_id"],
            "nombre": NOMBRES[p["piece_id"]],
            "etiqueta": p["label"],
            "cantidad": q["value"],
            "cantidadEstado": q["state"],
            "largo": L,
            "ancho": Wd,
            "grosor": T,
            "contornos": (p.get("geometry") or {}).get("source_contour_ids", []),
            "areaM2": area,
            "importe": amount,
            "importeEstimado": amount is not None and (L["est"] or Wd["est"]),
        })
    tableros = [p for p in pieces if p["importe"] is not None]
    # Como known_subtotal_eur: suma de las líneas ya redondeadas (preparación + tablero por componente).
    subtotal = money(float(Decimal(str(PREPARACION)) + sum(Decimal(str(p["importe"])) for p in tableros)))
    resumen = {
        "preparacion": money(PREPARACION),
        "tarifaTablero": TARIFA_TABLERO,
        "tableroTotal": money(float(sum(Decimal(str(p["importe"])) for p in tableros))),
        "subtotal": subtotal,
        "subtotalEstimado": any(p["importeEstimado"] for p in tableros),
        "piezasTablero": sum(p["cantidad"] for p in tableros),
        "catalogo": "synthetic-table-costs-2026-11-14",
        "estado": cons["summary"].get("label"),
        "authority": cons.get("authority"),
    }
    return pieces, resumen


def main() -> None:
    dxf = parse_dxf(show(DXF_PATH))
    outcome = json.loads(show(OUTCOME_PATH))
    pieces, resumen = build_pieces(outcome)
    assert resumen["piezasTablero"] == 23, resumen
    head = (
        "// Generado por scripts/caso_f02.py desde origin/main del repo Vexplorer. No editar a mano.\n"
        f"// DXF: {DXF_PATH}\n// Despiece: {OUTCOME_PATH} (derived.package.construction)\n"
        "// Precio: lógica de backend/app/estimacion/table_costs.py con el catálogo de demo (tarifas sintéticas).\n\n"
    )
    types = """export type Pt = [number, number]
export interface DxfEnt { h: string; layer: string; kind: 'poly' | 'line' | 'text' | 'point' | 'arrow'; pts?: Pt[]; closed?: boolean; x?: number; y?: number; height?: number; rot?: number; text?: string; scale?: number }
export interface DxfDim { h: string; layer: string; block: string; p1: Pt; p2: Pt; at: Pt; rot: number; parts: DxfEnt[] }
export interface Campo { v: number | null; est: boolean; min: number | null; max: number | null; state: string }
export interface PiezaCaso { id: string; nombre: string; etiqueta: string; cantidad: number; cantidadEstado: string; largo: Campo; ancho: Campo; grosor: Campo; contornos: string[]; areaM2: number | null; importe: number | null; importeEstimado: boolean }

"""
    body = (
        f"export const DXF: {{ layers: Record<string, {{ aci: number; ltype: string }}>; entities: DxfEnt[]; dims: DxfDim[] }} = {json.dumps(dxf, ensure_ascii=False)}\n\n"
        f"export const PIEZAS: PiezaCaso[] = {json.dumps(pieces, ensure_ascii=False, indent=1)}\n\n"
        f"export const RESUMEN = {json.dumps(resumen, ensure_ascii=False, indent=1)} as const\n"
    )
    OUT.write_text(head + types + body, encoding="utf-8", newline="\n")
    print("ok", OUT, "subtotal", resumen["subtotal"], "tablero", resumen["tableroTotal"])
    for p in pieces:
        print(p["id"], p["cantidad"], p["largo"]["v"], p["ancho"]["v"], p["grosor"]["v"], p["areaM2"], p["importe"], "est" if p["importeEstimado"] else "")


if __name__ == "__main__":
    main()
