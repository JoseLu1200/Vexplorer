"""Mantenimiento automático del espacio de embeddings (ideas 2.5 y 2.6).

Tres piezas, todas en el SQLite propio ``precedentes_espacio.sqlite3`` (nada en ``contratos/``):

- ``CandadoPersistente``: candado con *lease* (expiración) e intervalo mínimo entre llamadas,
  seguro entre hilos y procesos. Sustituye al candado en memoria de cada proceso.
- ``RegistroEspacio``: sella cada embedding (por ``cache_key``) con la huella del espacio vigente
  cuando se genera, y recuerda qué ``cache_key`` tenía cada elemento de la biblioteca para marcar como
  reemplazado el anterior cuando se guarda una revisión nueva. Implementa ``ContextoEspacio``.
- ``tras_guardar_biblioteca``: único punto de enganche con el guardado de la biblioteca. Marca y sella
  siempre (solo SQLite local, con timeout corto); la regeneración en segundo plano es opcional, está
  desactivada salvo ``VEXPLORER_PRECEDENTES_REGENERACION_AUTO=1`` y solo actúa por motivos de espacio,
  sin cambiar nunca la revisión guardada.

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
from datetime import datetime
from pathlib import Path

from pydantic import Field

from backend.app.contratos.modelos import LibraryItem
from backend.app.precedentes.comun import ModeloEstricto
from backend.app.precedentes.espacio import (
    VERSION_FRASES_CONTROL,
    AlmacenEspacio,
    HuellaEspacio,
)
from backend.app.precedentes.regeneracion import (
    LatidoPerdido,
    ProveedorEmbeddings,
    RepositorioBiblioteca,
    Sello,
    ahora_utc,
    regenerar_obsoletos,
)

logger = logging.getLogger(__name__)

NOMBRE_BD_ESPACIO = "precedentes_espacio.sqlite3"
VARIABLE_REGENERACION_AUTO = "VEXPLORER_PRECEDENTES_REGENERACION_AUTO"
NOMBRE_CANDADO_REGENERACION = "regeneracion"
NOMBRE_CANDADO_ESPACIO = "espacio"
# Un elemento tarda como mucho un ``embed`` (30 s de timeout del proveedor); el lease se renueva antes
# de cada elemento y antes de cada escritura, así que basta con holgura sobre ese peor caso para que un
# proceso caído no bloquee más de unos minutos.
TTL_REGENERACION_S = 300.0
# Verificar o rotar hacen una ráfaga de ``embed`` (una por frase de control) sin punto de renovación.
TTL_ESPACIO_S = 300.0
# La parte síncrona del enganche (registro y sellado) no debe retrasar el guardado: si la BD está
# bloqueada más de esto, se omite con un aviso en el log.
TIMEOUT_ENGANCHE_S = 2.0
# Máximo de regeneraciones tras guardar pendientes de ejecutar; el exceso se descarta (la regeneración
# manual lo recoge).
COLA_MAXIMA = 16
MOTIVO_REVISION_REEMPLAZADA = "revision_reemplazada"


class OperacionEnCurso(RuntimeError):
    pass


class CandadoPerdido(OperacionEnCurso, LatidoPerdido):
    """El lease expiró y otro titular lo adquirió (o no se pudo renovar): hay que abandonar la operación."""


class CandadoNoDisponible(RuntimeError):
    """La BD de candados no responde (bloqueada o dañada): ni se adquiere ni se asume que esté libre."""


class IntervaloNoCumplido(RuntimeError):
    def __init__(self, espera_s: float) -> None:
        super().__init__(f"intervalo_minimo:{espera_s:.0f}")
        self.espera_s = espera_s


class EstadoCandado(ModeloEstricto):
    ocupado: bool
    expira_en: float | None = None
    ultima_llamada: float | None = None


@contextmanager
def _conexion(ruta: Path, timeout_s: float = 30.0) -> Iterator[sqlite3.Connection]:
    conexion = sqlite3.connect(ruta, timeout=timeout_s, isolation_level=None)
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


def _asegurar_columna(db: sqlite3.Connection, tabla: str, columna: str, definicion: str) -> None:
    """Migra esquemas antiguos. Las tablas nuevas ya declaran la columna en su CREATE TABLE; con varios
    procesos arrancando a la vez sobre un esquema antiguo, el perdedor de la carrera ve
    ``duplicate column name`` y basta con ignorarlo."""
    if columna in {fila[1] for fila in db.execute(f"PRAGMA table_info({tabla})")}:
        return
    try:
        db.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
    except sqlite3.OperationalError as exc:
        if "duplicate column" not in str(exc).lower():
            raise


def _lease_activo(titular: object, expira_en: float, ttl_s: float, ahora: float) -> bool:
    """Activo si no ha expirado y su expiración es coherente con su TTL (un salto atrás del reloj de
    pared dejaría ``expira_en`` muy en el futuro y el candado colgado: se considera expirado)."""
    return titular is not None and ahora < expira_en <= ahora + ttl_s


class Lease:
    def __init__(self, candado: CandadoPersistente, nombre: str, titular: str, ttl_s: float) -> None:
        self._candado, self._nombre, self._titular, self._ttl_s = candado, nombre, titular, ttl_s

    def renovar(self) -> None:
        """Extiende la expiración; ``CandadoPerdido`` si otro titular ya tomó el candado o no se puede renovar."""
        try:
            with _conexion(self._candado.ruta, self._candado.timeout_s) as db, _transaccion(db):
                ahora = self._candado.reloj()
                cur = db.execute(
                    "UPDATE candados SET expira_en=? WHERE nombre=? AND titular=? AND expira_en > ?",
                    (ahora + self._ttl_s, self._nombre, self._titular, ahora),
                )
                cambiadas = cur.rowcount
        except sqlite3.DatabaseError as exc:
            raise CandadoPerdido(f"{self._nombre}:no_renovable") from exc
        if cambiadas != 1:
            raise CandadoPerdido(self._nombre)


class CandadoPersistente:
    """Candado no bloqueante con lease en SQLite; una fila por nombre.

    ``reloj`` debe ser de pared (``time.time``): se compara entre procesos. La adquisición y la
    comprobación del intervalo mínimo ocurren en la misma transacción ``BEGIN IMMEDIATE``.
    """

    def __init__(self, ruta: Path, reloj: Callable[[], float] = time.time, timeout_s: float = 30.0) -> None:
        self.ruta, self.reloj, self.timeout_s = Path(ruta), reloj, timeout_s
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with _conexion(self.ruta, timeout_s) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS candados ("
                "nombre TEXT PRIMARY KEY, titular TEXT, expira_en REAL NOT NULL DEFAULT 0, ultima_llamada REAL, ttl_s REAL)"
            )
            _asegurar_columna(db, "candados", "ttl_s", "REAL")

    @contextmanager
    def ocupar(self, nombre: str, ttl_s: float, intervalo_minimo_s: float | None = None) -> Iterator[Lease]:
        """Adquiere el candado o lanza ``OperacionEnCurso``.

        Con ``intervalo_minimo_s`` (aunque sea 0) registra la llamada y lanza ``IntervaloNoCumplido`` si
        la anterior fue hace menos de ese tiempo; el intervalo sobrevive a la liberación del candado.
        Una BD bloqueada o ilegible lanza ``CandadoNoDisponible``.
        """
        titular = uuid.uuid4().hex
        try:
            with _conexion(self.ruta, self.timeout_s) as db, _transaccion(db):
                ahora = self.reloj()
                fila = db.execute("SELECT titular, expira_en, ultima_llamada, ttl_s FROM candados WHERE nombre=?", (nombre,)).fetchone()
                ultima = fila[2] if fila else None
                if fila and _lease_activo(fila[0], fila[1], fila[3] if fila[3] is not None else ttl_s, ahora):
                    raise OperacionEnCurso(nombre)
                if intervalo_minimo_s is not None:
                    # ``ultima`` posterior a ``ahora`` (reloj atrás) no puede bloquear más que el intervalo.
                    if ultima is not None and ultima <= ahora:
                        espera = max(0.0, intervalo_minimo_s - (ahora - ultima))
                        if espera > 0:
                            raise IntervaloNoCumplido(espera)
                    ultima = ahora
                db.execute(
                    "INSERT OR REPLACE INTO candados (nombre, titular, expira_en, ultima_llamada, ttl_s) VALUES (?, ?, ?, ?, ?)",
                    (nombre, titular, ahora + ttl_s, ultima, ttl_s),
                )
        except sqlite3.DatabaseError as exc:
            raise CandadoNoDisponible(str(exc)) from exc
        try:
            yield Lease(self, nombre, titular, ttl_s)
        finally:
            try:
                with _conexion(self.ruta, self.timeout_s) as db:
                    db.execute("UPDATE candados SET titular=NULL, expira_en=0 WHERE nombre=? AND titular=?", (nombre, titular))
            except sqlite3.DatabaseError:
                # La operación ya terminó: no se convierte en error. El lease expira solo.
                logger.warning("no se pudo liberar el candado %s; expirara por lease", nombre, exc_info=True)

    def estado(self, nombre: str) -> EstadoCandado:
        with _conexion(self.ruta, self.timeout_s) as db:
            fila = db.execute("SELECT titular, expira_en, ultima_llamada, ttl_s FROM candados WHERE nombre=?", (nombre,)).fetchone()
        if fila is None:
            return EstadoCandado(ocupado=False)
        ocupado = _lease_activo(fila[0], fila[1], fila[3] if fila[3] is not None else float("inf"), self.reloj())
        return EstadoCandado(ocupado=ocupado, expira_en=fila[1] if ocupado else None, ultima_llamada=fila[2])


class EmbeddingReemplazado(ModeloEstricto):
    cache_key: str = Field(min_length=1)
    library_item_id: str = Field(min_length=1)
    result_revision: int = Field(gt=0)
    motivo: str
    marcado_en: str


def _posterior(referencia_creada_en: str, generado_en: str | None) -> bool:
    """¿La referencia se creó después de generarse el vector? Si no se puede decidir, no bloquea."""
    if generado_en is None:
        return False
    try:
        return datetime.fromisoformat(referencia_creada_en) > datetime.fromisoformat(generado_en)
    except (ValueError, TypeError):
        return False


class RegistroEspacio:
    """Sellos de huella por ``cache_key`` y seguimiento del embedding vigente de cada elemento."""

    def __init__(self, almacen: AlmacenEspacio, ahora: Callable[[], str] = ahora_utc, timeout_s: float = 30.0) -> None:
        self._almacen, self._ahora, self._timeout_s = almacen, ahora, timeout_s
        with self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS sellos_embedding ("
                "cache_key TEXT PRIMARY KEY, modelo TEXT NOT NULL, dimensiones INTEGER NOT NULL, "
                "descriptor_version TEXT NOT NULL, huella_id TEXT NOT NULL, sellado_en TEXT NOT NULL, "
                "version_frases TEXT NOT NULL DEFAULT 'control-v1')"
            )
            _asegurar_columna(db, "sellos_embedding", "version_frases", "TEXT NOT NULL DEFAULT 'control-v1'")
            db.execute(
                "CREATE TABLE IF NOT EXISTS biblioteca_vigente ("
                "library_item_id TEXT PRIMARY KEY, cache_key TEXT, result_revision INTEGER NOT NULL, registrado_en TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS embeddings_reemplazados ("
                "cache_key TEXT NOT NULL, library_item_id TEXT NOT NULL, result_revision INTEGER NOT NULL, "
                "motivo TEXT NOT NULL, marcado_en TEXT NOT NULL, PRIMARY KEY (cache_key, library_item_id, result_revision))"
            )

    def _db(self):
        return _conexion(self._almacen.ruta, self._timeout_s)

    # -- ContextoEspacio ---------------------------------------------------------------------
    def referencia_vigente(self, modelo: str, dimensiones: int) -> Sello | None:
        referencia = self._almacen.obtener(modelo, dimensiones)
        return None if referencia is None else Sello(referencia.huella_id, referencia.version_frases)

    def sello(self, cache_key: str) -> Sello | None:
        with self._db() as db:
            fila = db.execute("SELECT huella_id, version_frases FROM sellos_embedding WHERE cache_key=?", (cache_key,)).fetchone()
        return None if fila is None else Sello(fila[0], fila[1])

    def sellar(
        self,
        cache_key: str,
        modelo: str,
        dimensiones: int,
        descriptor_version: str,
        huella_esperada: str | None = None,
        generado_en: str | None = None,
    ) -> bool:
        """Sella el vector con la referencia vigente; no hace nada (ni llama al proveedor) si no existe.

        Si se conoce la huella vigente al empezar a generar (``huella_esperada``) y ha cambiado, o la
        referencia se creó después de generarse el vector (``generado_en``), no se sella y se borra el
        sello anterior: el vector queda *desconocido* en lugar de atribuirse a una huella equivocada.
        """
        with self._db() as db, _transaccion(db):
            fila = db.execute(
                "SELECT carga FROM referencias_espacio "
                "WHERE modelo=? AND dimensiones=? AND version_frases=?",
                (modelo, dimensiones, VERSION_FRASES_CONTROL),
            ).fetchone()
            if fila is None:
                return False
            referencia = HuellaEspacio.model_validate_json(fila[0])
            valido = (
                huella_esperada is None or referencia.huella_id == huella_esperada
            ) and not _posterior(referencia.creada_en, generado_en)
            if not valido:
                db.execute("DELETE FROM sellos_embedding WHERE cache_key=?", (cache_key,))
                return False
            db.execute(
                "INSERT OR REPLACE INTO sellos_embedding (cache_key, modelo, dimensiones, descriptor_version, huella_id, sellado_en, version_frases) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cache_key, modelo, dimensiones, descriptor_version, referencia.huella_id, self._ahora(), referencia.version_frases),
            )
        return True

    # -- seguimiento de la biblioteca ---------------------------------------------------------
    def registrar_guardado(self, item: LibraryItem) -> EmbeddingReemplazado | None:
        """Anota el embedding vigente del elemento y marca como reemplazado el anterior si cambió."""
        nueva = item.embedding.cache_key if item.embedding is not None else None
        marca: EmbeddingReemplazado | None = None
        with self._db() as db, _transaccion(db):
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

    def revision_vigente(self, library_item_id: str) -> int | None:
        with self._db() as db:
            fila = db.execute("SELECT result_revision FROM biblioteca_vigente WHERE library_item_id=?", (library_item_id,)).fetchone()
        return None if fila is None else fila[0]

    def listar_reemplazados(self) -> tuple[EmbeddingReemplazado, ...]:
        with self._db() as db:
            filas = db.execute(
                "SELECT cache_key, library_item_id, result_revision, motivo, marcado_en FROM embeddings_reemplazados "
                "ORDER BY marcado_en, library_item_id, result_revision, cache_key"
            ).fetchall()
        return tuple(EmbeddingReemplazado(cache_key=f[0], library_item_id=f[1], result_revision=f[2], motivo=f[3], marcado_en=f[4]) for f in filas)


# ------------------------------------------------------------------------- cola de fondo


class ColaMantenimiento:
    """Cola de fondo de un solo hilo, acotada (``COLA_MAXIMA``) y deduplicada por clave.

    Es una instancia, no un global: cada app (``create_app``) tiene la suya, de modo que apagar una no
    cancela el trabajo de otra en el mismo proceso. ``tras_guardar_biblioteca`` usa ``COLA_PROCESO``
    cuando no se le pasa una.
    """

    def __init__(self) -> None:
        self._cerrojo = threading.Lock()
        self._ejecutor: ThreadPoolExecutor | None = None
        self._pendientes: set[str] = set()
        self.detener = threading.Event()

    def encolar(self, clave: str, tarea: Callable[[], None]) -> None:
        """Una tarea cuenta como pendiente hasta que empieza a ejecutarse: si se guarda de nuevo el
        mismo elemento mientras corre, se encola otra. El exceso se descarta con un aviso."""
        with self._cerrojo:
            if clave in self._pendientes:
                return
            if len(self._pendientes) >= COLA_MAXIMA:
                logger.warning("cola de regeneracion llena; se omite %s", clave)
                return
            if self._ejecutor is None:
                self._ejecutor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="precedentes-regeneracion")
            ejecutor, pendientes, detener = self._ejecutor, self._pendientes, self.detener
            pendientes.add(clave)

        def ejecutar() -> None:
            try:
                if not detener.is_set():
                    tarea()
            finally:
                with self._cerrojo:
                    pendientes.discard(clave)

        ejecutor.submit(ejecutar)

    def pendientes(self) -> int:
        with self._cerrojo:
            return len(self._pendientes)

    def esperar(self, timeout_s: float = 30.0) -> None:
        """Bloquea hasta que termine lo ya encolado (cola FIFO de un hilo); para tests."""
        with self._cerrojo:
            sentinela = None if self._ejecutor is None else self._ejecutor.submit(lambda: None)
        if sentinela is not None:
            sentinela.result(timeout_s)

    def apagar(self) -> None:
        """Descarta lo pendiente y avisa a la tarea en curso (aborta en su siguiente latido); no espera a
        una llamada al proveedor ya iniciada. La cola queda reutilizable."""
        with self._cerrojo:
            ejecutor, detener = self._ejecutor, self.detener
            self._ejecutor, self._pendientes, self.detener = None, set(), threading.Event()
        detener.set()
        if ejecutor is not None:
            ejecutor.shutdown(wait=False, cancel_futures=True)


COLA_PROCESO = ColaMantenimiento()


def pendientes() -> int:
    return COLA_PROCESO.pendientes()


def esperar_pendientes(timeout_s: float = 30.0) -> None:
    COLA_PROCESO.esperar(timeout_s)


def apagar_mantenimiento() -> None:
    COLA_PROCESO.apagar()


# ------------------------------------------------------------------------- enganche tras guardar


def regeneracion_auto_activada() -> bool:
    return os.getenv(VARIABLE_REGENERACION_AUTO, "").strip().lower() in {"1", "true", "yes", "on"}


def regenerar_elemento_en_segundo_plano(
    ruta: Path,
    repositorio: RepositorioBiblioteca,
    proveedor: ProveedorEmbeddings,
    library_item_id: str,
    detener: threading.Event | None = None,
) -> None:
    """Regenera solo ese elemento si su espacio está obsoleto, conservando la revisión guardada.

    Se salta sin error si el candado está ocupado o la BD no responde.
    """
    try:
        registro = RegistroEspacio(AlmacenEspacio(ruta))
        with CandadoPersistente(ruta).ocupar(NOMBRE_CANDADO_REGENERACION, TTL_REGENERACION_S) as lease:

            def latido() -> None:
                if detener is not None and detener.is_set():
                    raise CandadoPerdido("apagado")
                lease.renovar()

            informe = regenerar_obsoletos(
                repositorio, proveedor, False, 1, contexto=registro, latido=latido,
                solo_ids=frozenset({library_item_id}), conservar_revision=True,
            )
            if informe.abortado:
                logger.info("regeneracion tras guardar abortada (%s)", library_item_id)
    except (OperacionEnCurso, CandadoNoDisponible):
        logger.info("regeneracion tras guardar omitida: candado ocupado o no disponible (%s)", library_item_id)
    except Exception:
        logger.warning("regeneracion tras guardar fallida (%s)", library_item_id, exc_info=True)


def tras_guardar_biblioteca(
    root: Path,
    repositorio: RepositorioBiblioteca,
    proveedor: ProveedorEmbeddings | None,
    item: LibraryItem,
    cola: ColaMantenimiento | None = None,
) -> None:
    """Enganche único tras ``save_library_item``. Nunca lanza: no puede alterar la respuesta del guardado.

    1. Anota el embedding vigente del elemento y marca el anterior como reemplazado.
    2. Si el vector se acaba de generar, lo sella con la huella vigente (si hay referencia y no se
       creó después de generarse el vector).
    3. Con ``VEXPLORER_PRECEDENTES_REGENERACION_AUTO`` y un item semántico, encola en segundo plano su
       regeneración si su espacio está obsoleto (p. ej. cache hit de un espacio retirado), sin cambiar
       la revisión guardada. Los items offline (sin embedding) nunca llaman al proveedor.

    La parte síncrona usa un timeout corto (``TIMEOUT_ENGANCHE_S``): si la BD está bloqueada se omite.
    """
    try:
        ruta = Path(root) / NOMBRE_BD_ESPACIO
        registro = RegistroEspacio(AlmacenEspacio(ruta, timeout_s=TIMEOUT_ENGANCHE_S), timeout_s=TIMEOUT_ENGANCHE_S)
        registro.registrar_guardado(item)
        metadatos = item.embedding
        if metadatos is None:
            return
        if metadatos.status == "generated":
            registro.sellar(metadatos.cache_key, metadatos.model, metadatos.dimensions, metadatos.descriptor_version, generado_en=item.created_at)
        if proveedor is not None and regeneracion_auto_activada():
            cola = cola or COLA_PROCESO
            detener = cola.detener
            cola.encolar(item.id, lambda: regenerar_elemento_en_segundo_plano(ruta, repositorio, proveedor, item.id, detener))
    except Exception:
        logger.warning("mantenimiento tras guardar omitido (%s)", item.id, exc_info=True)
