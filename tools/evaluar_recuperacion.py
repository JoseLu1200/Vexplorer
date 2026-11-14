"""Evalúa la recuperación de precedentes contra juicios graduados (idea 2.7).

Uso:
    python -m tools.evaluar_recuperacion --biblioteca export.json --juicios juicios.json --k 5

``--biblioteca`` es un JSON con una lista de ``LibraryItem`` o ``{"items": [...]}``.
Imprime las métricas en JSON por la salida estándar. Un conjunto ``synthetic`` solo
prueba el mecanismo: sus cifras no son evidencia de calidad.

Punto de extensión: para añadir otro método (p. ej. ``hibrido``, idea 2.3), registra en
``METODOS`` una función ``Ranqueador`` que reciba la consulta y los candidatos ya
filtrados y devuelva ``(id, score)`` sin ordenar. El orden final (score descendente,
empate por id) y las exclusiones son comunes a todos los métodos.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from backend.app.contratos.modelos import LibraryItem
from backend.app.precedentes.comun import ModeloEstricto
from backend.app.precedentes.evaluacion import (
    ConjuntoJuicios,
    MetricasAgregadas,
    MetricasConsulta,
    agregar,
    evaluar_consulta,
)
from backend.app.similarity.service import geometric_match

Ranqueador = Callable[[LibraryItem, tuple[LibraryItem, ...]], tuple[tuple[str, float], ...]]


def ranquear_geometrico(consulta: LibraryItem, candidatos: tuple[LibraryItem, ...]) -> tuple[tuple[str, float], ...]:
    return tuple((item.id, geometric_match(consulta.descriptor, item).score) for item in candidatos)


METODOS: dict[str, Ranqueador] = {"geometrico": ranquear_geometrico}


class ExclusionesConsulta(ModeloEstricto):
    consulta_id: str
    misma_consulta: int
    mismo_run: int
    version_descriptor_distinta: int


class InformeRecuperacion(ModeloEstricto):
    metodo: str
    origen_juicios: str
    version_juicios: str
    aviso: str | None
    agregadas: MetricasAgregadas
    por_consulta: tuple[MetricasConsulta, ...]
    exclusiones: tuple[ExclusionesConsulta, ...]
    advertencias: tuple[str, ...]


def cargar_biblioteca(ruta: Path) -> tuple[LibraryItem, ...]:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if isinstance(datos, dict):
        datos = datos.get("items")
    if not isinstance(datos, list):
        raise TypeError("la biblioteca debe ser una lista o un objeto con 'items'")
    items = tuple(LibraryItem.model_validate(item) for item in datos)
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("ids duplicados en la biblioteca")
    return tuple(sorted(items, key=lambda item: item.id))


def ranking_consulta(consulta: LibraryItem, biblioteca: tuple[LibraryItem, ...], ranqueador: Ranqueador) -> tuple[tuple[str, ...], ExclusionesConsulta]:
    """Excluye la propia consulta, el mismo run y otras versiones de descriptor; ordena por (-score, id)."""
    misma = mismo_run = version = 0
    candidatos: list[LibraryItem] = []
    for item in biblioteca:
        if item.id == consulta.id:
            misma += 1
        elif item.run_id == consulta.run_id:
            mismo_run += 1
        elif item.descriptor.descriptor_version != consulta.descriptor.descriptor_version:
            version += 1
        else:
            candidatos.append(item)
    puntuados = sorted(ranqueador(consulta, tuple(candidatos)), key=lambda par: (-par[1], par[0]))
    exclusiones = ExclusionesConsulta(consulta_id=consulta.id, misma_consulta=misma, mismo_run=mismo_run, version_descriptor_distinta=version)
    return tuple(item_id for item_id, _ in puntuados), exclusiones


def evaluar(biblioteca: tuple[LibraryItem, ...], juicios: ConjuntoJuicios, k: int, metodo: str) -> InformeRecuperacion:
    ranqueador = METODOS[metodo]
    por_id = {item.id: item for item in biblioteca}
    metricas: list[MetricasConsulta] = []
    exclusiones: list[ExclusionesConsulta] = []
    advertencias: list[str] = []
    for consulta in sorted(juicios.consultas, key=lambda item: item.consulta_id):
        item = por_id.get(consulta.consulta_id)
        if item is None:
            advertencias.append(f"consulta '{consulta.consulta_id}' ausente en la biblioteca; se omite")
            continue
        ausentes = sorted(candidato for candidato in consulta.relevancias if candidato not in por_id)
        if ausentes:
            advertencias.append(f"consulta '{consulta.consulta_id}': candidatos juzgados ausentes en la biblioteca {ausentes}; limitan el recall")
        ranking, excluidos = ranking_consulta(item, biblioteca, ranqueador)
        filtrados = sorted(candidato for candidato in consulta.relevancias if candidato in por_id and candidato not in ranking)
        if filtrados:
            advertencias.append(f"consulta '{consulta.consulta_id}': candidatos juzgados excluidos (mismo run o versión de descriptor distinta) {filtrados}; limitan el recall")
        metricas.append(evaluar_consulta(consulta.consulta_id, ranking, dict(consulta.relevancias), k))
        exclusiones.append(excluidos)
    avisos = {
        "synthetic": "Juicios sintéticos: las métricas solo prueban el mecanismo, no son evidencia de calidad.",
        "derived_reference": "Juicios derivados por regla de la referencia privada, no revisados por personas: miden acuerdo con esa regla, no preferencia del técnico.",
    }
    aviso = avisos.get(juicios.origen)
    return InformeRecuperacion(
        metodo=metodo, origen_juicios=juicios.origen, version_juicios=juicios.version, aviso=aviso,
        agregadas=agregar(tuple(metricas), k), por_consulta=tuple(metricas), exclusiones=tuple(exclusiones), advertencias=tuple(advertencias),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--biblioteca", type=Path, required=True)
    parser.add_argument("--juicios", type=Path, required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--metodo", choices=sorted(METODOS), default="geometrico")
    args = parser.parse_args(argv)
    if args.k < 1:
        parser.error("--k debe ser >= 1")
    try:
        biblioteca = cargar_biblioteca(args.biblioteca)
        juicios = ConjuntoJuicios.model_validate_json(args.juicios.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    informe = evaluar(biblioteca, juicios, args.k, args.metodo)
    print(json.dumps(informe.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
