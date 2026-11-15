"""Registro de decisiones de revisión sobre comparables y recomendación de pesos (idea 3.4).

Las decisiones (aceptar/descartar un candidato mostrado para una consulta) se guardan en
un SQLite propio. ``recomendar_pesos`` es una función pura que propone pesos para los
componentes del score a partir de cuánto separa cada componente aceptados de rechazados.
Es una RECOMENDACIÓN: nunca se aplica automáticamente al score.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from backend.app.precedentes.comun import ModeloEstricto

ValorComponente = Annotated[float, Field(allow_inf_nan=False)]
ClaveComponente = Annotated[str, Field(min_length=1, max_length=64)]
MAX_ID = 200
MAX_COMPONENTES = 32

COMPONENTES_POR_METODO: dict[str, tuple[str, ...]] = {
    "geometric": ("dimensions", "roles", "thickness"),
    "semantic": ("cosine",),
}


class DecisionEntrada(ModeloEstricto):
    consulta_id: str = Field(min_length=1, max_length=MAX_ID)
    candidato_id: str = Field(min_length=1, max_length=MAX_ID)
    metodo: str = Field(min_length=1, max_length=64)
    score_components: dict[ClaveComponente, ValorComponente] = Field(max_length=MAX_COMPONENTES)
    aceptado: bool
    motivo: str | None = Field(default=None, max_length=2000)
    actor: str | None = Field(default=None, min_length=1, max_length=MAX_ID)


class Decision(ModeloEstricto):
    consulta_id: str
    candidato_id: str
    metodo: str
    score_components: dict[str, float]
    aceptado: bool
    motivo: str | None
    actor: str | None
    registrada_en: str
    actualizada_en: str


class ResultadoRegistro(ModeloEstricto):
    decision: Decision
    estado: Literal["creada", "actualizada", "sin_cambios"]


class SeparacionComponente(ModeloEstricto):
    componente: str
    aceptadas: int
    rechazadas: int
    auc: float | None
    separacion: float


class RecomendacionPesos(ModeloEstricto):
    estado: Literal["recomendacion", "abstencion"]
    motivo: str | None
    minimo_decisiones: int
    aceptadas: int
    rechazadas: int
    componentes: tuple[SeparacionComponente, ...]
    pesos_recomendados: dict[str, float] | None
    aplicada_automaticamente: Literal[False] = False
    nota: str = "Recomendación orientativa: no modifica el score; requiere acuerdo del equipo para aplicarse."


class ResumenDecisiones(ModeloEstricto):
    metodo: str
    total: int
    aceptadas: int
    rechazadas: int
    recomendacion: RecomendacionPesos


def _auc(aceptados: list[float], rechazados: list[float]) -> float:
    """AUC de Mann-Whitney: probabilidad de que un aceptado puntúe más que un rechazado (empate = 0,5)."""
    favorables = 0.0
    for a in aceptados:
        for r in rechazados:
            favorables += 1.0 if a > r else 0.5 if a == r else 0.0
    return favorables / (len(aceptados) * len(rechazados))


def recomendar_pesos(decisiones: tuple[Decision, ...], componentes: tuple[str, ...], minimo_decisiones: int) -> RecomendacionPesos:
    """Propone pesos por componente a partir de decisiones de revisión.

    - ``minimo_decisiones`` se aplica al total de decisiones; además se exige al menos una
      decisión de cada clase. Si no se cumple, ``abstencion`` con motivo.
    - Por componente: AUC entre aceptados y rechazados usando solo las decisiones que
      contienen ese componente (un valor ausente no se trata como 0). Separación =
      ``max(0, AUC - 0,5)``; un componente sin ambas clases tiene separación 0.
    - Pesos = separación normalizada para sumar 1, solo para componentes con datos de ambas
      clases (sin datos no es evidencia de peso 0). Si toda separación es 0 → ``abstencion``.
    """
    aceptadas = sum(1 for item in decisiones if item.aceptado)
    rechazadas = len(decisiones) - aceptadas
    filas: list[SeparacionComponente] = []
    for componente in sorted(set(componentes)):
        si = [item.score_components[componente] for item in decisiones if item.aceptado and componente in item.score_components]
        no = [item.score_components[componente] for item in decisiones if not item.aceptado and componente in item.score_components]
        auc = round(_auc(si, no), 6) if si and no else None
        filas.append(SeparacionComponente(componente=componente, aceptadas=len(si), rechazadas=len(no), auc=auc, separacion=round(max(0.0, auc - 0.5), 6) if auc is not None else 0.0))

    def abstencion(motivo: str) -> RecomendacionPesos:
        return RecomendacionPesos(estado="abstencion", motivo=motivo, minimo_decisiones=minimo_decisiones, aceptadas=aceptadas, rechazadas=rechazadas, componentes=tuple(filas), pesos_recomendados=None)

    if not componentes:
        return abstencion("sin_componentes")
    if len(decisiones) < minimo_decisiones:
        return abstencion(f"decisiones_insuficientes: {len(decisiones)} < {minimo_decisiones}")
    if aceptadas == 0 or rechazadas == 0:
        return abstencion("falta_una_clase: se necesitan aceptados y rechazados")
    total = sum(fila.separacion for fila in filas)
    if total <= 0:
        return abstencion("sin_separacion: ningún componente distingue aceptados de rechazados")
    pesos = {fila.componente: round(fila.separacion / total, 6) for fila in filas if fila.auc is not None}
    return RecomendacionPesos(estado="recomendacion", motivo=None, minimo_decisiones=minimo_decisiones, aceptadas=aceptadas, rechazadas=rechazadas, componentes=tuple(filas), pesos_recomendados=pesos)


def componentes_para(metodo: str, decisiones: tuple[Decision, ...]) -> tuple[str, ...]:
    """Componentes conocidos del método; si no se conoce, los observados que no son pesos (``*_weight``)."""
    if metodo in COMPONENTES_POR_METODO:
        return COMPONENTES_POR_METODO[metodo]
    return tuple(sorted({clave for item in decisiones for clave in item.score_components if not clave.endswith("_weight")}))


def _ahora_utc() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def _conexion(ruta: Path, timeout_s: float = 10.0) -> Iterator[sqlite3.Connection]:
    conexion = sqlite3.connect(ruta, timeout=timeout_s, isolation_level=None)
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


class AlmacenDecisiones:
    """SQLite propio de decisiones. Idempotente por (consulta, candidato, método, actor)."""

    def __init__(self, ruta: Path, ahora: Callable[[], str] = _ahora_utc) -> None:
        self.ruta = Path(ruta)
        self._ahora = ahora
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._conexion() as db, _transaccion(db):
            db.execute(
                "CREATE TABLE IF NOT EXISTS decisiones ("
                " consulta_id TEXT NOT NULL, candidato_id TEXT NOT NULL, metodo TEXT NOT NULL,"
                " actor_clave TEXT NOT NULL, actor TEXT, score_components TEXT NOT NULL,"
                " aceptado INTEGER NOT NULL, motivo TEXT, registrada_en TEXT NOT NULL, actualizada_en TEXT NOT NULL,"
                " PRIMARY KEY (consulta_id, candidato_id, metodo, actor_clave))"
            )

    @contextmanager
    def _conexion(self) -> Iterator[sqlite3.Connection]:
        with _conexion(self.ruta) as db:
            yield db

    def _conectar(self) -> sqlite3.Connection:
        conexion = sqlite3.connect(self.ruta, timeout=10)
        conexion.execute("PRAGMA busy_timeout=10000")
        return conexion

    def registrar(self, entrada: DecisionEntrada) -> ResultadoRegistro:
        componentes = json.dumps(entrada.score_components, sort_keys=True)
        clave = (entrada.consulta_id, entrada.candidato_id, entrada.metodo, entrada.actor or "")
        ahora = self._ahora()
        with self._conexion() as db, _transaccion(db):
            fila = db.execute(
                "SELECT score_components, aceptado, motivo, registrada_en, actualizada_en FROM decisiones"
                " WHERE consulta_id=? AND candidato_id=? AND metodo=? AND actor_clave=?", clave,
            ).fetchone()
            if fila is None:
                db.execute("INSERT INTO decisiones VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (*clave, entrada.actor, componentes, int(entrada.aceptado), entrada.motivo, ahora, ahora))
                registrada, actualizada, estado = ahora, ahora, "creada"
            elif (fila[0], bool(fila[1]), fila[2]) == (componentes, entrada.aceptado, entrada.motivo):
                registrada, actualizada, estado = fila[3], fila[4], "sin_cambios"
            else:
                db.execute(
                    "UPDATE decisiones SET score_components=?, aceptado=?, motivo=?, actualizada_en=?"
                    " WHERE consulta_id=? AND candidato_id=? AND metodo=? AND actor_clave=?",
                    (componentes, int(entrada.aceptado), entrada.motivo, ahora, *clave),
                )
                registrada, actualizada, estado = fila[3], ahora, "actualizada"
        decision = Decision(
            consulta_id=entrada.consulta_id, candidato_id=entrada.candidato_id, metodo=entrada.metodo,
            score_components=dict(entrada.score_components), aceptado=entrada.aceptado, motivo=entrada.motivo,
            actor=entrada.actor, registrada_en=registrada, actualizada_en=actualizada,
        )
        return ResultadoRegistro(decision=decision, estado=estado)

    def listar(self, metodo: str | None = None) -> tuple[Decision, ...]:
        consulta = "SELECT consulta_id, candidato_id, metodo, actor, score_components, aceptado, motivo, registrada_en, actualizada_en FROM decisiones"
        parametros: tuple[str, ...] = ()
        if metodo is not None:
            consulta += " WHERE metodo=?"
            parametros = (metodo,)
        consulta += " ORDER BY consulta_id, candidato_id, metodo, actor_clave"
        with self._conexion() as db:
            filas = db.execute(consulta, parametros).fetchall()
        return tuple(
            Decision(consulta_id=f[0], candidato_id=f[1], metodo=f[2], actor=f[3], score_components=json.loads(f[4]), aceptado=bool(f[5]), motivo=f[6], registrada_en=f[7], actualizada_en=f[8])
            for f in filas
        )


def resumir(decisiones: tuple[Decision, ...], metodo: str, minimo_decisiones: int) -> ResumenDecisiones:
    propias = tuple(item for item in decisiones if item.metodo == metodo)
    aceptadas = sum(1 for item in propias if item.aceptado)
    return ResumenDecisiones(
        metodo=metodo, total=len(propias), aceptadas=aceptadas, rechazadas=len(propias) - aceptadas,
        recomendacion=recomendar_pesos(propias, componentes_para(metodo, propias), minimo_decisiones),
    )
