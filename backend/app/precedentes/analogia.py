"""Idea 2.2: presupuesto por analogía con alerta de desviación.

Junto al coste calculado (paramétrico), muestra los proyectos más parecidos del
histórico con su coste escalado al objetivo y avisa si el cálculo se sale del
rango del vecindario. El umbral de alerta se expresa en múltiplos de una
dispersión robusta (MAD) del vecindario, nunca como un porcentaje fijo.

Todo el resultado es una hipótesis basada en precedentes: se abstiene con menos
comparables válidos que el mínimo pedido y declara el origen de los datos.
"""

from __future__ import annotations

from datetime import date
from statistics import median
from typing import Literal

from pydantic import Field, model_validator

from backend.app.historico.models import HistoricalRecord, HistoricalTarget
from backend.app.historico.real_service import HistoricalStore
from backend.app.precedentes.comun import ModeloEstricto

Origen = Literal["actual", "published", "synthetic"]
NivelDesviacion = Literal["dentro_de_rango", "aviso", "alerta"]

# Constante de consistencia: 1,4826·MAD estima la desviación típica con datos normales.
FACTOR_MAD_NORMAL = 1.4826


class ConfiguracionAnalogia(ModeloEstricto):
    """Umbrales de la alerta, en múltiplos de la dispersión robusta del vecindario."""

    multiplo_aviso: float = Field(default=2.0, gt=0, allow_inf_nan=False)
    multiplo_alerta: float = Field(default=3.0, gt=0, allow_inf_nan=False)
    factor_mad: float = Field(default=FACTOR_MAD_NORMAL, gt=0, allow_inf_nan=False)
    suelo_relativo: float = Field(default=0.05, ge=0, allow_inf_nan=False)
    suelo_absoluto: float = Field(default=0.01, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def umbrales_ordenados(self) -> ConfiguracionAnalogia:
        if self.multiplo_alerta <= self.multiplo_aviso:
            raise ValueError("multiplo_alerta debe ser mayor que multiplo_aviso")
        return self


class SolicitudPresupuestoAnalogia(ModeloEstricto):
    objetivo: HistoricalTarget
    coste_calculado: float = Field(gt=0, allow_inf_nan=False)
    moneda: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    limite: int = Field(default=3, ge=1, le=20)
    metodo_recuperacion: Literal["attribute", "semantic"] = "attribute"
    incluir_sinteticos: bool = False
    minimo_comparables: int = Field(default=2, ge=1, le=20)


class ComparablePresupuesto(ModeloEstricto):
    record_id: str
    project_id: str
    score: float
    coste_escalado: float
    coste_historico: float | None
    base_coste: Literal["actual", "quote", "budget"] | None
    origen: Origen
    fuente: str
    fecha: date


class ComparableExcluido(ModeloEstricto):
    record_id: str
    origen: Origen
    motivos: tuple[str, ...]


class EstadisticosVecindario(ModeloEstricto):
    n: int
    mediana: float
    minimo: float
    maximo: float
    mad: float
    dispersion: float


class AlertaDesviacion(ModeloEstricto):
    nivel: NivelDesviacion
    desviacion_absoluta: float
    desviacion_relativa: float | None
    multiplos_de_dispersion: float


class ResultadoPresupuestoAnalogia(ModeloEstricto):
    estado: Literal["con_precedentes", "sin_precedentes_suficientes"]
    naturaleza: Literal["hipotesis"] = "hipotesis"
    coste_calculado: float
    moneda: str
    metodo_recuperacion: Literal["attribute", "semantic"]
    comparables_recuperados: int
    minimo_comparables: int
    comparables: tuple[ComparablePresupuesto, ...]
    excluidos: tuple[ComparableExcluido, ...]
    estadisticos: EstadisticosVecindario | None
    alerta: AlertaDesviacion | None
    origenes: dict[str, int]
    formula: str
    configuracion: ConfiguracionAnalogia
    avisos: tuple[str, ...]


class ErrorAnalogia(ValueError):
    """Error de petición con código estable para la API."""

    def __init__(self, codigo: str, mensaje: str, estado_http: int = 422) -> None:
        super().__init__(codigo)
        self.codigo = codigo
        self.mensaje = mensaje
        self.estado_http = estado_http


def describir_formula(config: ConfiguracionAnalogia) -> str:
    return (
        "mediana = valor central de los costes escalados (media de los dos centrales si n es par); "
        "MAD = mediana(|coste_i - mediana|); "
        f"dispersion = max({config.factor_mad} * MAD, {config.suelo_relativo} * |mediana|, "
        f"{config.suelo_absoluto}); "
        "k = |coste_calculado - mediana| / dispersion; "
        f"nivel = dentro_de_rango si k <= {config.multiplo_aviso}, "
        f"aviso si k <= {config.multiplo_alerta}, alerta en otro caso; "
        "desviacion_relativa = (coste_calculado - mediana) / mediana (nula si mediana = 0)"
    )


def calcular_estadisticos(
    costes: tuple[float, ...], config: ConfiguracionAnalogia
) -> EstadisticosVecindario:
    """Estadísticos robustos del vecindario. Función pura; requiere al menos un coste."""
    if not costes:
        raise ValueError("se necesita al menos un coste")
    ordenados = tuple(sorted(costes))
    centro = float(median(ordenados))
    mad = float(median(abs(valor - centro) for valor in ordenados))
    dispersion = max(
        config.factor_mad * mad,
        config.suelo_relativo * abs(centro),
        config.suelo_absoluto,
    )
    return EstadisticosVecindario(
        n=len(ordenados),
        mediana=round(centro, 2),
        minimo=round(ordenados[0], 2),
        maximo=round(ordenados[-1], 2),
        mad=round(mad, 4),
        dispersion=round(dispersion, 4),
    )


def clasificar_desviacion(
    coste_calculado: float,
    estadisticos: EstadisticosVecindario,
    config: ConfiguracionAnalogia,
) -> AlertaDesviacion:
    """Nivel de alerta en múltiplos de la dispersión. Función pura."""
    diferencia = coste_calculado - estadisticos.mediana
    multiplos = abs(diferencia) / estadisticos.dispersion
    if multiplos <= config.multiplo_aviso:
        nivel: NivelDesviacion = "dentro_de_rango"
    elif multiplos <= config.multiplo_alerta:
        nivel = "aviso"
    else:
        nivel = "alerta"
    relativa = (
        round(diferencia / estadisticos.mediana, 4) if estadisticos.mediana != 0 else None
    )
    return AlertaDesviacion(
        nivel=nivel,
        desviacion_absoluta=round(diferencia, 2),
        desviacion_relativa=relativa,
        multiplos_de_dispersion=round(multiplos, 4),
    )


def _avisos_de_origen(
    validos: tuple[ComparablePresupuesto, ...],
    metodo: str,
) -> list[str]:
    avisos: list[str] = []
    if validos:
        origenes = {item.origen for item in validos}
        if origenes == {"synthetic"}:
            avisos.append(
                "Todos los comparables son sintéticos: el rango no procede de proyectos reales."
            )
        elif "synthetic" in origenes:
            avisos.append("Parte de los comparables son sintéticos, no proyectos reales.")
        if "actual" not in origenes:
            avisos.append("Ningún comparable procede de un histórico real de la empresa.")
        if any(item.base_coste in ("quote", "budget") for item in validos):
            avisos.append(
                "Al menos un comparable es un presupuesto u oferta, no un coste ejecutado."
            )
    if metodo == "semantic":
        avisos.append(
            "Comparables ordenados por similitud semántica (coseno); el escalado del coste "
            "al objetivo usa siempre los atributos declarados (driver de cada concepto)."
        )
    else:
        avisos.append(
            "Comparables ordenados por similitud de atributos; el escalado del coste usa "
            "los atributos declarados (driver de cada concepto)."
        )
    return avisos


def presupuestar_por_analogia(
    store: HistoricalStore,
    solicitud: SolicitudPresupuestoAnalogia,
    config: ConfiguracionAnalogia | None = None,
) -> ResultadoPresupuestoAnalogia:
    """Compara el coste calculado con el vecindario histórico. Determinista."""
    config = config or ConfiguracionAnalogia()
    objetivo = solicitud.objetivo
    if (
        solicitud.moneda is not None
        and objetivo.currency is not None
        and solicitud.moneda != objetivo.currency
    ):
        raise ErrorAnalogia(
            "moneda_en_conflicto",
            "La moneda de la petición no coincide con la del objetivo.",
        )
    moneda = solicitud.moneda or objetivo.currency
    if moneda is None:
        raise ErrorAnalogia(
            "moneda_requerida",
            "Indica la moneda del coste calculado (campo moneda u objetivo.currency).",
        )
    if not objetivo.required_cost_scope:
        raise ErrorAnalogia(
            "alcance_coste_requerido",
            "El objetivo debe declarar required_cost_scope para comparar costes.",
        )
    objetivo = HistoricalTarget.model_validate(
        {**objetivo.model_dump(), "currency": moneda}
    )

    respuesta = store.find_comparables(
        objetivo,
        limit=solicitud.limite,
        retrieval_method=solicitud.metodo_recuperacion,
        include_synthetic=solicitud.incluir_sinteticos,
    )
    validos: list[ComparablePresupuesto] = []
    excluidos: list[ComparableExcluido] = []
    for comparable in respuesta.items:
        registro: HistoricalRecord = comparable.record
        motivos = _motivos_previos(registro, moneda)
        coste: float | None = None
        if not motivos:
            try:
                estimacion = store.estimate(
                    objetivo,
                    comparable_ids=(registro.record_id,),
                    include_synthetic=solicitud.incluir_sinteticos,
                )
            except ValueError as error:
                motivos = (str(error),)
            else:
                escenario = next(
                    (
                        item
                        for item in estimacion.scenarios
                        if item.record_id == registro.record_id
                    ),
                    None,
                )
                if escenario is None or escenario.cost_total is None:
                    faltan = sorted(
                        {
                            dato
                            for item in (escenario.contributors if escenario else ())
                            for dato in item.missing_data
                        }
                    )
                    motivos = tuple(faltan) or ("coste_no_estimable",)
                else:
                    coste = escenario.cost_total
        if coste is None:
            excluidos.append(
                ComparableExcluido(
                    record_id=registro.record_id,
                    origen=registro.origin,
                    motivos=motivos,
                )
            )
            continue
        validos.append(
            ComparablePresupuesto(
                record_id=registro.record_id,
                project_id=registro.project_id,
                score=comparable.score,
                coste_escalado=coste,
                coste_historico=registro.actual_cost,
                base_coste=registro.cost_basis,
                origen=registro.origin,
                fuente=registro.provenance.source,
                fecha=registro.provenance.source_date,
            )
        )

    validos_t = tuple(validos)
    avisos = _avisos_de_origen(validos_t, solicitud.metodo_recuperacion)
    if any("moneda_incompatible" in item.motivos for item in excluidos):
        avisos.append(
            f"Se excluyeron comparables en una moneda distinta de {moneda}; no se convierten."
        )
    origenes: dict[str, int] = {}
    for item in validos_t:
        origenes[item.origen] = origenes.get(item.origen, 0) + 1

    estadisticos: EstadisticosVecindario | None = None
    alerta: AlertaDesviacion | None = None
    if len(validos_t) < solicitud.minimo_comparables:
        estado: Literal["con_precedentes", "sin_precedentes_suficientes"] = (
            "sin_precedentes_suficientes"
        )
        avisos.append(
            f"Solo {len(validos_t)} comparable(s) válido(s) de {solicitud.minimo_comparables} "
            "exigidos: no se emite alerta."
        )
    else:
        estado = "con_precedentes"
        estadisticos = calcular_estadisticos(
            tuple(item.coste_escalado for item in validos_t), config
        )
        alerta = clasificar_desviacion(solicitud.coste_calculado, estadisticos, config)

    return ResultadoPresupuestoAnalogia(
        estado=estado,
        coste_calculado=solicitud.coste_calculado,
        moneda=moneda,
        metodo_recuperacion=solicitud.metodo_recuperacion,
        comparables_recuperados=len(respuesta.items),
        minimo_comparables=solicitud.minimo_comparables,
        comparables=validos_t,
        excluidos=tuple(excluidos),
        estadisticos=estadisticos,
        alerta=alerta,
        origenes=dict(sorted(origenes.items())),
        formula=describir_formula(config),
        configuracion=config,
        avisos=tuple(avisos),
    )


def _motivos_previos(registro: HistoricalRecord, moneda: str) -> tuple[str, ...]:
    motivos: list[str] = []
    if registro.actual_cost is None:
        motivos.append("sin_coste_historico")
    elif registro.currency != moneda:
        motivos.append("moneda_incompatible")
    return tuple(motivos)
