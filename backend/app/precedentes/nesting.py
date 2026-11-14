"""Idea 3.1: colocación 2D real de piezas en tableros (nesting por guillotina).

Algoritmo determinista (mismo input, mismo output exacto, sin depender del orden
de entrada):

1. Cada ocurrencia física de cada pieza (``cantidad``; ``None`` cuenta como 1) se
   trata por separado.
2. Se ordenan por área decreciente (empates por lado mayor, origen, pieza y
   ocurrencia): *first-fit decreasing*.
3. Cada una va al primer tablero donde cabe; dentro del tablero se elige el hueco
   libre y la orientación con menor sobrante del lado corto (*best short side fit*)
   y, a igualdad, el más bajo y a la izquierda.
4. El hueco usado se divide en dos con un corte de guillotina (eje de menor
   sobrante) y el ancho de sierra (``kerf``) se descuenta entre piezas vecinas. El
   kerf no se aplica en los bordes del tablero.

Convenciones: el eje X del tablero es su ``tablero_largo_mm`` y el eje Y su
``tablero_ancho_mm``. Una pieza sin girar ocupa ``largo`` en X y ``ancho`` en Y, de
modo que la veta, si la hay, sigue el largo del tablero; ``rotada=True`` intercambia
ambos. El margen se descuenta en los cuatro bordes. Todo en milímetros; internamente
se calcula en micrómetros enteros para no arrastrar error de coma flotante.

Nunca se inventa una medida: una pieza con largo o ancho desconocido queda fuera del
nesting con motivo ``medida_desconocida``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import NamedTuple

from pydantic import Field, model_validator

from backend.app.precedentes.comun import ModeloEstricto
from backend.app.precedentes.piezas import PiezaRef, unidades

METODO_NESTING = "guillotina_ffd_bssf"
LIMITE_OCURRENCIAS = 3000
_UM = 1000  # micrómetros por milímetro

MOTIVO_MEDIDA_DESCONOCIDA = "medida_desconocida"
MOTIVO_MAS_GRANDE = "mas_grande_que_el_area_util"
MOTIVO_SIN_ROTAR = "no_cabe_sin_rotar"
MOTIVOS_NO_CABE = (MOTIVO_MAS_GRANDE, MOTIVO_SIN_ROTAR)

NOTA_NESTING = (
    "Colocación real por guillotina (first-fit decreasing, ancho de sierra y margen "
    "aplicados). Heurística: no garantiza el mínimo de tableros."
)


class DemasiadasOcurrencias(ValueError):
    """La suma de ocurrencias físicas a colocar supera ``LIMITE_OCURRENCIAS``."""

    def __init__(self, total: int) -> None:
        super().__init__(
            f"{total} ocurrencias a colocar; el máximo es {LIMITE_OCURRENCIAS}."
        )
        self.total = total


class ParametrosNesting(ModeloEstricto):
    tablero_largo_mm: float = Field(
        default=2440.0, gt=0, le=10_000, allow_inf_nan=False
    )
    tablero_ancho_mm: float = Field(
        default=1220.0, gt=0, le=10_000, allow_inf_nan=False
    )
    kerf_mm: float = Field(default=3.0, ge=0, le=50, allow_inf_nan=False)
    margen_mm: float = Field(default=0.0, ge=0, le=500, allow_inf_nan=False)
    permitir_rotacion: bool = True

    @model_validator(mode="after")
    def _area_util_positiva(self) -> ParametrosNesting:
        if (
            self.tablero_largo_mm - 2 * self.margen_mm <= 0
            or self.tablero_ancho_mm - 2 * self.margen_mm <= 0
        ):
            raise ValueError("El margen no deja área útil en el tablero.")
        return self


class Colocacion(ModeloEstricto):
    origen_id: str
    pieza_id: str
    ocurrencia: int
    tablero: int
    x_mm: float
    y_mm: float
    ancho_mm: float
    alto_mm: float
    rotada: bool


class PiezaNoColocada(ModeloEstricto):
    origen_id: str
    pieza_id: str
    ocurrencias: int
    largo_mm: float | None
    ancho_mm: float | None
    motivo: str


class TableroNesting(ModeloEstricto):
    tablero: int
    piezas: int
    superficie_piezas_m2: float
    aprovechamiento: float


class ResultadoNesting(ModeloEstricto):
    metodo: str = METODO_NESTING
    es_estimacion: bool = False
    tableros: int
    tableros_detalle: tuple[TableroNesting, ...]
    colocaciones: tuple[Colocacion, ...]
    no_colocadas: tuple[PiezaNoColocada, ...]
    aprovechamiento_total: float
    nota: str = NOTA_NESTING


def _um_arriba(mm: float) -> int:
    # El redondeo previo a 6 decimales elimina el ruido de coma flotante (1220.3 mm
    # es 1220300.0000000002 µm) para que ``ceil`` no sume un micrómetro espurio.
    return math.ceil(round(mm * _UM, 6))


def _um_abajo(mm: float) -> int:
    return math.floor(round(mm * _UM, 6))


def _um_pieza(mm: float) -> int:
    """Piezas, margen y kerf se redondean hacia arriba; el tablero, hacia abajo.

    Todo error de redondeo juega en contra de la pieza, nunca a su favor: lo que se
    declara colocado cabe de verdad en el tablero físico.
    """
    return max(1, _um_arriba(mm))


class _Geometria(NamedTuple):
    margen: int
    kerf: int
    ancho_util: int
    alto_util: int
    area_tablero: int


def _geometria(parametros: ParametrosNesting) -> _Geometria:
    margen = _um_arriba(parametros.margen_mm)
    largo = _um_abajo(parametros.tablero_largo_mm)
    ancho = _um_abajo(parametros.tablero_ancho_mm)
    return _Geometria(
        margen=margen,
        kerf=_um_arriba(parametros.kerf_mm),
        ancho_util=largo - 2 * margen,
        alto_util=ancho - 2 * margen,
        area_tablero=largo * ancho,
    )


def _cabe(w: int, h: int, ancho_util: int, alto_util: int, girable: bool) -> bool:
    return (w <= ancho_util and h <= alto_util) or (
        girable and h <= ancho_util and w <= alto_util
    )


def cabe_en_area_util(
    largo_mm: float,
    ancho_mm: float,
    parametros: ParametrosNesting,
    rotable: bool = True,
) -> bool:
    """La pieza entra, sola, en el área útil del tablero (con rotación si procede)."""
    geo = _geometria(parametros)
    return _cabe(
        _um_pieza(largo_mm),
        _um_pieza(ancho_mm),
        geo.ancho_util,
        geo.alto_util,
        parametros.permitir_rotacion and rotable,
    )


class _Hueco(NamedTuple):
    x: int
    y: int
    w: int
    h: int


class _Item(NamedTuple):
    origen_id: str
    pieza_id: str
    ocurrencia: int
    w: int
    h: int
    girable: bool


class _Tablero:
    def __init__(self, area_util: _Hueco) -> None:
        self.huecos: list[_Hueco] = [area_util]
        self.colocadas: list[tuple[_Item, int, int, int, int, bool]] = []

    def mejor_ajuste(
        self, item: _Item
    ) -> tuple[tuple[int, int, int, int, int, int], int, bool] | None:
        """Mejor (puntuación, hueco, girada) o ``None`` si no cabe en este tablero."""
        mejor: tuple[tuple[int, int, int, int, int, int], int, bool] | None = None
        orientaciones = [(item.w, item.h, False)]
        if item.girable and item.w != item.h:
            orientaciones.append((item.h, item.w, True))
        for indice, hueco in enumerate(self.huecos):
            for w, h, girada in orientaciones:
                if w > hueco.w or h > hueco.h:
                    continue
                sobra_w, sobra_h = hueco.w - w, hueco.h - h
                puntuacion = (
                    min(sobra_w, sobra_h),
                    max(sobra_w, sobra_h),
                    hueco.y,
                    hueco.x,
                    indice,
                    int(girada),
                )
                if mejor is None or puntuacion < mejor[0]:
                    mejor = (puntuacion, indice, girada)
        return mejor

    def colocar(
        self, item: _Item, indice: int, girada: bool, kerf: int, minimo: int
    ) -> None:
        hueco = self.huecos[indice]
        w, h = (item.h, item.w) if girada else (item.w, item.h)
        self.colocadas.append((item, hueco.x, hueco.y, w, h, girada))
        sobra_w, sobra_h = hueco.w - w, hueco.h - h
        if sobra_w <= sobra_h:  # corte horizontal completo; derecha limitada a la pieza
            derecha = _Hueco(hueco.x + w + kerf, hueco.y, sobra_w - kerf, h)
            arriba = _Hueco(hueco.x, hueco.y + h + kerf, hueco.w, sobra_h - kerf)
        else:  # corte vertical completo; arriba limitada a la pieza
            derecha = _Hueco(hueco.x + w + kerf, hueco.y, sobra_w - kerf, hueco.h)
            arriba = _Hueco(hueco.x, hueco.y + h + kerf, w, sobra_h - kerf)
        nuevos = [r for r in (derecha, arriba) if r.w >= minimo and r.h >= minimo]
        self.huecos[indice : indice + 1] = nuevos

    @property
    def area_piezas(self) -> int:
        return sum(w * h for _, _, _, w, h, _ in self.colocadas)


def _mm(micras: int) -> float:
    return round(micras / _UM, 3)


def _item_no_colocado(pieza: PiezaRef, motivo: str, cantidad: int) -> PiezaNoColocada:
    return PiezaNoColocada(
        origen_id=pieza.origen_id,
        pieza_id=pieza.pieza_id,
        ocurrencias=cantidad,
        largo_mm=pieza.largo_mm,
        ancho_mm=pieza.ancho_mm,
        motivo=motivo,
    )


def nestear(
    piezas: Sequence[PiezaRef], parametros: ParametrosNesting
) -> ResultadoNesting:
    """Coloca todas las ocurrencias de ``piezas`` en tableros del tamaño dado.

    Lanza ``DemasiadasOcurrencias`` si hay más de ``LIMITE_OCURRENCIAS`` ocurrencias
    con medidas conocidas y ``ValueError`` si hay pares (origen_id, pieza_id)
    duplicados. No agrupa por material: eso lo hace quien llama.
    """
    ordenadas = sorted(piezas, key=lambda p: (p.origen_id, p.pieza_id))
    claves = [(p.origen_id, p.pieza_id) for p in ordenadas]
    if len(set(claves)) != len(claves):
        repetidas = sorted({f"{o}/{i}" for o, i in claves if claves.count((o, i)) > 1})
        raise ValueError("Piezas duplicadas: " + ", ".join(repetidas))
    total = sum(
        unidades(p)
        for p in ordenadas
        if p.largo_mm is not None and p.ancho_mm is not None
    )
    if total > LIMITE_OCURRENCIAS:
        raise DemasiadasOcurrencias(total)

    margen, kerf, ancho_util, alto_util, area_tablero = _geometria(parametros)

    items: list[_Item] = []
    no_colocadas: list[PiezaNoColocada] = []
    for pieza in ordenadas:
        if pieza.largo_mm is None or pieza.ancho_mm is None:
            no_colocadas.append(
                _item_no_colocado(pieza, MOTIVO_MEDIDA_DESCONOCIDA, unidades(pieza))
            )
            continue
        w, h = _um_pieza(pieza.largo_mm), _um_pieza(pieza.ancho_mm)
        girable = parametros.permitir_rotacion and pieza.rotable
        if not _cabe(w, h, ancho_util, alto_util, girable):
            giro_valdria = _cabe(w, h, ancho_util, alto_util, True)
            motivo = MOTIVO_SIN_ROTAR if giro_valdria else MOTIVO_MAS_GRANDE
            no_colocadas.append(_item_no_colocado(pieza, motivo, unidades(pieza)))
            continue
        items.extend(
            _Item(pieza.origen_id, pieza.pieza_id, n, w, h, girable)
            for n in range(1, unidades(pieza) + 1)
        )

    items.sort(
        key=lambda i: (
            -i.w * i.h,
            -max(i.w, i.h),
            i.origen_id,
            i.pieza_id,
            i.ocurrencia,
        )
    )
    minimo = min((min(i.w, i.h) for i in items), default=1)
    tableros: list[_Tablero] = []
    area_util = _Hueco(margen, margen, ancho_util, alto_util)
    # Los huecos de un tablero solo se reducen: si una forma no cupo en un tablero,
    # no cabrá nunca. ``primer_candidato`` recuerda, por forma, desde qué tablero
    # buscar. Evita el coste cuadrático (una pieza por tablero) sin cambiar el
    # resultado del first-fit.
    primer_candidato: dict[tuple[int, int, bool], int] = {}
    for item in items:
        forma = (item.w, item.h, item.girable)
        elegido: tuple[int, int, bool] | None = None
        for indice in range(primer_candidato.get(forma, 0), len(tableros)):
            ajuste = tableros[indice].mejor_ajuste(item)
            if ajuste is not None:
                elegido = (indice, ajuste[1], ajuste[2])
                break
        if elegido is None:
            nuevo = _Tablero(area_util)
            ajuste = nuevo.mejor_ajuste(item)
            assert ajuste is not None  # ya comprobado que cabe en el área útil
            tableros.append(nuevo)
            elegido = (len(tableros) - 1, ajuste[1], ajuste[2])
        primer_candidato[forma] = elegido[0]
        tableros[elegido[0]].colocar(item, elegido[1], elegido[2], kerf, minimo)

    colocaciones: list[Colocacion] = []
    detalle: list[TableroNesting] = []
    for numero, tablero in enumerate(tableros, start=1):
        for item, x, y, w, h, girada in sorted(
            tablero.colocadas,
            key=lambda c: (c[2], c[1], c[0].origen_id, c[0].pieza_id, c[0].ocurrencia),
        ):
            colocaciones.append(
                Colocacion(
                    origen_id=item.origen_id,
                    pieza_id=item.pieza_id,
                    ocurrencia=item.ocurrencia,
                    tablero=numero,
                    x_mm=_mm(x),
                    y_mm=_mm(y),
                    ancho_mm=_mm(w),
                    alto_mm=_mm(h),
                    rotada=girada,
                )
            )
        detalle.append(
            TableroNesting(
                tablero=numero,
                piezas=len(tablero.colocadas),
                superficie_piezas_m2=round(tablero.area_piezas / _UM**2 / 1_000_000, 6),
                aprovechamiento=round(tablero.area_piezas / area_tablero, 6),
            )
        )
    area_total = sum(t.area_piezas for t in tableros)
    return ResultadoNesting(
        tableros=len(tableros),
        tableros_detalle=tuple(detalle),
        colocaciones=tuple(colocaciones),
        no_colocadas=tuple(no_colocadas),
        aprovechamiento_total=(
            round(area_total / (len(tableros) * area_tablero), 6) if tableros else 0.0
        ),
    )
