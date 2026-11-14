"""Idea 3.3: embeddings de imagen del plano (solo mecanismo).

No hay modelo de imagen en producción (los embeddings de OpenAI no admiten imágenes y
EmbeddingGemma 2 solo se usó en local en ``docs/semantic-lab/``). Este módulo deja el
mecanismo listo para enchufar un proveedor:

- ``ProveedorEmbeddingImagen``: protocolo mínimo (``espacio_id``, ``dimensiones``, ``embeber``).
- ``AlmacenImagen``: SQLite propio. Caché de vectores por (sha256 del PNG, ``espacio_id``) y
  asignación de vistas por run.
- Obtención de PNGs: se renderizan desde la extracción del run con
  ``backend.app.agente.vision.render_view`` (sin modificarla). Es viable porque el repositorio
  expone ``get_extraction``; por eso no se aceptan PNGs subidos por el cliente. El render es
  determinista, así que el hash del PNG sirve como clave de caché.
- Búsqueda: coseno entre vectores L2-normalizados, agregado por run como **máximo sobre pares
  de vistas** (las etiquetas FRONT/TOP/SIDE no son fiables entre planos, así que no se exige
  correspondencia; la media penalizaría runs con vistas extra). Se informa del mejor par.
  Solo se comparan vectores del mismo ``espacio_id``. El score es un coseno, no una
  probabilidad, y no está calibrado: si ningún candidato alcanza el umbral, se abstiene.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import Field

from backend.app.agente.vision import render_view
from backend.app.contratos.modelos import DrawingExtraction
from backend.app.precedentes.comun import ModeloEstricto

MAX_VISTAS_POR_RUN = 3
MAX_BYTES_PNG = 2_000_000
MAX_DIMENSIONES = 8192
CRITERIO_AGREGACION = "maximo_coseno_entre_pares_de_vistas"
NOTA_SCORE = (
    "El score es la similitud coseno entre embeddings de imagen (rango -1..1); "
    "no es una probabilidad ni está calibrado. Un precedente es una hipótesis."
)
_REVISION_NINGUNA = 0  # SQLite trata NULL como distinto en claves; las revisiones reales son >= 1.


class ErrorImagen(Exception):
    """Error de dominio con código estable para la API."""

    def __init__(self, codigo: str, mensaje: str | None = None) -> None:
        super().__init__(mensaje or codigo)
        self.codigo = codigo
        self.mensaje = mensaje


@runtime_checkable
class ProveedorEmbeddingImagen(Protocol):
    espacio_id: str
    dimensiones: int

    def embeber(self, png: bytes) -> tuple[float, ...]: ...


class RepositorioRuns(Protocol):
    """Subconjunto del repositorio que necesita este módulo (``DemoRepository`` lo cumple)."""

    def get_run(self, run_id: str): ...

    def get_extraction(self, run_id: str) -> DrawingExtraction: ...


# --- Modelos ---------------------------------------------------------------------------


class VistaPng(ModeloEstricto):
    vista_id: str = Field(min_length=1)
    png: bytes = Field(min_length=1, max_length=MAX_BYTES_PNG)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class VistaOmitida(ModeloEstricto):
    vista_id: str
    codigo: str


class VistasDeRun(ModeloEstricto):
    run_id: str
    result_revision: int | None = Field(default=None, ge=1)
    vistas: tuple[VistaPng, ...]
    omitidas: tuple[VistaOmitida, ...] = ()


class VistaIndexada(ModeloEstricto):
    vista_id: str
    sha256: str
    desde_cache: bool


class ResultadoIndexado(ModeloEstricto):
    run_id: str
    result_revision: int | None
    espacio_id: str
    dimensiones: int
    vistas: tuple[VistaIndexada, ...]
    vistas_omitidas: tuple[VistaOmitida, ...]


class Precedente(ModeloEstricto):
    run_id: str
    result_revision: int | None
    score_coseno: float
    vista_consulta: str
    vista_candidata: str


class ResultadoSimilares(ModeloEstricto):
    run_id: str
    espacio_id: str
    estado: Literal["ok", "sin_precedentes_suficientes"]
    metrica: Literal["coseno"] = "coseno"
    es_probabilidad: Literal[False] = False
    agregacion: str = CRITERIO_AGREGACION
    umbral_minimo: float
    candidatos_evaluados: int
    precedentes: tuple[Precedente, ...]
    nota: str = NOTA_SCORE


class VectorVista(ModeloEstricto):
    run_id: str
    result_revision: int | None
    vista_id: str
    sha256: str
    vector: tuple[float, ...]


# --- Funciones puras -------------------------------------------------------------------


def validar_y_normalizar(vector: object, dimensiones: int) -> tuple[float, ...]:
    """Comprueba dimensión, finitud y norma > 0; devuelve el vector L2-normalizado."""
    if not isinstance(vector, (tuple, list)):
        raise ErrorImagen("vector_invalido", "El proveedor no devolvió una secuencia.")
    if len(vector) != dimensiones:
        raise ErrorImagen(
            "vector_invalido",
            f"Dimensión {len(vector)} distinta de la declarada ({dimensiones}).",
        )
    valores: list[float] = []
    for valor in vector:
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ErrorImagen("vector_invalido", "El vector contiene valores no numéricos.")
        if not math.isfinite(valor):
            raise ErrorImagen("vector_invalido", "El vector contiene valores no finitos.")
        valores.append(float(valor))
    norma = math.sqrt(math.fsum(v * v for v in valores))
    if not math.isfinite(norma) or norma <= 0:
        raise ErrorImagen("vector_invalido", "El vector tiene norma nula.")
    return tuple(v / norma for v in valores)


def coseno(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Coseno entre vectores ya normalizados (producto escalar acotado a [-1, 1])."""
    if len(a) != len(b):
        raise ErrorImagen("dimension_incompatible")
    return max(-1.0, min(1.0, math.fsum(x * y for x, y in zip(a, b, strict=True))))


def agregar_por_run(
    consulta: Mapping[str, tuple[float, ...]],
    candidatos: Mapping[str, tuple[VectorVista, ...]],
    *,
    excluir_run_id: str,
) -> tuple[Precedente, ...]:
    """Máximo coseno sobre pares de vistas por run candidato; orden (-score, run_id)."""
    resultado: list[Precedente] = []
    for run_id in sorted(candidatos):
        if run_id == excluir_run_id:
            continue
        mejor: tuple[float, str, str] | None = None
        revision: int | None = None
        for vista_q in sorted(consulta):
            for candidata in sorted(candidatos[run_id], key=lambda v: v.vista_id):
                score = coseno(consulta[vista_q], candidata.vector)
                if mejor is None or score > mejor[0]:
                    mejor = (score, vista_q, candidata.vista_id)
                    revision = candidata.result_revision
        if mejor is not None:
            resultado.append(
                Precedente(
                    run_id=run_id,
                    result_revision=revision,
                    score_coseno=round(mejor[0], 12),
                    vista_consulta=mejor[1],
                    vista_candidata=mejor[2],
                )
            )
    return tuple(sorted(resultado, key=lambda p: (-p.score_coseno, p.run_id)))


def seleccionar_precedentes(
    agregados: tuple[Precedente, ...], *, limite: int, umbral_minimo: float
) -> tuple[Literal["ok", "sin_precedentes_suficientes"], tuple[Precedente, ...]]:
    filtrados = tuple(p for p in agregados if p.score_coseno >= umbral_minimo)[:limite]
    return ("ok" if filtrados else "sin_precedentes_suficientes"), filtrados


def renderizar_vistas(
    extraction: DrawingExtraction, *, max_vistas: int = MAX_VISTAS_POR_RUN
) -> tuple[tuple[VistaPng, ...], tuple[VistaOmitida, ...]]:
    """Renderiza hasta ``max_vistas`` vistas (orden por id); omite las no renderizables."""
    vistas: list[VistaPng] = []
    omitidas: list[VistaOmitida] = []
    for vista in sorted(extraction.views, key=lambda v: v.id):
        if len(vistas) >= max_vistas:
            break
        try:
            render = render_view(extraction, vista.id, max_png_bytes=MAX_BYTES_PNG)
        except ValueError as error:
            omitidas.append(VistaOmitida(vista_id=vista.id, codigo=str(error)))
            continue
        vistas.append(VistaPng(vista_id=render.view_id, png=render.png, sha256=render.sha256))
    return tuple(vistas), tuple(omitidas)


def vistas_desde_repositorio(repositorio: RepositorioRuns, run_id: str) -> VistasDeRun:
    """Obtiene la extracción del run y renderiza sus vistas. ``KeyError`` si no existe."""
    run = repositorio.get_run(run_id)
    extraction = repositorio.get_extraction(run_id)
    vistas, omitidas = renderizar_vistas(extraction)
    return VistasDeRun(
        run_id=run_id,
        result_revision=getattr(run, "result_revision", None),
        vistas=vistas,
        omitidas=omitidas,
    )


# --- Almacén SQLite --------------------------------------------------------------------


class AlmacenImagen:
    """Vectores de imagen por (run, revisión, vista, sha256, espacio) con caché por hash."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._conexion() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS vectores_imagen (
                    png_sha256 TEXT NOT NULL,
                    espacio_id TEXT NOT NULL,
                    dimensiones INTEGER NOT NULL,
                    vector_json TEXT NOT NULL,
                    creado_en TEXT NOT NULL,
                    PRIMARY KEY (png_sha256, espacio_id)
                );
                CREATE TABLE IF NOT EXISTS vistas_imagen (
                    run_id TEXT NOT NULL,
                    result_revision INTEGER NOT NULL,
                    vista_id TEXT NOT NULL,
                    png_sha256 TEXT NOT NULL,
                    espacio_id TEXT NOT NULL,
                    PRIMARY KEY (run_id, espacio_id, vista_id)
                );
                CREATE INDEX IF NOT EXISTS vistas_imagen_espacio
                    ON vistas_imagen (espacio_id, run_id);
                """
            )

    @contextmanager
    def _conexion(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.ruta)) as db, db:
            yield db

    def obtener_vector(self, png_sha256: str, espacio_id: str) -> tuple[float, ...] | None:
        with self._conexion() as db:
            fila = db.execute(
                "SELECT vector_json FROM vectores_imagen WHERE png_sha256=? AND espacio_id=?",
                (png_sha256, espacio_id),
            ).fetchone()
        return None if fila is None else tuple(json.loads(fila[0]))

    def guardar_vector(
        self, png_sha256: str, espacio_id: str, dimensiones: int, vector: tuple[float, ...]
    ) -> tuple[float, ...]:
        normalizado = validar_y_normalizar(vector, dimensiones)
        with self._conexion() as db:
            db.execute(
                "INSERT OR IGNORE INTO vectores_imagen VALUES (?,?,?,?,?)",
                (
                    png_sha256,
                    espacio_id,
                    dimensiones,
                    json.dumps(normalizado),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return normalizado

    def asignar_vistas(
        self,
        run_id: str,
        result_revision: int | None,
        espacio_id: str,
        vistas: tuple[tuple[str, str], ...],
    ) -> None:
        """Reemplaza atómicamente las vistas del run en el espacio por ``(vista_id, sha256)``."""
        revision = _REVISION_NINGUNA if result_revision is None else result_revision
        with self._conexion() as db:
            db.execute(
                "DELETE FROM vistas_imagen WHERE run_id=? AND espacio_id=?", (run_id, espacio_id)
            )
            db.executemany(
                "INSERT INTO vistas_imagen VALUES (?,?,?,?,?)",
                [(run_id, revision, vista_id, sha, espacio_id) for vista_id, sha in vistas],
            )

    def espacios_de_run(self, run_id: str) -> tuple[str, ...]:
        with self._conexion() as db:
            filas = db.execute(
                "SELECT DISTINCT espacio_id FROM vistas_imagen WHERE run_id=? ORDER BY espacio_id",
                (run_id,),
            ).fetchall()
        return tuple(fila[0] for fila in filas)

    def vectores_del_espacio(self, espacio_id: str) -> dict[str, tuple[VectorVista, ...]]:
        with self._conexion() as db:
            filas = db.execute(
                """
                SELECT v.run_id, v.result_revision, v.vista_id, v.png_sha256, e.vector_json
                FROM vistas_imagen v
                JOIN vectores_imagen e
                  ON e.png_sha256 = v.png_sha256 AND e.espacio_id = v.espacio_id
                WHERE v.espacio_id = ?
                ORDER BY v.run_id, v.vista_id
                """,
                (espacio_id,),
            ).fetchall()
        agrupado: dict[str, list[VectorVista]] = {}
        for run_id, revision, vista_id, sha, vector_json in filas:
            agrupado.setdefault(run_id, []).append(
                VectorVista(
                    run_id=run_id,
                    result_revision=None if revision == _REVISION_NINGUNA else revision,
                    vista_id=vista_id,
                    sha256=sha,
                    vector=tuple(json.loads(vector_json)),
                )
            )
        return {run_id: tuple(vistas) for run_id, vistas in agrupado.items()}


# --- Casos de uso ----------------------------------------------------------------------


def _validar_proveedor(proveedor: ProveedorEmbeddingImagen) -> None:
    if not isinstance(proveedor.espacio_id, str) or not proveedor.espacio_id:
        raise ErrorImagen("proveedor_imagen_invalido", "espacio_id vacío.")
    if not isinstance(proveedor.dimensiones, int) or not 1 <= proveedor.dimensiones <= MAX_DIMENSIONES:
        raise ErrorImagen("proveedor_imagen_invalido", "dimensiones fuera de rango.")


def indexar_vistas(
    almacen: AlmacenImagen, proveedor: ProveedorEmbeddingImagen, vistas: VistasDeRun
) -> ResultadoIndexado:
    """Embebe (con caché por sha256 y espacio) y registra las vistas del run."""
    _validar_proveedor(proveedor)
    if not vistas.vistas:
        raise ErrorImagen("sin_vistas_renderizables", "Ninguna vista del plano se pudo renderizar.")
    indexadas: list[VistaIndexada] = []
    for vista in sorted(vistas.vistas, key=lambda v: v.vista_id):
        en_cache = almacen.obtener_vector(vista.sha256, proveedor.espacio_id) is not None
        if not en_cache:
            try:
                vector = proveedor.embeber(vista.png)
            except ErrorImagen:
                raise
            except Exception as error:  # el proveedor es externo
                raise ErrorImagen("proveedor_imagen_fallo", type(error).__name__) from error
            almacen.guardar_vector(vista.sha256, proveedor.espacio_id, proveedor.dimensiones, vector)
        indexadas.append(VistaIndexada(vista_id=vista.vista_id, sha256=vista.sha256, desde_cache=en_cache))
    almacen.asignar_vistas(
        vistas.run_id,
        vistas.result_revision,
        proveedor.espacio_id,
        tuple((v.vista_id, v.sha256) for v in indexadas),
    )
    return ResultadoIndexado(
        run_id=vistas.run_id,
        result_revision=vistas.result_revision,
        espacio_id=proveedor.espacio_id,
        dimensiones=proveedor.dimensiones,
        vistas=tuple(indexadas),
        vistas_omitidas=vistas.omitidas,
    )


def buscar_similares(
    almacen: AlmacenImagen,
    run_id: str,
    espacio_id: str,
    *,
    limite: int,
    umbral_minimo: float,
) -> ResultadoSimilares:
    """Busca sobre vectores ya guardados; no necesita proveedor."""
    por_run = almacen.vectores_del_espacio(espacio_id)
    propias = por_run.get(run_id)
    if not propias:
        raise ErrorImagen("run_no_indexado", "El run no tiene vectores en este espacio.")
    consulta = {v.vista_id: v.vector for v in propias}
    agregados = agregar_por_run(consulta, por_run, excluir_run_id=run_id)
    estado, precedentes = seleccionar_precedentes(
        agregados, limite=limite, umbral_minimo=umbral_minimo
    )
    return ResultadoSimilares(
        run_id=run_id,
        espacio_id=espacio_id,
        estado=estado,
        umbral_minimo=umbral_minimo,
        candidatos_evaluados=len(agregados),
        precedentes=precedentes,
    )
