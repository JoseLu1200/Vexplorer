"""Genera public/local/raros/ (ignorado por git) con los muebles raros de PlankAssembly sin procesar.

Solo para uso local por licencia (CC BY-NC-ND 4.0): no se versionan ni se publican. Solo lee Vexplorer.

    C:/Users/marti/Proyectos/Vexplorer/.venv/Scripts/python.exe -B scripts/build_raros.py [ruta-vexplorer]

Salida:
    index.json       [{id, titulo, piezas, tipos, medidas_mm: {ancho, fondo, alto}}]
    <id>.json        {id, drawing}: DrawingExtraction de extract_drawing(<id>.dxf, "general_furniture").
Las cajas `planks` de seleccion.json son la referencia del dataset, no un resultado: no se exportan.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "public" / "local" / "raros"
VEXPLORER = Path(sys.argv[1] if len(sys.argv) > 1 else "C:/Users/marti/Proyectos/Vexplorer").resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(VEXPLORER))
os.chdir(VEXPLORER)

from backend.app.geometria.extraction import extract_drawing  # noqa: E402

SRC = Path(".runtime/plank-raros")


def main() -> None:
    seleccion = json.loads((SRC / "seleccion.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for n, item in enumerate(seleccion, start=1):
        dxf = SRC / f"{item['id']}.dxf"
        if not dxf.exists():
            continue
        drawing = extract_drawing(dxf, input_kind="general_furniture").model_dump(mode="json")
        (OUT / f"{item['id']}.json").write_text(json.dumps({"id": item["id"], "drawing": drawing}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        index.append({
            "id": item["id"], "titulo": f"PlankAssembly {n:02d}", "piezas": item.get("piezas"), "tipos": item.get("tipos"),
            "medidas_mm": {"ancho": item.get("W"), "fondo": item.get("D"), "alto": item.get("H")},
        })
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(index)} raros en {OUT}")


main()
