"""Corpus de evaluación PlankAssembly por particiones + juicios de relevancia derivados.

Reutiliza el adaptador de ``prepare_plankassembly`` (lector validado, DXF
ortográfico determinista, ZIP por caso) y añade:

* respeto del split oficial (``train``/``valid``/``test``), exclusión de los JSON no
  listados y muestreo determinista por semilla con tamaño configurable;
* auditoría de duplicados y variantes casi idénticas sobre **todos** los modelos
  listados: ningún grupo cruza particiones y cada partición conserva un único
  representante por grupo;
* separación física pública/privada (la pública solo contiene vistas DXF);
* juicios graduados para ``tools/evaluar_recuperacion`` derivados de la referencia
  privada con una regla documentada (``ReglaRelevancia``).

No descarga ni escribe datos en Git: las salidas deben ir fuera del repositorio
(CC BY-NC-ND 4.0). Es preparación de datos, no un resultado de inferencia.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from tools.prepare_plankassembly import (
    PUBLIC_INSTRUCTION,
    _archive_case,
    _digest,
    _family_hash,
    _load_model,
    _write_assembled_dxf,
    _write_hashes,
    _write_json,
)

GENERATOR_VERSION = "plankassembly-corpus-1"
REPO_ROOT = Path(__file__).resolve().parents[1]
# Orden de prioridad al resolver grupos que cruzan particiones: se conserva la primera.
PARTICIONES = ("train", "valid", "test")
VISTAS_EMPOBRECIDAS: dict[str, tuple[str, ...]] = {
    "solo_frontal": ("front",),
    "frontal_y_planta": ("front", "top"),
}
VIEW_KIND_COMPLETA = "assembled_orthographic"
VIEW_KIND_EMPOBRECIDA = "assembled_orthographic_partial"
PREFIJO_ID = "pa"
_MAX_DIM_ERROR = 1e-9


# --------------------------------------------------------------------------- regla


@dataclass(frozen=True)
class ReglaRelevancia:
    """Regla de relevancia graduada. Todos los umbrales son inclusivos.

    Grado 2 (comparable): misma familia, envolvente dentro de ``tol_cercana`` en cada
    eje, diferencia de nº de tableros <= ``dif_tableros_cercana`` y diferencia L1 del
    histograma (horizontales, verticales) <= ``dif_histograma_cercana``.
    Grado 1 (parcial): no es 2 y la envolvente está dentro de ``tol_amplia`` en cada
    eje, la diferencia de nº de tableros es <= ``dif_tableros_amplia`` y, además, es la
    misma familia o la diferencia L1 del histograma es <= ``dif_histograma_cercana``.
    Grado 0: el resto.
    """

    tol_cercana: float = 0.10
    tol_amplia: float = 0.25
    dif_tableros_cercana: int = 1
    dif_tableros_amplia: int = 3
    dif_histograma_cercana: int = 2

    def descripcion(self) -> str:
        return (
            "Juicios derivados por regla (ReglaRelevancia) de la referencia privada de PlankAssembly; "
            "no los ha revisado ninguna persona. Eje de comparacion: envolvente (ancho>=fondo, alto) de los "
            "tableros fisicos sin la fila envolvente, numero de tableros, histograma (horizontales, verticales) "
            "inferido del eje mas delgado de cada cuboide (no usa `normal`) y familia (categoria declarada si "
            "existe; si no, familia estructural perfil+trasera). "
            f"Grado 2: misma familia, envolvente <= {self.tol_cercana:.0%} por eje, |dn| <= {self.dif_tableros_cercana}, "
            f"L1 histograma <= {self.dif_histograma_cercana}. "
            f"Grado 1: no es 2, envolvente <= {self.tol_amplia:.0%} por eje, |dn| <= {self.dif_tableros_amplia} y "
            f"(misma familia o L1 <= {self.dif_histograma_cercana}). Grado 0: el resto. "
            "Miden acuerdo con esta regla, no preferencia del tecnico; un metodo que use las mismas magnitudes "
            "(dimensiones, numero de piezas) queda favorecido por construccion."
        )


def grado_relevancia(consulta: Mapping[str, object], candidato: Mapping[str, object], regla: ReglaRelevancia) -> int:
    """Grado 0/1/2 de ``candidato`` para ``consulta`` (puro, determinista, simétrico)."""
    return _grado(_metricas_par(consulta, candidato), regla)


def _metricas_par(consulta: Mapping[str, object], candidato: Mapping[str, object]) -> tuple[bool, float, int, int]:
    fq, fc = consulta["features"], candidato["features"]  # type: ignore[index]
    dims_q = (fq["ancho_mm"], fq["fondo_mm"], fq["alto_mm"])
    dims_c = (fc["ancho_mm"], fc["fondo_mm"], fc["alto_mm"])
    d_rel = max(abs(a - b) / max(a, b) for a, b in zip(dims_q, dims_c))
    dn = abs(fq["n_piezas"] - fc["n_piezas"])
    l1 = abs(fq["n_horizontales"] - fc["n_horizontales"]) + abs(fq["n_verticales"] - fc["n_verticales"])
    return consulta["familia"] == candidato["familia"], d_rel, dn, l1


def _grado(par: tuple[bool, float, int, int], regla: ReglaRelevancia) -> int:
    misma, d_rel, dn, l1 = par
    if misma and d_rel <= regla.tol_cercana and dn <= regla.dif_tableros_cercana and l1 <= regla.dif_histograma_cercana:
        return 2
    if d_rel <= regla.tol_amplia and dn <= regla.dif_tableros_amplia and (misma or l1 <= regla.dif_histograma_cercana):
        return 1
    return 0


# ------------------------------------------------------------------ características


def _rodear(valor: float) -> int:
    return math.floor(valor + 0.5)


def calcular_features(fisicas: Sequence[Sequence[float]]) -> dict[str, object]:
    """Características estructurales de los tableros físicos (sin la envolvente).

    Supone la convención x=ancho, y=fondo, z=alto. La orientación de cada tablero se
    infiere de su eje más delgado, no de ``normal``.
    """
    xmin = min(b[0] for b in fisicas)
    ymin = min(b[1] for b in fisicas)
    zmin = min(b[2] for b in fisicas)
    extent = (max(b[3] for b in fisicas) - xmin, max(b[4] for b in fisicas) - ymin, max(b[5] for b in fisicas) - zmin)
    ancho, fondo = max(extent[0], extent[1]), min(extent[0], extent[1])
    alto = extent[2]
    eje_largo = 0 if extent[0] >= extent[1] else 1
    eje_trasera = 1 - eje_largo
    horizontales = laterales = traseras = 0
    for b in fisicas:
        dims = (b[3] - b[0], b[4] - b[1], b[5] - b[2])
        # Prioridad de desempate z, x, y para que sea determinista.
        eje = min((2, 0, 1), key=lambda axis: (dims[axis], axis != 2, axis))
        if eje == 2:
            horizontales += 1
            continue
        laterales += 1
        if (
            eje == eje_trasera
            and dims[eje_largo] >= 0.9 * extent[eje_largo]
            and dims[2] >= 0.6 * alto
        ):
            traseras += 1
    perfil_ratio = alto / ancho
    perfil = "alto" if perfil_ratio >= 1.5 else ("bajo" if perfil_ratio <= 0.6 else "medio")
    familia = f"{perfil}_{'con_trasera' if traseras else 'abierto'}"
    return {
        "n_piezas": len(fisicas),
        "n_horizontales": horizontales,
        "n_verticales": laterales,
        "n_traseras": traseras,
        "ancho_mm": round(ancho, 3),
        "fondo_mm": round(fondo, 3),
        "alto_mm": round(alto, 3),
        "familia_estructural": familia,
        "orientacion": "inferida_del_eje_mas_delgado",
    }


# ----------------------------------------------------------------------- firmas


def _firmas(fisicas: Sequence[Sequence[float]], tolerancia_mm: float, paso_escala: float) -> tuple[str, tuple[Hashable, ...]]:
    """Hash exacto (invariante a traslación) y claves de agrupación de duplicados.

    Claves: exacta (mm, 0.1), mismas dimensiones por tablero a ``tolerancia_mm`` y
    reescalado isótropo (dimensiones normalizadas por la mayor extensión, ``paso_escala``).
    Las dos últimas usan dos rejillas desplazadas medio paso: reducen, sin eliminar, los
    fallos por frontera de celda.
    """
    xmin = min(b[0] for b in fisicas)
    ymin = min(b[1] for b in fisicas)
    zmin = min(b[2] for b in fisicas)
    exacta = tuple(sorted(
        tuple(round(v - o, 1) for v, o in zip(b, (xmin, ymin, zmin, xmin, ymin, zmin))) for b in fisicas
    ))
    exact_hash = _digest(json.dumps(exacta, separators=(",", ":")).encode("ascii"))[:16]
    dims = sorted(tuple(sorted(b[i + 3] - b[i] for i in range(3))) for b in fisicas)
    mayor = max(
        max(b[3] for b in fisicas) - xmin, max(b[4] for b in fisicas) - ymin, max(b[5] for b in fisicas) - zmin
    )
    claves: list[Hashable] = [("exacta", exact_hash)]
    for etiqueta, paso, factor in (("dim", tolerancia_mm, 1.0), ("escala", paso_escala, 1.0 / mayor)):
        for desplazamiento in (0.0, 0.5):
            claves.append((
                etiqueta, desplazamiento,
                tuple(tuple(_rodear(d * factor / paso + desplazamiento) for d in plank) for plank in dims),
            ))
    return exact_hash, tuple(claves)


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, item: int) -> int:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            # La raíz menor mantiene el resultado independiente del orden de las uniones.
            self._parent[max(a, b)] = min(a, b)


@dataclass(frozen=True)
class ModeloAnalizado:
    filename: str
    partition: str
    sha256: str
    fisicas: tuple[tuple[float, ...], ...]
    has_normal: bool
    exact_hash: str
    family_hash: str
    claves: tuple[Hashable, ...]
    features: dict[str, object]
    categoria: str | None
    model: dict[str, object]


# ------------------------------------------------------------------- auditoría


def _leer_particiones(source: Path) -> dict[str, list[str]]:
    base = source / "extracted" / "data"
    listas: dict[str, list[str]] = {}
    for partition in PARTICIONES:
        path = base / "splits" / f"{partition}.txt"
        listas[partition] = sorted({line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()})
    vistos: dict[str, str] = {}
    for partition, nombres in listas.items():
        for nombre in nombres:
            if nombre in vistos:
                raise ValueError(f"model {nombre!r} listed in both {vistos[nombre]} and {partition}")
            vistos[nombre] = partition
    return listas


def _split_hashes(source: Path) -> dict[str, str]:
    base = source / "extracted" / "data" / "splits"
    return {p: _digest((base / f"{p}.txt").read_bytes()) for p in PARTICIONES}


def auditar_universo(
    source: Path,
    *,
    tolerancia_mm: float = 2.0,
    paso_escala: float = 0.01,
    campo_categoria: str | None = None,
) -> tuple[list[ModeloAnalizado], dict[str, object]]:
    """Analiza todos los modelos listados y aplica la política de duplicados.

    Devuelve los supervivientes (ordenados por partición y nombre) y la auditoría.
    Política: sobre grupos de duplicados/variantes casi idénticas (unión de claves),
    un grupo que toca varias particiones se conserva solo en la primera según
    ``PARTICIONES`` (train > valid > test; se descontamina valid/test, train queda
    intacto) y dentro de cada partición queda un único representante (menor nombre).
    """
    listas = _leer_particiones(source)
    model_dir = source / "extracted" / "data" / "model"
    listados = {nombre for nombres in listas.values() for nombre in nombres}
    ausentes = sorted(n for n in listados if not (model_dir / n).is_file())
    if ausentes:
        raise ValueError(f"{len(ausentes)} listed models are missing, e.g. {ausentes[0]!r}")
    no_listados = sorted(p.name for p in model_dir.glob("*.json") if p.name not in listados)

    analizados: list[ModeloAnalizado] = []
    invalidos: list[dict[str, str]] = []
    for partition in PARTICIONES:
        for nombre in listas[partition]:
            try:
                model, data = _load_model(source, nombre)
            except (ValueError, json.JSONDecodeError, OSError) as exc:
                invalidos.append({"source_file": nombre, "partition": partition, "reason": str(exc)})
                continue
            fisicas = tuple(tuple(b) for b in model["planks"][1:])  # type: ignore[index]
            exact_hash, claves = _firmas(fisicas, tolerancia_mm, paso_escala)
            categoria = None
            if campo_categoria is not None:
                valor = model.get(campo_categoria)
                categoria = valor if isinstance(valor, str) and valor else None
            analizados.append(ModeloAnalizado(
                filename=nombre, partition=partition, sha256=_digest(data), fisicas=fisicas,
                has_normal=model.get("normal") is not None, exact_hash=exact_hash,
                family_hash=_family_hash(model["planks"]),  # type: ignore[arg-type]
                claves=claves, features=calcular_features(fisicas), categoria=categoria, model=model,
            ))

    union = _UnionFind(len(analizados))
    primera: dict[Hashable, int] = {}
    for indice, modelo in enumerate(analizados):
        for clave in modelo.claves:
            if clave in primera:
                union.union(primera[clave], indice)
            else:
                primera[clave] = indice
    grupos: dict[int, list[int]] = {}
    for indice in range(len(analizados)):
        grupos.setdefault(union.find(indice), []).append(indice)

    prioridad = {p: i for i, p in enumerate(PARTICIONES)}
    supervivientes: list[ModeloAnalizado] = []
    cruce: dict[str, list[str]] = {p: [] for p in PARTICIONES}
    dentro: dict[str, list[str]] = {p: [] for p in PARTICIONES}
    grupo_de: dict[str, str] = {}
    grupos_cruzados = grupos_con_duplicados = 0
    for raiz in sorted(grupos):
        miembros = [analizados[i] for i in grupos[raiz]]
        particiones = {m.partition for m in miembros}
        if len(miembros) > 1:
            grupos_con_duplicados += 1
        if len(particiones) > 1:
            grupos_cruzados += 1
        ganadora = min(particiones, key=prioridad.__getitem__)
        miembros.sort(key=lambda m: m.filename)
        representante = next(m for m in miembros if m.partition == ganadora)
        group_id = "grp-" + _digest(("group|" + representante.filename).encode())[:12]
        for miembro in miembros:
            if miembro.partition != ganadora:
                cruce[miembro.partition].append(miembro.filename)
            elif miembro is not representante:
                dentro[miembro.partition].append(miembro.filename)
        grupo_de[representante.filename] = group_id
        supervivientes.append(representante)
    supervivientes.sort(key=lambda m: (prioridad[m.partition], m.filename))

    resumen = {
        p: {
            "listed": len(listas[p]),
            "invalid": sum(1 for item in invalidos if item["partition"] == p),
            "dropped_cross_split": len(cruce[p]),
            "dropped_within_split_duplicate": len(dentro[p]),
            "available": sum(1 for m in supervivientes if m.partition == p),
        }
        for p in PARTICIONES
    }
    auditoria: dict[str, object] = {
        "unlisted_json_excluded": len(no_listados),
        "unlisted_json_files": no_listados,
        "invalid_models": invalidos,
        "partitions": resumen,
        "duplicate_groups": {
            "groups": len(grupos),
            "groups_with_more_than_one_member": grupos_con_duplicados,
            "groups_crossing_partitions": grupos_cruzados,
            "tolerance_mm": tolerancia_mm,
            "scale_step": paso_escala,
            "keys": ["exact_translated_mm_0.1", "per_plank_dims_within_tolerance_dual_grid", "isotropic_scale_dual_grid"],
            "limitation": "Heuristic grid keys: they bound but do not prove the absence of near-duplicates; anisotropic or parametric variants are not detected.",
        },
        "dropped_cross_split": cruce,
        "dropped_within_split_duplicate": dentro,
        "group_ids": grupo_de,
    }
    return supervivientes, auditoria


# ------------------------------------------------------------------- muestreo


def muestrear(
    supervivientes: Sequence[ModeloAnalizado], semilla: str, tamanos: Mapping[str, int]
) -> dict[str, list[ModeloAnalizado]]:
    """Muestreo determinista y estable por prefijo: orden por SHA-256(semilla|partición|archivo)."""
    resultado: dict[str, list[ModeloAnalizado]] = {}
    for partition in PARTICIONES:
        candidatos = [m for m in supervivientes if m.partition == partition]
        candidatos.sort(key=lambda m: (_digest(f"{semilla}|{partition}|{m.filename}".encode()), m.filename))
        resultado[partition] = candidatos[: max(0, tamanos.get(partition, 0))]
    return resultado


# ---------------------------------------------------------------------- juicios


def construir_juicios(
    referencias: Sequence[Mapping[str, object]],
    regla: ReglaRelevancia,
    *,
    version: str,
    particion_consultas: str = "test",
    max_pares: int = 3_000_000,
    ceros_por_consulta: int | None = None,
) -> dict[str, object]:
    """Juicios densos (todos los pares) de las consultas hacia el resto del corpus completo.

    ``ceros_por_consulta=None`` incluye todos los candidatos (cobertura 1.0). Con un
    entero N, conserva los grados >= 1 y los N ceros más cercanos (cobertura < 1).
    """
    completas = sorted((r for r in referencias if r.get("variant_of") is None), key=lambda r: str(r["id"]))
    consultas = [r for r in completas if r["partition"] == particion_consultas]
    if not consultas:
        raise ValueError(f"no complete cases in partition {particion_consultas!r}")
    if ceros_por_consulta is None and len(consultas) * (len(completas) - 1) > max_pares:
        raise ValueError(
            f"{len(consultas) * (len(completas) - 1)} judged pairs exceed max_pairs={max_pares}; "
            "reduce sizes or pass zeros_per_query to keep only the nearest zero-grade candidates"
        )
    salida = []
    for consulta in consultas:
        puntuados = []
        for candidato in completas:
            if candidato["id"] == consulta["id"]:
                continue
            par = _metricas_par(consulta, candidato)
            puntuados.append((str(candidato["id"]), _grado(par, regla), par[1], par[3]))
        if ceros_por_consulta is not None:
            positivos = [p for p in puntuados if p[1] >= 1]
            ceros = sorted((p for p in puntuados if p[1] == 0), key=lambda p: (p[2], p[3], p[0]))[:ceros_por_consulta]
            puntuados = positivos + ceros
        relevancias = {item_id: grado for item_id, grado, _, _ in sorted(puntuados)}
        salida.append({"consulta_id": str(consulta["id"]), "relevancias": relevancias})
    return {
        "version": version,
        "origen": "derived_reference",
        "descripcion": regla.descripcion(),
        "consultas": salida,
    }


def _variantes_de(referencias: Sequence[Mapping[str, object]], poor_kind: str) -> list[Mapping[str, object]]:
    return [r for r in sorted(referencias, key=lambda r: str(r["id"])) if r.get("variant_of") is not None and r.get("poor_kind") == poor_kind]


def _comprobar_pares(consultas: int, candidatos: int, max_pares: int, zeros: int | None, que: str) -> None:
    if zeros is None and consultas * candidatos > max_pares:
        raise ValueError(
            f"{que}: {consultas * candidatos} judged pairs exceed max_pairs={max_pares}; "
            "reduce sizes or pass zeros_per_query"
        )


def juicios_de_variantes(
    juicios_base: Mapping[str, object], referencias: Sequence[Mapping[str, object]], poor_kind: str,
    *, max_pares: int = 3_000_000, ceros_por_consulta: int | None = None,
) -> dict[str, object] | None:
    """Mismos grados que la consulta completa; las variantes candidatas heredan el de su caso base.

    Biblioteca del archivo: casos completos + variantes de ``poor_kind``. La variante usa
    como ``run_id`` el id de su caso base, de modo que el evaluador excluye al mueble
    completo propio. Las variantes de otros casos son candidatas y se juzgan con el grado
    de su base respecto a la base de la consulta (cobertura completa).
    """
    por_base = {c["consulta_id"]: c for c in juicios_base["consultas"]}  # type: ignore[index, union-attr]
    variantes = _variantes_de(referencias, poor_kind)
    variante_de_base = {str(r["variant_of"]): str(r["id"]) for r in variantes}
    completas = sum(1 for r in referencias if r.get("variant_of") is None)
    _comprobar_pares(len(variantes), completas + len(variantes) - 1, max_pares, ceros_por_consulta, f"variants {poor_kind}")
    consultas = []
    for ref in variantes:
        base = por_base.get(ref["variant_of"])
        if base is None:
            continue
        relevancias = dict(base["relevancias"])
        for base_id, variante_id in variante_de_base.items():
            if variante_id != ref["id"] and base_id in base["relevancias"]:
                relevancias[variante_id] = base["relevancias"][base_id]
        consultas.append({
            "consulta_id": ref["id"],
            "relevancias": dict(sorted(relevancias.items())),
            "nota": f"Variante empobrecida ({poor_kind}) de {ref['variant_of']}; mismos grados que la consulta completa; "
                    "las variantes candidatas heredan el grado de su base. Con run_id de la variante = id de su base, "
                    "la completa propia queda excluida.",
        })
    if not consultas:
        return None
    return {**juicios_base, "version": f"{juicios_base['version']}+{poor_kind}", "consultas": consultas}


def juicios_identidad(
    referencias: Sequence[Mapping[str, object]], poor_kind: str, *, version: str,
    max_pares: int = 3_000_000, ceros_por_consulta: int | None = None,
) -> dict[str, object] | None:
    """Tarea entre vistas: la consulta es una variante empobrecida y solo su mueble completo es relevante.

    Mide si un método reconoce el mismo mueble con menos vistas (el caso difícil que el
    laboratorio semántico midió con Hit@1=0,30). Es una tarea distinta de la similitud
    graduada: aquí el caso completo propio es **el** acierto (grado 2), el resto grado 0.
    Biblioteca del archivo: casos completos + variantes de ``poor_kind``, cada una con un
    ``run_id`` distinto del de su base. Las variantes de otros casos se juzgan con 0.
    """
    completas = sorted(str(r["id"]) for r in referencias if r.get("variant_of") is None)
    variantes = _variantes_de(referencias, poor_kind)
    _comprobar_pares(len(variantes), len(completas) + len(variantes) - 1, max_pares, ceros_por_consulta, f"identity {poor_kind}")
    consultas = []
    for ref in variantes:
        propio = str(ref["variant_of"])
        otros = sorted([c for c in completas if c != propio] + [str(v["id"]) for v in variantes if v["id"] != ref["id"]])
        if ceros_por_consulta is not None:
            otros = otros[:ceros_por_consulta]
        relevancias = {cid: 0 for cid in otros}
        relevancias[propio] = 2
        consultas.append({
            "consulta_id": ref["id"], "relevancias": dict(sorted(relevancias.items())),
            "nota": f"Identidad entre vistas ({poor_kind}): solo {propio} es el mismo mueble.",
        })
    if not consultas:
        return None
    return {
        "version": f"{version}+identidad+{poor_kind}",
        "origen": "derived_reference",
        "descripcion": (
            "Juicios de identidad entre vistas derivados de la construccion del corpus (variante empobrecida "
            f"-> su mueble completo, grado 2; resto, grado 0), vistas {poor_kind}. No miden similitud graduada. "
            "Referencia: mismo programa de origen."
        ),
        "consultas": consultas,
    }


# ---------------------------------------------------------------------- escritura


def _id_opaco(semilla: str, partition: str, posicion: int, tipo: str) -> str:
    """Id público de longitud fija derivado de la semilla (privada) y no reconstruible sin ella."""
    return f"{PREFIJO_ID}-" + _digest(f"{semilla}|case-id|{partition}|{posicion}|{tipo}".encode())[:12]


def _referencia(case_id: str, grupo: str, modelo: ModeloAnalizado) -> dict[str, object]:
    planks = modelo.model["planks"]
    normal = modelo.model.get("normal")
    familia = modelo.categoria or str(modelo.features["familia_estructural"])
    return {
        "id": case_id,
        "partition": modelo.partition,
        "variant_of": None,
        "source_file": modelo.filename,
        "source_sha256": modelo.sha256,
        "group_id": grupo,
        "exact_hash": modelo.exact_hash,
        "family_hash": modelo.family_hash,
        "categoria": modelo.categoria,
        "familia": familia,
        "familia_origen": "categoria_declarada" if modelo.categoria else "estructural_inferida",
        "features": modelo.features,
        "envelope_source_index": 0,
        "components": [
            {
                "source_index": source_index,
                "bounds_mm": bounds,
                "normal": normal[source_index] if normal is not None else None,
            }
            for source_index, bounds in enumerate(planks[1:], 1)  # type: ignore[index]
        ],
        "source_attach_indices": modelo.model["attach"],
    }


def _validar_destinos(public: Path, private: Path) -> None:
    if public == private or public.is_relative_to(private) or private.is_relative_to(public):
        raise ValueError("public and private destinations must be separate")
    for destino in (public, private):
        if destino.is_relative_to(REPO_ROOT):
            raise ValueError(f"destination {destino} is inside the repository; dataset derivatives (CC BY-NC-ND 4.0) must stay outside Git")
        if destino.exists():
            raise ValueError("destination exists")


def generar_corpus(
    source: Path,
    public_destination: Path,
    private_destination: Path,
    *,
    seed: str | int = "vexplorer-corpus-1",
    sizes: Mapping[str, int] | None = None,
    poor_variants: bool = False,
    poor_partitions: Sequence[str] = ("test",),
    category_field: str | None = None,
    tolerance_mm: float = 2.0,
    scale_step: float = 0.01,
    source_revision: str | None = None,
    rule: ReglaRelevancia | None = None,
    max_pairs: int = 3_000_000,
    zeros_per_query: int | None = None,
) -> dict[str, object]:
    """Genera el corpus público/privado y los juicios. Devuelve el manifiesto público."""
    source = source.resolve()
    public_destination = public_destination.resolve()
    private_destination = private_destination.resolve()
    _validar_destinos(public_destination, private_destination)
    tamanos = {"train": 200, "valid": 50, "test": 50, **(dict(sizes) if sizes else {})}
    if set(tamanos) - set(PARTICIONES) or any(not isinstance(v, int) or v < 0 for v in tamanos.values()):
        raise ValueError("sizes must map train/valid/test to non-negative integers")
    if tamanos["test"] < 1:
        raise ValueError("the test partition needs at least one case to derive judgments")
    if not 0 < scale_step < 1 or tolerance_mm <= 0:
        raise ValueError("invalid duplicate-audit tolerances")
    desconocidas = set(poor_partitions) - set(PARTICIONES)
    if desconocidas:
        raise ValueError(f"unknown partitions for poor variants: {sorted(desconocidas)}")
    regla = rule or ReglaRelevancia()
    semilla = str(seed)

    supervivientes, auditoria = auditar_universo(
        source, tolerancia_mm=tolerance_mm, paso_escala=scale_step, campo_categoria=category_field
    )
    muestra = muestrear(supervivientes, semilla, tamanos)
    grupo_de: dict[str, str] = auditoria["group_ids"]  # type: ignore[assignment]

    public_destination.parent.mkdir(parents=True, exist_ok=True)
    private_destination.parent.mkdir(parents=True, exist_ok=True)
    public_stage = Path(tempfile.mkdtemp(prefix=public_destination.name + ".partial-", dir=public_destination.parent))
    private_stage = Path(tempfile.mkdtemp(prefix=private_destination.name + ".partial-", dir=private_destination.parent))
    try:
        (public_stage / "dxf").mkdir()
        (public_stage / "agent_cases").mkdir()
        (private_stage / "juicios").mkdir()
        casos: list[dict[str, object]] = []
        referencias: list[dict[str, object]] = []

        def emitir(case_id: str, fisicas: Sequence[Sequence[float]], partition: str, vistas: tuple[str, ...],
                   *, base: str | None) -> None:
            ruta = public_stage / "dxf" / f"{case_id}.dxf"
            _write_assembled_dxf(ruta, [list(b) for b in fisicas], vistas)
            view_kind = VIEW_KIND_EMPOBRECIDA if base else VIEW_KIND_COMPLETA
            metadata = {
                "id": case_id, "file": f"dxf/{case_id}.dxf", "format": "dxf", "unit": "mm",
                "view_kind": view_kind, "instruction": PUBLIC_INSTRUCTION, "sha256": _digest(ruta.read_bytes()),
            }
            # La relación variante-base, el tipo y la sal de los ids solo viven en references.json.
            casos.append({**metadata, "partition": partition})
            _archive_case(ruta, {k: metadata[k] for k in ("id", "file", "format", "unit", "view_kind", "instruction", "sha256")},
                          public_stage / "agent_cases" / f"{case_id}.zip")

        for partition in PARTICIONES:
            for posicion, modelo in enumerate(muestra[partition], 1):
                case_id = _id_opaco(semilla, partition, posicion, "completa")
                emitir(case_id, modelo.fisicas, partition, ("front", "top", "side"), base=None)
                referencias.append(_referencia(case_id, grupo_de[modelo.filename], modelo))
                if poor_variants and partition in poor_partitions:
                    for kind, vistas in sorted(VISTAS_EMPOBRECIDAS.items()):
                        variant_id = _id_opaco(semilla, partition, posicion, kind)
                        emitir(variant_id, modelo.fisicas, partition, vistas, base=case_id)
                        referencias.append({
                            "id": variant_id, "partition": partition, "variant_of": case_id, "poor_kind": kind,
                            "view_kind": VIEW_KIND_EMPOBRECIDA, "group_id": grupo_de[modelo.filename],
                        })
        casos.sort(key=lambda c: str(c["id"]))
        referencias.sort(key=lambda r: str(r["id"]))

        version_juicios = f"derived-{GENERATOR_VERSION}-seed-{_digest(semilla.encode())[:8]}"
        juicios = construir_juicios(
            referencias, regla, version=version_juicios, max_pares=max_pairs, ceros_por_consulta=zeros_per_query
        )
        # Validación contra el esquema real del evaluador antes de escribir nada.
        from backend.app.precedentes.evaluacion import ConjuntoJuicios
        ConjuntoJuicios.model_validate(juicios)
        archivos_juicios = {"juicios_test.json": juicios}
        ids_completos = sorted(str(r["id"]) for r in referencias if r["variant_of"] is None)
        bibliotecas: dict[str, object] = {"juicios_test.json": {"case_ids": ids_completos, "run_id_overrides": {}}}
        if poor_variants:
            for kind in sorted(VISTAS_EMPOBRECIDAS):
                variantes = _variantes_de(referencias, kind)
                ids_con_variantes = sorted(ids_completos + [str(v["id"]) for v in variantes])
                derivados = juicios_de_variantes(
                    juicios, referencias, kind, max_pares=max_pairs, ceros_por_consulta=zeros_per_query
                )
                if derivados is not None:
                    ConjuntoJuicios.model_validate(derivados)
                    nombre = f"juicios_test_{kind}.json"
                    archivos_juicios[nombre] = derivados
                    bibliotecas[nombre] = {
                        "case_ids": ids_con_variantes,
                        "run_id_overrides": {str(v["id"]): str(v["variant_of"]) for v in variantes},
                    }
                identidad = juicios_identidad(
                    referencias, kind, version=version_juicios, max_pares=max_pairs, ceros_por_consulta=zeros_per_query
                )
                if identidad is not None:
                    ConjuntoJuicios.model_validate(identidad)
                    nombre = f"juicios_identidad_{kind}.json"
                    archivos_juicios[nombre] = identidad
                    bibliotecas[nombre] = {"case_ids": ids_con_variantes, "run_id_overrides": {}}
        for nombre, contenido in archivos_juicios.items():
            _write_json(private_stage / "juicios" / nombre, contenido)
        _write_json(private_stage / "juicios" / "bibliotecas.json", bibliotecas)

        completas = [r for r in referencias if r["variant_of"] is None]
        conteos = {
            p: {
                "requested": tamanos[p],
                "available_after_audit": auditoria["partitions"][p]["available"],  # type: ignore[index]
                "sampled": len(muestra[p]),
            }
            for p in PARTICIONES
        }
        manifiesto_base = {
            "generator_version": GENERATOR_VERSION,
            "source_dataset": "manycore-research/PlankAssembly",
            "source_revision": source_revision or "not declared (not verifiable offline)",
            "partitions": conteos,
            "complete_cases": len(completas),
            "poor_variant_cases": len(referencias) - len(completas),
            "view_kind": VIEW_KIND_COMPLETA,
            "inference_evaluated": False,
            "redistribution_authorized": False,
            "license_notice": "Derived from a CC BY-NC-ND 4.0 dataset; keep outside Git and do not redistribute.",
        }
        _write_json(public_stage / "cases.json", casos)
        _write_json(public_stage / "manifest.json", {
            **manifiesto_base,
            "cases_sha256": _digest((public_stage / "cases.json").read_bytes()),
        })
        _write_json(private_stage / "references.json", referencias)
        _write_json(private_stage / "audit.json", auditoria)
        sin_normal = sum(1 for m in (m for p in PARTICIONES for m in muestra[p]) if not m.has_normal)
        _write_json(private_stage / "manifest.json", {
            **manifiesto_base,
            "seed": semilla,
            "source_split_sha256": _split_hashes(source),
            "audit_summary": auditoria["partitions"],
            "unlisted_json_excluded": auditoria["unlisted_json_excluded"],
            "sampled_without_normal": sin_normal,
            "sampling": "ascending sha256(seed|partition|source_file) over audited survivors; prefix-stable",
            "duplicate_policy": "group crossing partitions kept only in train>valid>test; one representative (lowest filename) per group per partition",
            "relevance_rule": asdict(regla),
            "judgments": {
                "files": sorted(archivos_juicios),
                "query_partition": "test",
                "candidates": "all complete cases except the query",
                "zeros_per_query": zeros_per_query,
                "queries": len(juicios["consultas"]),  # type: ignore[arg-type]
                "queries_without_relevant": sum(
                    1 for c in juicios["consultas"] if not any(g >= 1 for g in c["relevancias"].values())  # type: ignore[union-attr]
                ),
                "biblioteca_contract": "juicios/bibliotecas.json lists, per judgments file, the case_ids the library must "
                                       "contain and run_id_overrides (default run_id == id); one descriptor_version; "
                                       "graded poor-variant files: variant run_id == base case id; "
                                       "identity files: variant run_id != base case id",
            },
            "public_manifest_sha256": _digest((public_stage / "manifest.json").read_bytes()),
            "public_cases_sha256": _digest((public_stage / "cases.json").read_bytes()),
        })
        _write_hashes(public_stage)
        _write_hashes(private_stage)
        public_stage.rename(public_destination)
        private_stage.rename(private_destination)
        return json.loads((public_destination / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        shutil.rmtree(public_stage, ignore_errors=True)
        shutil.rmtree(private_stage, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help="carpeta del dataset (contiene extracted/data)")
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--seed", default="vexplorer-corpus-1")
    parser.add_argument("--train", type=int, default=200)
    parser.add_argument("--valid", type=int, default=50)
    parser.add_argument("--test", type=int, default=50)
    parser.add_argument("--poor-variants", action="store_true", help="variantes empobrecidas (vistas parciales) de la partición test")
    parser.add_argument("--category-field", default=None, help="campo JSON de categoría, solo si se ha verificado que existe")
    parser.add_argument("--tolerance-mm", type=float, default=2.0)
    parser.add_argument("--scale-step", type=float, default=0.01)
    parser.add_argument("--source-revision", default=None, help="revisión HF declarada (no verificable sin conexión)")
    parser.add_argument("--max-pairs", type=int, default=3_000_000)
    parser.add_argument("--zeros-per-query", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        manifiesto = generar_corpus(
            args.source, args.public_output, args.private_output,
            seed=args.seed, sizes={"train": args.train, "valid": args.valid, "test": args.test},
            poor_variants=args.poor_variants, category_field=args.category_field,
            tolerance_mm=args.tolerance_mm, scale_step=args.scale_step, source_revision=args.source_revision,
            max_pairs=args.max_pairs, zeros_per_query=args.zeros_per_query,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Corpus generation failed: {exc}\n")
    print(json.dumps(manifiesto, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
