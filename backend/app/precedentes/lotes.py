"""Idea 3.1: preparar lotes de corte agrupando pedidos por clave exacta.

- El concepto de pedido no existe en el sistema: los pedidos llegan explícitos
  en la petición (o se toma cada ``run_id`` de biblioteca como un pedido).
- Clave EXACTA: (espesor, material normalizado, acabado normalizado). Un acabado
  ``None`` es su propia clave y nunca se mezcla con un acabado conocido.
- Piezas con espesor, material, largo o ancho desconocidos van al grupo
  ``sin_clasificar`` con motivo (largo/ancho se añaden porque sin ellos la
  superficie quedaría infraestimada).
- ``estimacion``: tableros = ceil(superficie / (área_tablero × aprovechamiento)). Es
  una ESTIMACIÓN por superficie, se conserva solo como referencia.
- ``nesting``: colocación real por guillotina (ver ``nesting.py``) con ancho de sierra,
  margen y rotación; es la cifra de tableros que debe usarse para preparar el corte.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence

from pydantic import Field

from backend.app.precedentes.comun import ModeloEstricto, normalizar_texto
from backend.app.precedentes.nesting import (
    LIMITE_OCURRENCIAS,
    MOTIVOS_NO_CABE,
    ParametrosNesting,
    ResultadoNesting,
    cabe_en_area_util,
    nestear,
)
from backend.app.precedentes.piezas import (
    OrigenDatos,
    PiezaRef,
    contar_origen,
    unidades,
)

# El límite por lote (``LIMITE_OCURRENCIAS``) protege cada nesting; este presupuesto
# acota el trabajo total de una petición con muchos lotes. Un lote que no entra
# conserva su estimación por superficie y se marca con el motivo.
LIMITE_OCURRENCIAS_TOTAL = 15_000
MOTIVO_DEMASIADAS_OCURRENCIAS = "demasiadas_ocurrencias"
MOTIVO_LIMITE_TOTAL = "limite_total_de_calculo"

NOTA_ESTIMACION = (
    "Referencia por superficie: ceil(superficie / (área de tablero × aprovechamiento)). "
    "No es un nesting; la colocación real está en el campo `nesting` y el número real "
    "de tableros puede ser mayor."
)


class ConfiguracionLotes(ParametrosNesting):
    aprovechamiento: float = Field(default=0.8, gt=0, le=1, allow_inf_nan=False)


class ClaveLote(ModeloEstricto):
    espesor_mm: float
    material: str
    acabado: str | None


class PiezaNoCabe(ModeloEstricto):
    origen_id: str
    pieza_id: str
    largo_mm: float
    ancho_mm: float


class EstimacionTableros(ModeloEstricto):
    es_estimacion: bool = True
    metodo: str = "superficie_sobre_aprovechamiento"
    tableros: int
    tablero_largo_mm: float
    tablero_ancho_mm: float
    aprovechamiento: float
    nota: str = NOTA_ESTIMACION


class LoteCorte(ModeloEstricto):
    lote_id: str
    clave: ClaveLote
    pedidos: tuple[str, ...]
    piezas: tuple[PiezaRef, ...]
    referencias: int
    unidades: int
    unidades_con_cantidad_supuesta: int
    superficie_m2: float
    estimacion: EstimacionTableros
    # ``None`` si no se calculó: ver ``nesting_omitido``; la estimación siempre existe.
    nesting: ResultadoNesting | None
    nesting_omitido: str | None = None
    piezas_que_no_caben: tuple[PiezaNoCabe, ...]


class PiezaSinClasificar(ModeloEstricto):
    pieza: PiezaRef
    motivo: str


class GrupoSinClasificar(ModeloEstricto):
    grupo: str = "sin_clasificar"
    pedidos: tuple[str, ...]
    piezas: tuple[PiezaSinClasificar, ...]


class ResultadoLotes(ModeloEstricto):
    configuracion: ConfiguracionLotes
    lotes: tuple[LoteCorte, ...]
    sin_clasificar: GrupoSinClasificar
    pedidos: tuple[str, ...]
    pedidos_sin_piezas: tuple[str, ...]
    origen_datos: OrigenDatos
    aviso: str = (
        "Preparación de lote revisable. Agrupa por espesor, material y acabado exactos; "
        "`nesting` coloca cada ocurrencia con una heurística de guillotina (no garantiza "
        "el mínimo de tableros) y `estimacion` es solo la referencia por superficie."
    )


def _motivo_sin_clasificar(pieza: PiezaRef) -> str | None:
    faltan = [
        nombre
        for nombre, valor in (
            ("espesor", pieza.espesor_mm),
            ("material", normalizar_texto(pieza.material)),
            ("largo", pieza.largo_mm),
            ("ancho", pieza.ancho_mm),
            ("cantidad", pieza.cantidad),
        )
        if valor is None
    ]
    if faltan == ["cantidad"]:
        return "cantidad desconocida"
    return f"{', '.join(faltan)} desconocido" if faltan else None


def cabe_en_tablero(
    largo: float,
    ancho: float,
    configuracion: ConfiguracionLotes,
    rotable: bool = True,
) -> bool:
    """La pieza cabe, sola, en el área útil del tablero (con giro si está permitido)."""
    return cabe_en_area_util(largo, ancho, configuracion, rotable)


def estimar_tableros(superficie_mm2: float, configuracion: ConfiguracionLotes) -> int:
    util = configuracion.tablero_largo_mm * configuracion.tablero_ancho_mm
    cociente = superficie_mm2 / (util * configuracion.aprovechamiento)
    # Redondeo previo para que el ruido de coma flotante no sume un tablero.
    return math.ceil(round(cociente, 9))


def _clave_orden(pieza: PiezaRef) -> tuple[str, str]:
    return (pieza.origen_id, pieza.pieza_id)


def preparar_lotes(
    piezas: Sequence[PiezaRef],
    configuracion: ConfiguracionLotes,
    pedidos: Sequence[str] = (),
) -> ResultadoLotes:
    """Función pura. ``origen_id`` de cada pieza identifica su pedido.

    ``pedidos`` lista todos los pedidos considerados (incluidos los que no aportan
    piezas, para informar de ellos).
    """
    por_clave: dict[tuple[float, str, str | None], list[PiezaRef]] = defaultdict(list)
    sin_clasificar: list[PiezaSinClasificar] = []
    for pieza in sorted(piezas, key=_clave_orden):
        motivo = _motivo_sin_clasificar(pieza)
        if motivo is not None:
            sin_clasificar.append(PiezaSinClasificar(pieza=pieza, motivo=motivo))
            continue
        material = normalizar_texto(pieza.material)
        assert material is not None and pieza.espesor_mm is not None
        por_clave[(pieza.espesor_mm, material, normalizar_texto(pieza.acabado))].append(
            pieza
        )

    grupos = []
    for (espesor, material, acabado), miembros in por_clave.items():
        superficie_mm2 = sum(
            float(p.largo_mm or 0) * float(p.ancho_mm or 0) * unidades(p)
            for p in miembros
        )
        grupos.append((espesor, material, acabado, miembros, superficie_mm2))
    grupos.sort(
        key=lambda g: (
            -round(g[4] / 1_000_000, 6),
            g[0],
            g[1],
            g[2] is None,
            g[2] or "",
        )
    )

    lotes: list[LoteCorte] = []
    presupuesto = LIMITE_OCURRENCIAS_TOTAL
    for indice, (espesor, material, acabado, miembros, superficie_mm2) in enumerate(
        grupos, start=1
    ):
        ocurrencias = sum(
            unidades(p)
            for p in miembros
            if cabe_en_tablero(
                float(p.largo_mm or 0),
                float(p.ancho_mm or 0),
                configuracion,
                p.rotable,
            )
        )
        omitido: str | None = None
        if ocurrencias > LIMITE_OCURRENCIAS:
            omitido = MOTIVO_DEMASIADAS_OCURRENCIAS
        elif ocurrencias > presupuesto:
            omitido = MOTIVO_LIMITE_TOTAL
        resultado_nesting: ResultadoNesting | None = None
        if omitido is None:
            presupuesto -= ocurrencias
            resultado_nesting = nestear(miembros, configuracion)
            no_caben = tuple(
                PiezaNoCabe(
                    origen_id=n.origen_id,
                    pieza_id=n.pieza_id,
                    largo_mm=float(n.largo_mm or 0),
                    ancho_mm=float(n.ancho_mm or 0),
                )
                for n in resultado_nesting.no_colocadas
                if n.motivo in MOTIVOS_NO_CABE
            )
        else:
            # Sin nesting solo se puede comprobar cada pieza por separado.
            no_caben = tuple(
                PiezaNoCabe(
                    origen_id=p.origen_id,
                    pieza_id=p.pieza_id,
                    largo_mm=float(p.largo_mm or 0),
                    ancho_mm=float(p.ancho_mm or 0),
                )
                for p in miembros
                if not cabe_en_tablero(
                    float(p.largo_mm or 0),
                    float(p.ancho_mm or 0),
                    configuracion,
                    p.rotable,
                )
            )
        lotes.append(
            LoteCorte(
                lote_id=f"lote-{indice:03d}",
                clave=ClaveLote(espesor_mm=espesor, material=material, acabado=acabado),
                pedidos=tuple(sorted({p.origen_id for p in miembros})),
                piezas=tuple(miembros),
                referencias=len(miembros),
                unidades=ocurrencias,
                unidades_con_cantidad_supuesta=sum(
                    1 for p in miembros if p.cantidad is None
                ),
                superficie_m2=round(superficie_mm2 / 1_000_000, 6),
                estimacion=EstimacionTableros(
                    tableros=estimar_tableros(superficie_mm2, configuracion),
                    tablero_largo_mm=configuracion.tablero_largo_mm,
                    tablero_ancho_mm=configuracion.tablero_ancho_mm,
                    aprovechamiento=configuracion.aprovechamiento,
                ),
                nesting=resultado_nesting,
                nesting_omitido=omitido,
                piezas_que_no_caben=no_caben,
            )
        )

    numerados = tuple(lotes)
    con_piezas = {p.origen_id for p in piezas}
    todos = sorted(set(pedidos) | con_piezas)
    return ResultadoLotes(
        configuracion=configuracion,
        lotes=numerados,
        sin_clasificar=GrupoSinClasificar(
            pedidos=tuple(sorted({s.pieza.origen_id for s in sin_clasificar})),
            piezas=tuple(sin_clasificar),
        ),
        pedidos=tuple(todos),
        pedidos_sin_piezas=tuple(p for p in todos if p not in con_piezas),
        origen_datos=contar_origen(piezas),
    )
