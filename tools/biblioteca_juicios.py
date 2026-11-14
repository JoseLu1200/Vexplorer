"""Construye la biblioteca de ``LibraryItem`` que ``tools.evaluar_recuperacion`` espera para un archivo de juicios.

    python -m tools.biblioteca_juicios --privado <priv> --publico <pub> \\
        --juicios juicios_test.json --descriptores descriptores.json --salida biblioteca.json

Combina tres entradas:

* ``<priv>/juicios/bibliotecas.json``: solo ids (``case_ids`` y ``run_id_overrides`` por archivo de
  juicios). Es lo único privado que se abre; ``references.json`` nunca se lee.
* ``<pub>/cases.json``: los ids deben existir en el corpus público.
* ``--descriptores``: JSON ``{id_de_caso: descriptor}`` (modelos ``furniture-v1/v2/v3`` de
  ``contratos``) **construido a partir de las vistas públicas**. Esta herramienta no extrae
  descriptores: hoy no existe un extractor de descriptores para las vistas ortográficas ensambladas
  (``build_descriptor`` consume un ``Result`` de estantería y la regla A2 del arnés solo propone
  hipótesis rectangulares). Hasta que exista, el operador aporta ese archivo; ver
  ``docs/PLANKASSEMBLY.md``. Por defensa, se rechaza un archivo de descriptores situado dentro del
  directorio privado.

Salida: ``LibraryItem`` con ``id`` = id del caso, ``run_id = run_id_overrides.get(id, id)``, un único
``descriptor_version`` y exactamente los ``case_ids`` del archivo. No es un resultado de inferencia.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

from backend.app.contratos.modelos import LibraryItem
from backend.app.semantic.descriptor import descriptor_fingerprint

CREATED_AT = "1970-01-01T00:00:00+00:00"  # fijo: la salida es determinista


def _json(path: Path, etiqueta: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"no se puede leer {etiqueta}: {error}") from error


def _dentro_de(ruta: Path, carpeta: Path) -> bool:
    ruta, carpeta = ruta.resolve(), carpeta.resolve()
    return ruta == carpeta or carpeta in ruta.parents


def construir_biblioteca(
    privado: Path,
    publico: Path,
    archivo_juicios: str,
    descriptores: Mapping[str, object],
) -> tuple[LibraryItem, ...]:
    """Valida y construye la biblioteca de un archivo de juicios (ver el módulo)."""
    bibliotecas = _json(privado / "juicios" / "bibliotecas.json", "juicios/bibliotecas.json")
    if not isinstance(bibliotecas, dict) or archivo_juicios not in bibliotecas:
        conocidos = sorted(bibliotecas) if isinstance(bibliotecas, dict) else []
        raise ValueError(f"'{archivo_juicios}' no figura en bibliotecas.json (conocidos: {conocidos})")
    contrato = bibliotecas[archivo_juicios]
    if not isinstance(contrato, dict) or not isinstance(contrato.get("case_ids"), list):
        raise TypeError("entrada de bibliotecas.json malformada")
    case_ids: list[str] = contrato["case_ids"]
    overrides = contrato.get("run_id_overrides") or {}
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("case_ids duplicados en bibliotecas.json")
    if not set(overrides) <= set(case_ids):
        raise ValueError("run_id_overrides referencia ids que no están en case_ids")

    filas = _json(publico / "cases.json", "cases.json público")
    publicos = {fila.get("id") for fila in filas if isinstance(fila, dict)} if isinstance(filas, list) else set()
    ausentes_publico = sorted(set(case_ids) - publicos)
    if ausentes_publico:
        raise ValueError(f"ids de la biblioteca ausentes del corpus público: {ausentes_publico[:5]}")

    faltan = sorted(set(case_ids) - set(descriptores))
    sobran = sorted(set(descriptores) - set(case_ids))
    if faltan or sobran:
        raise ValueError(f"los descriptores no coinciden con case_ids (faltan {faltan[:5]}, sobran {sobran[:5]})")

    items: list[LibraryItem] = []
    for case_id in sorted(case_ids):
        probe = LibraryItem.model_validate({
            "id": case_id, "run_id": overrides.get(case_id, case_id), "result_revision": 1, "label": case_id,
            "descriptor": descriptores[case_id], "descriptor_fingerprint": "0" * 64, "created_at": CREATED_AT,
        })
        items.append(probe.model_copy(update={"descriptor_fingerprint": descriptor_fingerprint(probe.descriptor)}))
    versiones = {item.descriptor.descriptor_version for item in items}
    if len(versiones) > 1:
        raise ValueError(f"la biblioteca debe usar un único descriptor_version, hay {sorted(versiones)}")
    return tuple(items)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--privado", type=Path, required=True, help="directorio privado del corpus (solo juicios/bibliotecas.json)")
    parser.add_argument("--publico", type=Path, required=True, help="directorio público del corpus")
    parser.add_argument("--juicios", required=True, help="nombre del archivo de juicios, p. ej. juicios_test.json")
    parser.add_argument("--descriptores", type=Path, required=True, help="JSON {id: descriptor} construido desde las vistas públicas")
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if _dentro_de(args.descriptores, args.privado):
            raise ValueError("el archivo de descriptores no puede estar dentro del directorio privado")
        descriptores = _json(args.descriptores, "descriptores")
        if not isinstance(descriptores, dict):
            raise TypeError("--descriptores debe ser un objeto {id: descriptor}")
        biblioteca = construir_biblioteca(args.privado, args.publico, args.juicios, descriptores)
    except (ValueError, TypeError) as error:  # incluye ValidationError de Pydantic
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(
        json.dumps([item.model_dump(mode="json") for item in biblioteca], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
