"""Mantenimiento automático del espacio de embeddings (ideas 2.5 y 2.6).

Tres piezas, todas en el SQLite propio ``precedentes_espacio.sqlite3`` (nada en ``contratos/``):

- ``CandadoPersistente``: candado con *lease* (expiración) e intervalo mínimo entre llamadas,
  seguro entre hilos y procesos. Sustituye al candado en memoria de cada proceso.
- ``RegistroEspacio``: sella cada embedding (por ``cache_key``) con la huella del espacio vigente
  cuando se genera, y recuerda qué ``cache_key`` tenía cada elemento de la biblioteca para marcar como
  reemplazado el anterior cuando se guarda una revisión nueva. Implementa ``ContextoEspacio``.
- ``tras_guardar_biblioteca``: único punto de enganche con el guardado de la biblioteca. Marca y sella
  siempre (solo SQLite local, sin proveedor); la regeneración en segundo plano es opcional y está
  desactivada salvo ``VEXPLORER_PRECEDENTES_REGENERACION_AUTO=1``.

Limitación asumida: el sello afirma que el vector se generó bajo la referencia vigente en ese momento;
es tan fiable como la disciplina de verificar y rotar la referencia cuando el proveedor cambia.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from pydantic import Field

from backend.app.contratos.modelos import LibraryItem
from backend.app.precedentes.comun import ModeloEstricto
from backend.app.precedentes.espacio import AlmacenEspacio
from backend.app.precedentes.regeneracion import (
    ProveedorEmbeddings,
    RepositorioBiblioteca,
    ahora_utc,
    regenerar_obsoletos,
)

logger = logging.getLogger(__name__)

NOMBRE_BD_ESPACIO = "precedentes_espacio.sqlite3"
VARIABLE_REGENERACION_AUTO = "VEXPLORER_PRECEDENTES_REGENERACION_AUTO"
NOMBRE_CANDADO_REGENERACION = "regeneracion"
NOMBRE_CANDADO_ESPACIO = "espacio"
# Un elemento tarda como mucho un ``embed`` (30 s de timeout del proveedor); el lease se renueva antes
# de cada elemento, así que basta con holgura sobre ese peor caso para que un proceso caído no bloquee
# más de unos minutos.
TTL_REGENERACION_S = 300.0
# Verificar o rotar hacen una ráfaga de ``embed`` (una por frase de control) sin punto de renovación.
TTL_ESPACIO_S = 300.0
MOTIVO_REVISION_REEMPLAZADA = "revision_reemplazada"


class OperacionEnCurso(RuntimeError):
    pass


class CandadoPerdido(OperacionEnCurso):
    """El lease expiró y otro titular lo adquirió: hay que abandonar la operación."""


class IntervaloNoCumplido(RuntimeError):
    def __init__(self, espera_s: float) -> None:
        super().__init__(f"intervalo_minimo:{espera_s:.0f}")
        self.espera_s = espera_s


class EstadoCandado(ModeloEstricto):
    ocupado: bool
    expira_en: float | None = None
    ultima_llamada: float | None = None


@contextmanager
def _conexion(ruta: Path) -> Iterator[sqlite3.Connection]:
    conexion = sqlite3.connect(ruta, timeout=30, isolation_level=None)
    try:
        yield conexion
    finally:
        conexion.close()


@contextmanager
def _transaccion(conexion: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conexion.execute("BEGIN IMMEDIATE")
    try:
        yield conexion
    except BaseException:
        conexion.execute("ROLLBACK")
        raise
    conexion.execute("COMMIT")


class Lease:
    def __init__(self, candado: CandadoPersistente, nombre: str, titular: str, ttl_s: float) -> None:
        self._candado, self._nombre, self._titular, self._ttl_s = candado, nombre, titular, ttl_s

    def renovar(self) -> None:
        """Extiende la expiración; ``CandadoPerdido`` si otro titular ya tomó el candado."""
        with _conexion(self._candado.ruta) as db:
            cambiadas = db.execute(
                "UPDATE candados SET expira_en=? WHERE nombre=? AND titular=?",
                (self._candado.reloj() + self._ttl_s, self._nombre, self._titular),
            ).rowcount
        if cambiadas == 0:
            raise CandadoPerdido(self._nombre)


class CandadoPersistente:
    """Candado no bloqueante con lease en SQLite; una fila por nombre.

    ``reloj`` debe ser de pared (``time.time``): se compara entre procesos. La adquisición y la
    comprobación del intervalo mínimo ocurren en la misma transacción ``BEGIN IMMEDIATE``.
    """

    def __init__(self, ruta: Path, reloj: Callable[[], float] = time.time) -> None:
        self.ruta, self.reloj = Path(ruta), reloj
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with _conexion(self.ruta) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS candados ("
                "nombre TEXT PRIMARY KEY, titular TEXT, expira_en REAL NOT NULL DEFAULT 0, ultima_llamada REAL)"
            )

    @contextmanager
    def ocupar(self, nombre: str, ttl_s: float, intervalo_minimo_s: float | None = None) -> Iterator[Lease]:
        """Adquiere el candado o lanza ``OperacionEnCurso``.

        Con ``intervalo_minimo_s`` (aunque sea 0) registra la llamada y lanza ``IntervaloNoCumplido`` si
        la anterior fue hace menos de ese tiempo; el intervalo sobrevive a la liberación del candado.
        """
        titular = uuid.uuid4().hex
        with _conexion(self.ruta) as db, _transaccion(db):
            ahora = self.reloj()
            fila = db.execute("SELECT titular, expira_en, ultima_llamada FROM candados WHERE nombre=?", (nombre,)).fetchone()
            ultima = fila[2] if fila else None
            if fila and fila[0] is not None and fila[1] > ahora:
                raise OperacionEnCurso(nombre)
            if intervalo_minimo_s is not None:
                if ultima is not None:
                    espera = max(0.0, intervalo_minimo_s - (ahora - ultima))
                    if espera > 0:
                        raise IntervaloNoCumplido(espera)
                ultima = ahora
            db.execute(
                "INSERT OR REPLACE INTO candados (nombre, titular, expira_en, ultima_llamada) VALUES (?, ?, ?, ?)",
                (nombre, titular, ahora + ttl_s, ultima),
            )
        try:
            yield Lease(self, nombre, titular, ttl_s)
        finally:
            with _conexion(self.ruta) as db:
                db.execute("UPDATE candados SET titular=NULL, expira_en=0 WHERE nombre=? AND titular=?", (nombre, titular))

    def estado(self, nombre: str) -> EstadoCandado:
        with _conexion(self.ruta) as db:
            fila = db.execute("SELECT titular, expira_en, ultima_llamada FROM candados WHERE nombre=?", (nombre,)).fetchone()
        if fila is None:
            return EstadoCandado(ocupado=False)
        ocupado = fila[0] is not None and fila[1] > self.reloj()
        return EstadoCandado(ocupado=ocupado, expira_en=fila[1] if ocupado else None, ultima_llamada=fila[2])


class EmbeddingReemplazado(ModeloEstricto):
    cache_key: str = Field(min_length=1)
    library_item_id: str = Field(min_length=1)
    result_revision: int = Field(gt=0)
    motivo: str
    marcado_en: str


class RegistroEspacio:
    """Sellos de huella por ``cache_key`` y seguimiento del embedding vigente de cada elemento."""

    def __init__(self, almacen: AlmacenEspacio, ahora: Callable[[], str] = ahora_utc) -> None:
        self._almacen, self._ahora = almacen, ahora
        with _conexion(almacen.ruta) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS sellos_embedding ("
                "cache_key TEXT PRIMARY KEY, modelo TEXT NOT NULL, dimensiones INTEGER NOT NULL, "
                "descriptor_version TEXT NOT NULL, huella_id TEXT NOT NULL, sellado_en TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS biblioteca_vigente ("
                "library_item_id TEXT PRIMARY KEY, cache_key TEXT, result_revision INTEGER NOT NULL, registrado_en TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS embeddings_reemplazados ("
                "cache_key TEXT NOT NULL, library_item_id TEXT NOT NULL, result_revision INTEGER NOT NULL, "
                "motivo TEXT NOT NULL, marcado_en TEXT NOT NULL, PRIMARY KEY (cache_key, library_item_id, result_revision))"
            )

    # -- ContextoEspacio ---------------------------------------------------------------------
    def huella_vigente(self, modelo: str, dimensiones: int) -> str | None:
        referencia = self._almacen.obtener(modelo, dimensiones)
        return None if referencia is None else referencia.huella_id

    def sello(self, cache_key: str) -> str | None:
        with _conexion(self._almacen.ruta) as db:
            fila = db.execute("SELECT huella_id FROM sellos_embedding WHERE cache_key=?", (cache_key,)).fetchone()
        return None if fila is None else fila[0]

    def sellar_vigente(self, cache_key: str, modelo: str, dimensiones: int, descriptor_version: str) -> bool:
        """Sella el vector con la referencia vigente; no hace nada (ni llama al proveedor) si no existe."""
        huella = self.huella_vigente(modelo, dimensiones)
        if huella is None:
            return False
        with _conexion(self._almacen.ruta) as db:
            db.execute(
                "INSERT OR REPLACE INTO sellos_embedding VALUES (?, ?, ?, ?, ?, ?)",
                (cache_key, modelo, dimensiones, descriptor_version, huella, self._ahora()),
            )
        return True

    # -- seguimiento de la biblioteca ---------------------------------------------------------
    def registrar_guardado(self, item: LibraryItem) -> EmbeddingReemplazado | None:
        """Anota el embedding vigente del elemento y marca como reemplazado el anterior si cambió."""
        nueva = item.embedding.cache_key if item.embedding is not None else None
        marca: EmbeddingReemplazado | None = None
        with _conexion(self._almacen.ruta) as db, _transaccion(db):
            fila = db.execute("SELECT cache_key, result_revision FROM biblioteca_vigente WHERE library_item_id=?", (item.id,)).fetchone()
            ahora = self._ahora()
            if fila is not None and fila[0] is not None and fila[0] != nueva:
                marca = EmbeddingReemplazado(cache_key=fila[0], library_item_id=item.id, result_revision=fila[1], motivo=MOTIVO_REVISION_REEMPLAZADA, marcado_en=ahora)
                db.execute(
                    "INSERT OR IGNORE INTO embeddings_reemplazados VALUES (?, ?, ?, ?, ?)",
                    (marca.cache_key, marca.library_item_id, marca.result_revision, marca.motivo, marca.marcado_en),
                )
            if fila is not None or nueva is not None:
                db.execute("INSERT OR REPLACE INTO biblioteca_vigente VALUES (?, ?, ?, ?)", (item.id, nueva, item.result_revision, ahora))
        return marca

    def listar_reemplazados(self) -> tuple[EmbeddingReemplazado, ...]:
        with _conexion(self._almacen.ruta) as db:
            filas = db.execute(
                "SELECT cache_key, library_item_id, result_revision, motivo, marcado_en FROM embeddings_reemplazados "
                "ORDER BY marcado_en, library_item_id, result_revision, cache_key"
            ).fetchall()
        return tuple(EmbeddingReemplazado(cache_key=f[0], library_item_id=f[1], result_revision=f[2], motivo=f[3], marcado_en=f[4]) for f in filas)


# ------------------------------------------------------------------------- enganche tras guardar

_EJECUTOR: ThreadPoolExecutor | None = None
_CERROJO_EJECUTOR = threading.Lock()


def _encolar(tarea: Callable[[], None]) -> None:
    """Un solo hilo de fondo: las regeneraciones tras guardar se serializan y no bloquean la respuesta."""
    global _EJECUTOR
    with _CERROJO_EJECUTOR:
        if _EJECUTOR is None:
            _EJECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="precedentes-regeneracion")
        _EJECUTOR.submit(tarea)


def esperar_pendientes(timeout_s: float = 30.0) -> None:
    """Bloquea hasta que termine lo ya encolado (cola FIFO de un hilo); para tests y apagado ordenado."""
    with _CERROJO_EJECUTOR:
        ejecutor = _EJECUTOR
        sentinela = ejecutor.submit(lambda: None) if ejecutor is not None else None
    if sentinela is not None:
        sentinela.result(timeout_s)


def regeneracion_auto_activada() -> bool:
    return os.getenv(VARIABLE_REGENERACION_AUTO, "").strip().lower() in {"1", "true", "yes", "on"}


def regenerar_elemento_en_segundo_plano(ruta: Path, repositorio: RepositorioBiblioteca, proveedor: ProveedorEmbeddings, library_item_id: str) -> None:
    """Regenera solo ese elemento si está obsoleto; se salta sin error si el candado está ocupado."""
    try:
        registro = RegistroEspacio(AlmacenEspacio(ruta))
        with CandadoPersistente(ruta).ocupar(NOMBRE_CANDADO_REGENERACION, TTL_REGENERACION_S) as lease:
            regenerar_obsoletos(repositorio, proveedor, False, 1, contexto=registro, latido=lease.renovar, solo_ids=frozenset({library_item_id}))
    except OperacionEnCurso:
        logger.info("regeneracion tras guardar omitida: candado ocupado (%s)", library_item_id)
    except Exception:
        logger.warning("regeneracion tras guardar fallida (%s)", library_item_id, exc_info=True)


def tras_guardar_biblioteca(root: Path, repositorio: RepositorioBiblioteca, proveedor: ProveedorEmbeddings | None, item: LibraryItem) -> None:
    """Enganche único tras ``save_library_item``. Nunca lanza: no puede alterar la respuesta del guardado.

    1. Anota el embedding vigente del elemento y marca el anterior como reemplazado.
    2. Si el vector se acaba de generar, lo sella con la huella vigente (si hay referencia).
    3. Con ``VEXPLORER_PRECEDENTES_REGENERACION_AUTO`` y un item semántico, encola en segundo plano su
       regeneración si está obsoleto (p. ej. cache hit de un espacio retirado). Los items offline
       (sin embedding) nunca llaman al proveedor.
    """
    try:
        ruta = Path(root) / NOMBRE_BD_ESPACIO
        registro = RegistroEspacio(AlmacenEspacio(ruta))
        registro.registrar_guardado(item)
        metadatos = item.embedding
        if metadatos is None:
            return
        if metadatos.status == "generated":
            registro.sellar_vigente(metadatos.cache_key, metadatos.model, metadatos.dimensions, metadatos.descriptor_version)
        if proveedor is not None and regeneracion_auto_activada():
            _encolar(lambda: regenerar_elemento_en_segundo_plano(ruta, repositorio, proveedor, item.id))
    except Exception:
        logger.warning("mantenimiento tras guardar fallido (%s)", item.id, exc_info=True)
