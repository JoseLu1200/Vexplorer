"""Idea 3.5: herrajes y mecanizados por precedentes (solo mecanismo).

No existe aún un histórico real de herrajes. Este módulo define un almacén
propio (SQLite separado del histórico, sin tocar ``HistoricalRecord``) que asocia
a cada ``record_id`` del histórico una lista de herrajes/mecanizados con su
origen y procedencia, y una agregación pura que, a partir de los comparables de
un objetivo, sugiere qué herrajes suele llevar un mueble parecido.

Cada sugerencia es una hipótesis con soporte n/N; por debajo del mínimo se
abstiene. Nunca se presentan datos sintéticos como reales.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path
from statistics import median
from typing import Literal

from pydantic import Field, field_validator, model_validator

from backend.app.historico.models import HistoricalComparable, HistoricalTarget
from backend.app.historico.real_service import HistoricalStore
from backend.app.precedentes.comun import ModeloEstricto, normalizar_texto

Origen = Literal["actual", "published", "synthetic"]


class ProcedenciaHerrajes(ModeloEstricto):
    fuente: str = Field(min_length=1, max_length=500)
    fecha: date


class HerrajeMecanizado(ModeloEstricto):
    tipo: str = Field(min_length=1, max_length=200)
    cantidad: int | None = Field(default=None, gt=0, le=100_000)
    por_unidad_de: str | None = Field(default=None, min_length=1, max_length=100)
    notas: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("tipo", mode="after")
    @classmethod
    def _tipo_normalizado(cls, valor: str) -> str:
        limpio = normalizar_texto(valor)
        if limpio is None:
            raise ValueError("tipo vacío")
        return limpio

    @field_validator("por_unidad_de", mode="after")
    @classmethod
    def _unidad_normalizada(cls, valor: str | None) -> str | None:
        return normalizar_texto(valor)


class RegistroHerrajes(ModeloEstricto):
    record_id: str = Field(min_length=1, max_length=200)
    origen: Origen
    procedencia: ProcedenciaHerrajes
    herrajes: tuple[HerrajeMecanizado, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _canonico(self) -> RegistroHerrajes:
        claves = [(item.tipo, item.por_unidad_de or "") for item in self.herrajes]
        if len(claves) != len(set(claves)):
            raise ValueError("tipo y por_unidad_de duplicados en el mismo registro")
        ordenados = tuple(
            sorted(self.herrajes, key=lambda item: (item.tipo, item.por_unidad_de or ""))
        )
        if ordenados != self.herrajes:
            object.__setattr__(self, "herrajes", ordenados)
        return self

    def huella(self) -> str:
        texto = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class ImportacionHerrajes(ModeloEstricto):
    registros: tuple[RegistroHerrajes, ...] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _ids_unicos(self) -> ImportacionHerrajes:
        ids = [item.record_id for item in self.registros]
        if len(ids) != len(set(ids)):
            raise ValueError("record_id duplicado en la importación")
        return self


class ResultadoImportacionHerrajes(ModeloEstricto):
    insertados: int
    actualizados: int
    sin_cambios: int


class PaginaHerrajes(ModeloEstricto):
    items: tuple[RegistroHerrajes, ...]
    total: int
    limite: int
    desplazamiento: int


@contextmanager
def _conexion(ruta: Path, timeout_s: float = 10.0) -> Iterator[sqlite3.Connection]:
    conexion = sqlite3.connect(ruta, timeout=timeout_s, isolation_level=None)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA busy_timeout=10000")
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


class AlmacenHerrajes:
    """SQLite propio de herrajes, separado de la base del histórico."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._conexion() as db, _transaccion(db):
            db.execute(
                "CREATE TABLE IF NOT EXISTS herrajes_registros ("
                "record_id TEXT PRIMARY KEY, origen TEXT NOT NULL, "
                "huella TEXT NOT NULL, payload TEXT NOT NULL)"
            )

    @contextmanager
    def _conexion(self) -> Iterator[sqlite3.Connection]:
        with _conexion(self.ruta) as db:
            yield db

    def _conectar(self) -> sqlite3.Connection:
        conexion = sqlite3.connect(self.ruta, timeout=10)
        conexion.row_factory = sqlite3.Row
        return conexion

    def importar(self, valor: ImportacionHerrajes) -> ResultadoImportacionHerrajes:
        insertados = actualizados = sin_cambios = 0
        with self._conexion() as db, _transaccion(db):
            for registro in valor.registros:
                huella = registro.huella()
                fila = db.execute(
                    "SELECT huella FROM herrajes_registros WHERE record_id = ?",
                    (registro.record_id,),
                ).fetchone()
                if fila is not None and fila["huella"] == huella:
                    sin_cambios += 1
                    continue
                db.execute(
                    "INSERT OR REPLACE INTO herrajes_registros "
                    "(record_id, origen, huella, payload) VALUES (?, ?, ?, ?)",
                    (
                        registro.record_id,
                        registro.origen,
                        huella,
                        registro.model_dump_json(),
                    ),
                )
                if fila is None:
                    insertados += 1
                else:
                    actualizados += 1
        return ResultadoImportacionHerrajes(
            insertados=insertados, actualizados=actualizados, sin_cambios=sin_cambios
        )

    def listar(self, *, limite: int = 100, desplazamiento: int = 0) -> PaginaHerrajes:
        with self._conexion() as db:
            total = db.execute("SELECT COUNT(*) FROM herrajes_registros").fetchone()[0]
            filas = db.execute(
                "SELECT payload FROM herrajes_registros ORDER BY record_id LIMIT ? OFFSET ?",
                (limite, desplazamiento),
            ).fetchall()
        return PaginaHerrajes(
            items=tuple(RegistroHerrajes.model_validate_json(f["payload"]) for f in filas),
            total=total,
            limite=limite,
            desplazamiento=desplazamiento,
        )

    def obtener(self, record_ids: tuple[str, ...]) -> dict[str, RegistroHerrajes]:
        if not record_ids:
            return {}
        marcadores = ",".join("?" for _ in record_ids)
        with self._conexion() as db:
            filas = db.execute(
                f"SELECT record_id, payload FROM herrajes_registros "
                f"WHERE record_id IN ({marcadores})",
                record_ids,
            ).fetchall()
        return {
            f["record_id"]: RegistroHerrajes.model_validate_json(f["payload"])
            for f in filas
        }


# --- Sugerencias -----------------------------------------------------------


class SolicitudSugerenciasHerrajes(ModeloEstricto):
    objetivo: HistoricalTarget
    limite: int = Field(default=10, ge=1, le=50)
    incluir_sinteticos: bool = False
    minimo_soporte: int = Field(default=2, ge=1, le=50)
    proporcion_minima: float = Field(default=0.5, gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def minimo_alcanzable(self) -> SolicitudSugerenciasHerrajes:
        if self.minimo_soporte > self.limite:
            raise ValueError(
                "minimo_soporte no puede superar limite: la abstención sería segura"
            )
        return self


class EstadisticaCantidad(ModeloEstricto):
    por_unidad_de: str | None
    n: int
    mediana: float
    minimo: int
    maximo: int


class SugerenciaHerraje(ModeloEstricto):
    tipo: str
    estado: Literal["hipotesis", "abstencion"]
    soporte: int
    total_con_datos: int
    soporte_texto: str
    cantidades: tuple[EstadisticaCantidad, ...]
    record_ids: tuple[str, ...]
    origenes: dict[str, int]
    solo_sintetico: bool
    motivo_abstencion: str | None = None


class ResultadoSugerenciasHerrajes(ModeloEstricto):
    naturaleza: Literal["hipotesis"] = "hipotesis"
    comparables_recuperados: int
    comparables_con_datos: int
    record_ids_sin_datos: tuple[str, ...]
    minimo_soporte: int
    proporcion_minima: float
    sugerencias: tuple[SugerenciaHerraje, ...]
    avisos: tuple[str, ...]


def _origen_efectivo(origen_registro: str, origen_herrajes: str) -> str:
    """El origen menos fiable de los dos: sintético > publicado > real."""
    rango = {"actual": 0, "published": 1, "synthetic": 2}
    return max(origen_registro, origen_herrajes, key=lambda valor: rango[valor])


def agregar_sugerencias(
    comparables: tuple[HistoricalComparable, ...],
    registros: dict[str, RegistroHerrajes],
    *,
    minimo_soporte: int,
    incluir_sinteticos: bool,
    proporcion_minima: float = 0.5,
) -> ResultadoSugerenciasHerrajes:
    """Cruza comparables con herrajes y calcula soporte y cantidades. Función pura."""
    con_datos: list[tuple[str, str, RegistroHerrajes]] = []
    sin_datos: list[str] = []
    descartados_sinteticos = 0
    for comparable in sorted(comparables, key=lambda item: item.record.record_id):
        record_id = comparable.record.record_id
        registro = registros.get(record_id)
        if registro is None:
            sin_datos.append(record_id)
            continue
        if not incluir_sinteticos and registro.origen == "synthetic":
            descartados_sinteticos += 1
            sin_datos.append(record_id)
            continue
        con_datos.append(
            (record_id, _origen_efectivo(comparable.record.origin, registro.origen), registro)
        )

    total = len(con_datos)
    por_tipo: dict[str, list[tuple[str, str, HerrajeMecanizado]]] = {}
    for record_id, origen, registro in con_datos:
        for herraje in registro.herrajes:
            por_tipo.setdefault(herraje.tipo, []).append((record_id, origen, herraje))

    sugerencias: list[SugerenciaHerraje] = []
    for tipo in sorted(por_tipo):
        entradas = por_tipo[tipo]
        ids = tuple(sorted({record_id for record_id, _, _ in entradas}))
        origen_por_id = {record_id: origen for record_id, origen, _ in entradas}
        origenes: dict[str, int] = {}
        for origen in origen_por_id.values():
            origenes[origen] = origenes.get(origen, 0) + 1
        cantidades_por_unidad: dict[str, list[int]] = {}
        for _, _, herraje in entradas:
            if herraje.cantidad is not None:
                cantidades_por_unidad.setdefault(herraje.por_unidad_de or "", []).append(
                    herraje.cantidad
                )
        soporte = len(ids)
        motivos: list[str] = []
        if soporte < minimo_soporte:
            motivos.append(f"Soporte {soporte} inferior al mínimo {minimo_soporte}.")
        if total and soporte / total < proporcion_minima:
            motivos.append(
                f"Proporción {soporte}/{total} inferior a la mínima {proporcion_minima}."
            )
        abstiene = bool(motivos)
        cantidades = (
            ()
            if abstiene
            else tuple(
                EstadisticaCantidad(
                    por_unidad_de=unidad or None,
                    n=len(valores),
                    mediana=float(median(valores)),
                    minimo=min(valores),
                    maximo=max(valores),
                )
                for unidad, valores in sorted(cantidades_por_unidad.items())
            )
        )
        sugerencias.append(
            SugerenciaHerraje(
                tipo=tipo,
                estado="abstencion" if abstiene else "hipotesis",
                soporte=soporte,
                total_con_datos=total,
                soporte_texto=f"{soporte}/{total}",
                cantidades=cantidades,
                record_ids=ids,
                origenes=dict(sorted(origenes.items())),
                solo_sintetico=set(origenes) == {"synthetic"},
                motivo_abstencion=" ".join(motivos) if abstiene else None,
            )
        )
    sugerencias.sort(key=lambda item: (-item.soporte, item.tipo))

    avisos: list[str] = []
    if total == 0:
        avisos.append("Ningún comparable tiene datos de herrajes: no se sugiere nada.")
    if descartados_sinteticos:
        avisos.append(
            f"{descartados_sinteticos} registro(s) de herrajes sintéticos excluidos "
            "(incluir_sinteticos=false)."
        )
    origenes_totales = {origen for _, origen, _ in con_datos}
    if origenes_totales == {"synthetic"}:
        avisos.append(
            "Todo el soporte es sintético: las sugerencias no proceden de muebles reales."
        )
    elif "synthetic" in origenes_totales:
        avisos.append("Parte del soporte es sintético, no procede de muebles reales.")
    if any(item.estado == "hipotesis" for item in sugerencias):
        avisos.append(
            "Las sugerencias son hipótesis por precedentes; deben revisarse antes de usarse."
        )
    return ResultadoSugerenciasHerrajes(
        comparables_recuperados=len(comparables),
        comparables_con_datos=total,
        record_ids_sin_datos=tuple(sin_datos),
        minimo_soporte=minimo_soporte,
        proporcion_minima=proporcion_minima,
        sugerencias=tuple(sugerencias),
        avisos=tuple(avisos),
    )


def sugerir_herrajes(
    store: HistoricalStore,
    almacen: AlmacenHerrajes,
    solicitud: SolicitudSugerenciasHerrajes,
) -> ResultadoSugerenciasHerrajes:
    respuesta = store.find_comparables(
        solicitud.objetivo,
        limit=solicitud.limite,
        retrieval_method="attribute",
        include_synthetic=solicitud.incluir_sinteticos,
    )
    registros = almacen.obtener(
        tuple(item.record.record_id for item in respuesta.items)
    )
    return agregar_sugerencias(
        respuesta.items,
        registros,
        minimo_soporte=solicitud.minimo_soporte,
        incluir_sinteticos=solicitud.incluir_sinteticos,
        proporcion_minima=solicitud.proporcion_minima,
    )
