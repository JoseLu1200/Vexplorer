"""Idea 2.6: huella del espacio de embedding con frases de control fijas (hallazgo H8).

La huella son los vectores de ``FRASES_CONTROL`` bajo (modelo, dimensiones). Se guarda una
referencia por (modelo, dimensiones, versión de frases) en un SQLite propio; cada verificación
compara el coseno por frase con una tolerancia. Si el proveedor cambia su modelo interno sin cambiar
el nombre, la deriva aparece aquí aunque el nombre del modelo sea el mismo.

La huella no se guarda en ``EmbeddingMetadata`` (cambiaría el contrato y requiere acuerdo A/B): se
vincula a cada embedding mediante sellos por ``cache_key`` en el mismo SQLite (ver ``mantenimiento``).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import Field

from backend.app.precedentes.comun import ModeloEstricto
from backend.app.precedentes.regeneracion import ProveedorEmbeddings, ahora_utc
from backend.app.semantic.embeddings import EmbeddingProviderError, validate_embedding
from backend.app.similarity.service import cosine_similarity

VERSION_FRASES_CONTROL = "control-v1"
TOLERANCIA_POR_DEFECTO = 0.999

# Frases en el formato de ``semantic_text`` (descriptor furniture-v1). No se generan en tiempo de
# ejecución: si ``semantic_text`` cambia, estas frases deben seguir idénticas. Cualquier cambio aquí
# exige subir ``VERSION_FRASES_CONTROL``.
FRASES_CONTROL: tuple[str, ...] = (
    "descriptor=furniture-v1; family=rectangular_shelving; structure=top_base_between_sides; dimensions_mm=width:900.0,depth:300.0,height:1800.0; roles=base_panel:1, shelf:3, side_panel:2, top_panel:1; material=tablero; finish=melamina; unknowns=none",
    "descriptor=furniture-v1; family=rectangular_shelving; structure=top_base_cap_sides; dimensions_mm=width:600.0,depth:400.0,height:1200.0; roles=base_panel:1, shelf:2, side_panel:2, top_panel:1; material=pino; finish=barniz; unknowns=none",
    "descriptor=furniture-v1; family=rectangular_shelving; structure=top_base_between_sides; dimensions_mm=width:1200.0,depth:350.0,height:2000.0; roles=base_panel:1, shelf:4, side_panel:2, top_panel:1; material=roble; finish=aceite; unknowns=none",
    "descriptor=furniture-v1; family=rectangular_shelving; structure=top_base_cap_sides; dimensions_mm=width:450.0,depth:250.0,height:800.0; roles=base_panel:1, shelf:1, side_panel:2, top_panel:1; material=tablero; finish=lacado; unknowns=none",
    "descriptor=furniture-v1; family=rectangular_shelving; structure=top_base_between_sides; dimensions_mm=width:800.0,depth:500.0,height:900.0; roles=base_panel:1, side_panel:2, top_panel:1; material=contrachapado; finish=natural; unknowns=none",
    "descriptor=furniture-v1; family=unknown; structure=unknown; dimensions_mm=width:None,depth:None,height:None; roles=; material=unknown; finish=unknown; unknowns=dimensions.depth_mm,dimensions.height_mm,dimensions.width_mm,finish,material,structure",
)

EstadoEspacio = Literal["referencia_creada", "estable", "deriva_detectada"]


class HuellaEspacio(ModeloEstricto):
    modelo: str = Field(min_length=1)
    dimensiones: int = Field(gt=0)
    version_frases: str = Field(min_length=1)
    huella_id: str = Field(min_length=64, max_length=64)
    vectores: tuple[tuple[float, ...], ...]
    creada_en: str = Field(min_length=1)


class ResumenHuella(ModeloEstricto):
    modelo: str
    dimensiones: int
    version_frases: str
    huella_id: str
    num_frases: int
    creada_en: str
    vectores: tuple[tuple[float, ...], ...] | None = None


class ComparacionFrase(ModeloEstricto):
    indice: int = Field(ge=0)
    frase: str
    coseno: float = Field(allow_inf_nan=False)
    estable: bool


class ResultadoVerificacion(ModeloEstricto):
    estado: EstadoEspacio
    modelo: str
    dimensiones: int
    version_frases: str
    tolerancia: float
    huella_referencia: str
    huella_actual: str
    referencia_creada_en: str
    coseno_minimo: float | None = None
    detalle: tuple[ComparacionFrase, ...] = ()
    accion_sugerida: Literal["rotar_referencia"] | None = None
    mensaje: str | None = None


class HuellaRetirada(ModeloEstricto):
    huella: ResumenHuella
    retirada_en: str


class ResultadoRotacion(ModeloEstricto):
    modelo: str
    dimensiones: int
    version_frases: str
    referencia_nueva: ResumenHuella
    referencia_anterior: HuellaRetirada | None = None
    embeddings_invalidados: int = Field(ge=0)


class ErrorInvalidacionEmbeddings(RuntimeError):
    """La caché no pudo invalidarse; la referencia no debe rotar."""


def calcular_huella_id(modelo: str, dimensiones: int, version_frases: str, vectores: tuple[tuple[float, ...], ...]) -> str:
    """Hash estable (vectores redondeados a 6 decimales) para identificar el espacio."""
    redondeados = [[round(valor, 6) for valor in vector] for vector in vectores]
    carga = json.dumps({"modelo": modelo, "dimensiones": dimensiones, "version_frases": version_frases, "vectores": redondeados}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(carga.encode("utf-8")).hexdigest()


def calcular_huella(proveedor: ProveedorEmbeddings, ahora: Callable[[], str] = ahora_utc, frases: tuple[str, ...] = FRASES_CONTROL, version_frases: str = VERSION_FRASES_CONTROL) -> HuellaEspacio:
    vectores: list[tuple[float, ...]] = []
    for frase in frases:
        resultado = proveedor.embed(frase)
        if resultado.model != proveedor.model or resultado.dimensions != proveedor.dimensions:
            raise EmbeddingProviderError("embedding_space_incompatible")
        vectores.append(validate_embedding(list(resultado.vector), proveedor.dimensions))
    tupla = tuple(vectores)
    return HuellaEspacio(
        modelo=proveedor.model,
        dimensiones=proveedor.dimensions,
        version_frases=version_frases,
        huella_id=calcular_huella_id(proveedor.model, proveedor.dimensions, version_frases, tupla),
        vectores=tupla,
        creada_en=ahora(),
    )


def comparar_huellas(referencia: HuellaEspacio, actual: HuellaEspacio, tolerancia: float, frases: tuple[str, ...] = FRASES_CONTROL) -> ResultadoVerificacion:
    """Función pura: coseno por frase; estable si todos alcanzan la tolerancia."""
    if (referencia.modelo, referencia.dimensiones, referencia.version_frases) != (actual.modelo, actual.dimensiones, actual.version_frases):
        raise ValueError("embedding_space_incompatible")
    if len(referencia.vectores) != len(actual.vectores) or len(frases) != len(actual.vectores):
        raise ValueError("frases_control_incompatibles")
    detalle: list[ComparacionFrase] = []
    for indice, (frase, izquierda, derecha) in enumerate(zip(frases, referencia.vectores, actual.vectores, strict=True)):
        try:
            coseno = round(cosine_similarity(izquierda, derecha), 6)
        except ValueError:
            coseno = -1.0
        detalle.append(ComparacionFrase(indice=indice, frase=frase, coseno=coseno, estable=coseno >= tolerancia))
    estable = all(item.estable for item in detalle)
    return ResultadoVerificacion(
        accion_sugerida=None if estable else "rotar_referencia",
        mensaje=None if estable else (
            "El espacio ha derivado: los vectores nuevos no son comparables con los antiguos. "
            "Rota la referencia (POST .../embeddings/espacio/rotar) y vuelve a embeber la biblioteca."
        ),
        estado="estable" if estable else "deriva_detectada",
        modelo=actual.modelo,
        dimensiones=actual.dimensiones,
        version_frases=actual.version_frases,
        tolerancia=tolerancia,
        huella_referencia=referencia.huella_id,
        huella_actual=actual.huella_id,
        referencia_creada_en=referencia.creada_en,
        coseno_minimo=min(item.coseno for item in detalle) if detalle else None,
        detalle=tuple(detalle),
    )


def resumir(huella: HuellaEspacio, incluir_vectores: bool = False) -> ResumenHuella:
    return ResumenHuella(
        modelo=huella.modelo,
        dimensiones=huella.dimensiones,
        version_frases=huella.version_frases,
        huella_id=huella.huella_id,
        num_frases=len(huella.vectores),
        creada_en=huella.creada_en,
        vectores=huella.vectores if incluir_vectores else None,
    )


class AlmacenEspacio:
    """SQLite propio con una huella de referencia por (modelo, dimensiones, versión de frases)."""

    def __init__(self, ruta: Path, timeout_s: float = 5.0) -> None:
        self._ruta, self._timeout_s = ruta, timeout_s
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._conectar() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS referencias_espacio ("
                "modelo TEXT NOT NULL, dimensiones INTEGER NOT NULL, version_frases TEXT NOT NULL, "
                "carga TEXT NOT NULL, PRIMARY KEY (modelo, dimensiones, version_frases))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS referencias_espacio_historico ("
                "modelo TEXT NOT NULL, dimensiones INTEGER NOT NULL, version_frases TEXT NOT NULL, "
                "carga TEXT NOT NULL, retirada_en TEXT NOT NULL)"
            )

    @property
    def ruta(self) -> Path:
        return self._ruta

    @contextmanager
    def _conectar(self) -> Iterator[sqlite3.Connection]:
        conexion = sqlite3.connect(self._ruta, timeout=self._timeout_s)
        try:
            with conexion:
                yield conexion
        finally:
            conexion.close()

    def obtener(self, modelo: str, dimensiones: int, version_frases: str = VERSION_FRASES_CONTROL) -> HuellaEspacio | None:
        with self._conectar() as db:
            fila = db.execute(
                "SELECT carga FROM referencias_espacio WHERE modelo=? AND dimensiones=? AND version_frases=?",
                (modelo, dimensiones, version_frases),
            ).fetchone()
        return None if fila is None else HuellaEspacio.model_validate_json(fila[0])

    def registrar(self, huella: HuellaEspacio) -> HuellaEspacio:
        """Inserta la referencia si no existe; devuelve la que quede guardada (nunca sobrescribe)."""
        with self._conectar() as db:
            db.execute(
                "INSERT OR IGNORE INTO referencias_espacio VALUES (?, ?, ?, ?)",
                (huella.modelo, huella.dimensiones, huella.version_frases, huella.model_dump_json()),
            )
        guardada = self.obtener(huella.modelo, huella.dimensiones, huella.version_frases)
        assert guardada is not None
        return guardada

    def rotar(self, huella: HuellaEspacio, retirada_en: str) -> HuellaRetirada | None:
        """Guarda ``huella`` como referencia vigente y archiva la anterior (si la había) con fecha."""
        with self._conectar() as db:
            db.execute("BEGIN IMMEDIATE")
            fila = db.execute(
                "SELECT carga FROM referencias_espacio WHERE modelo=? AND dimensiones=? AND version_frases=?",
                (huella.modelo, huella.dimensiones, huella.version_frases),
            ).fetchone()
            if fila is not None:
                db.execute(
                    "INSERT INTO referencias_espacio_historico VALUES (?, ?, ?, ?, ?)",
                    (huella.modelo, huella.dimensiones, huella.version_frases, fila[0], retirada_en),
                )
            db.execute(
                "INSERT OR REPLACE INTO referencias_espacio VALUES (?, ?, ?, ?)",
                (huella.modelo, huella.dimensiones, huella.version_frases, huella.model_dump_json()),
            )
        if fila is None:
            return None
        return HuellaRetirada(huella=resumir(HuellaEspacio.model_validate_json(fila[0])), retirada_en=retirada_en)

    def listar_historico(self) -> tuple[HuellaRetirada, ...]:
        with self._conectar() as db:
            filas = db.execute(
                "SELECT carga, retirada_en FROM referencias_espacio_historico "
                "ORDER BY modelo, dimensiones, version_frases, retirada_en, rowid"
            ).fetchall()
        return tuple(HuellaRetirada(huella=resumir(HuellaEspacio.model_validate_json(carga)), retirada_en=fecha) for carga, fecha in filas)

    def listar(self) -> tuple[HuellaEspacio, ...]:
        with self._conectar() as db:
            filas = db.execute("SELECT carga FROM referencias_espacio ORDER BY modelo, dimensiones, version_frases").fetchall()
        return tuple(HuellaEspacio.model_validate_json(fila[0]) for fila in filas)


def verificar_espacio(proveedor: ProveedorEmbeddings, almacen: AlmacenEspacio, tolerancia: float = TOLERANCIA_POR_DEFECTO, ahora: Callable[[], str] = ahora_utc) -> ResultadoVerificacion:
    actual = calcular_huella(proveedor, ahora)
    referencia = almacen.obtener(actual.modelo, actual.dimensiones, actual.version_frases)
    if referencia is None:
        guardada = almacen.registrar(actual)
        if guardada.huella_id == actual.huella_id:
            return ResultadoVerificacion(
                estado="referencia_creada",
                modelo=actual.modelo,
                dimensiones=actual.dimensiones,
                version_frases=actual.version_frases,
                tolerancia=tolerancia,
                huella_referencia=guardada.huella_id,
                huella_actual=actual.huella_id,
                referencia_creada_en=guardada.creada_en,
            )
        referencia = guardada
    return comparar_huellas(referencia, actual, tolerancia)


def rotar_espacio(
    proveedor: ProveedorEmbeddings,
    almacen: AlmacenEspacio,
    ahora: Callable[[], str] = ahora_utc,
    invalidar: Callable[[str, int], int] | None = None,
) -> ResultadoRotacion:
    """Rotación explícita: la huella actual pasa a ser la referencia; la anterior queda archivada."""
    actual = calcular_huella(proveedor, ahora)
    try:
        invalidados = invalidar(actual.modelo, actual.dimensiones) if invalidar else 0
    except Exception as exc:
        raise ErrorInvalidacionEmbeddings("invalidacion_embeddings_fallida") from exc
    anterior = almacen.rotar(actual, ahora())
    return ResultadoRotacion(
        modelo=actual.modelo,
        dimensiones=actual.dimensiones,
        version_frases=actual.version_frases,
        referencia_nueva=resumir(actual),
        referencia_anterior=anterior,
        embeddings_invalidados=invalidados,
    )
