"""Idea 2.4: piezas casi idénticas y propuesta de medida estándar.

Algoritmo (determinista, sin encadenamiento):

1. Solo son elegibles las piezas con largo, ancho, espesor y material conocidos.
   Espesor y material normalizado (``normalizar_texto``) deben coincidir EXACTOS;
   ``None`` nunca coincide con nada (la pieza se descarta con motivo).
2. Orientación: sin ``permitir_giro`` se respeta largo/ancho tal cual (la veta
   importa). Con giro, cada pieza se orienta como (mayor, menor) y se marca
   ``girada`` si se invirtió respecto a su entrada.
3. Dentro de cada clave exacta (espesor, material) se enumeran ventanas
   ``[l0, l0 + tol_largo] × [w0, w0 + tol_ancho]`` ancladas en valores reales.
   Una ventana es elegible si cubre piezas de >= 2 ``origen_id`` y >= 2 medidas
   distintas. Se elige de forma voraz la que cubre más unidades (cantidad;
   ``None`` = 1); desempates: más orígenes, menor ancla (l0, w0). Se retiran
   sus piezas y se repite.
   Como el rango de cada eje dentro del grupo es <= tolerancia, cada miembro
   está dentro de tolerancia de cualquier otro y de la medida estándar.
   Antes del voraz, las piezas se parten por huecos mayores que la tolerancia
   (alternando largo y ancho): ninguna ventana válida cruza un hueco, así que
   el resultado es idéntico y cada parte se resuelve por separado.
   Coste acotado: un presupuesto determinista de trabajo (piezas visitadas)
   limita el cálculo; si se agota, el resultado se marca ``parcial=True`` y se
   indican las piezas no evaluadas. Los grupos devueltos siguen siendo válidos.
4. Medida estándar: la medida de miembro más frecuente ponderada por cantidad;
   en empate, la mayor (por área largo×ancho, luego largo, luego ancho).

Es una sugerencia revisable, no una decisión de fabricación.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from collections.abc import Sequence
from itertools import pairwise

from pydantic import Field

from backend.app.precedentes.comun import ModeloEstricto, normalizar_texto
from backend.app.precedentes.piezas import (
    OrigenDatos,
    PiezaRef,
    contar_origen,
    unidades,
)

EPSILON_MM = 1e-9
TOLERANCIA_MAXIMA_MM = 50.0
PRESUPUESTO_TRABAJO = 500_000
AVISO_GEMELAS = (
    "Propuesta de unificación revisable: agrupa por tolerancia numérica por eje; "
    "no comprueba veta visual, cantos ni mecanizados."
)


class ConfiguracionGemelas(ModeloEstricto):
    tolerancia_largo_mm: float = Field(
        default=3.0, ge=0, le=TOLERANCIA_MAXIMA_MM, allow_inf_nan=False
    )
    tolerancia_ancho_mm: float = Field(
        default=3.0, ge=0, le=TOLERANCIA_MAXIMA_MM, allow_inf_nan=False
    )
    permitir_giro: bool = False


class MedidaEstandar(ModeloEstricto):
    largo_mm: float
    ancho_mm: float
    espesor_mm: float
    material: str


class MiembroGemela(ModeloEstricto):
    pieza: PiezaRef
    largo_orientado_mm: float
    ancho_orientado_mm: float
    girada: bool
    desviacion_largo_mm: float
    desviacion_ancho_mm: float


class GrupoGemelas(ModeloEstricto):
    grupo_id: str
    medida_estandar: MedidaEstandar
    miembros: tuple[MiembroGemela, ...]
    origenes: tuple[str, ...]
    unidades: int
    referencias_actuales: int
    referencias_propuestas: int = 1
    ahorro_referencias: int


class PiezaDescartada(ModeloEstricto):
    origen_id: str
    pieza_id: str
    motivo: str


class ResultadoGemelas(ModeloEstricto):
    configuracion: ConfiguracionGemelas
    grupos: tuple[GrupoGemelas, ...]
    piezas_analizadas: int
    piezas_descartadas: tuple[PiezaDescartada, ...]
    ahorro_referencias_total: int
    origen_datos: OrigenDatos
    parcial: bool = False
    piezas_no_evaluadas: tuple[PiezaDescartada, ...] = ()
    criterio_estandar: str = (
        "Medida de miembro más frecuente ponderada por cantidad (None = 1); "
        "en empate, la mayor por área, luego largo, luego ancho."
    )
    aviso: str = AVISO_GEMELAS


class _Orientada(ModeloEstricto):
    pieza: PiezaRef
    largo: float
    ancho: float
    girada: bool


def _motivo_descarte(pieza: PiezaRef) -> str | None:
    faltan = [
        nombre
        for nombre, valor in (
            ("largo", pieza.largo_mm),
            ("ancho", pieza.ancho_mm),
            ("espesor", pieza.espesor_mm),
            ("material", normalizar_texto(pieza.material)),
        )
        if valor is None
    ]
    return f"{', '.join(faltan)} desconocido" if faltan else None


def _orientar(pieza: PiezaRef, permitir_giro: bool) -> _Orientada:
    largo, ancho = float(pieza.largo_mm or 0), float(pieza.ancho_mm or 0)
    if permitir_giro and ancho > largo:
        return _Orientada(pieza=pieza, largo=ancho, ancho=largo, girada=True)
    return _Orientada(pieza=pieza, largo=largo, ancho=ancho, girada=False)


def _clave_pieza(orientada: _Orientada) -> tuple[str, str]:
    return (orientada.pieza.origen_id, orientada.pieza.pieza_id)


def _medida_estandar(miembros: Sequence[_Orientada]) -> tuple[float, float]:
    peso: dict[tuple[float, float], int] = defaultdict(int)
    for miembro in miembros:
        peso[(miembro.largo, miembro.ancho)] += unidades(miembro.pieza)
    return max(
        peso,
        key=lambda medida: (peso[medida], medida[0] * medida[1], medida[0], medida[1]),
    )


_Puntuacion = tuple[int, int, float, float]


class _Presupuesto:
    """Contador determinista de trabajo (piezas visitadas), no de tiempo."""

    def __init__(self, limite: int) -> None:
        self.restante = limite

    def consumir(self, unidades_trabajo: int) -> bool:
        self.restante -= unidades_trabajo
        return self.restante >= 0


def _cortar_por_huecos(
    piezas: list[_Orientada], eje: str, tolerancia: float
) -> list[list[_Orientada]]:
    ordenadas = sorted(piezas, key=lambda p: (getattr(p, eje), _clave_pieza(p)))
    partes: list[list[_Orientada]] = [[ordenadas[0]]]
    for anterior, actual in pairwise(ordenadas):
        if getattr(actual, eje) - getattr(anterior, eje) > tolerancia:
            partes.append([])
        partes[-1].append(actual)
    return partes


def _particionar(
    piezas: list[_Orientada], tol_l: float, tol_w: float
) -> list[list[_Orientada]]:
    """Parte por huecos > tolerancia alternando ejes hasta que no se pueda más."""
    pendientes = [piezas] if piezas else []
    finales: list[list[_Orientada]] = []
    while pendientes:
        parte = pendientes.pop()
        por_largo = _cortar_por_huecos(parte, "largo", tol_l)
        if len(por_largo) > 1:
            pendientes.extend(por_largo)
            continue
        por_ancho = _cortar_por_huecos(parte, "ancho", tol_w)
        if len(por_ancho) > 1:
            pendientes.extend(por_ancho)
            continue
        finales.append(parte)
    return sorted(
        finales,
        key=lambda parte: min((p.largo, p.ancho, _clave_pieza(p)) for p in parte),
    )


def _mejor_en_franja(
    franja: list[_Orientada], l0: float, tol_w: float
) -> tuple[_Puntuacion, float] | None:
    """Mejor ancla de ancho w0 para la franja de largo [l0, l0 + tol].

    Ventana deslizante sobre el ancho. Orden: más unidades, más orígenes,
    menor ancla (l0, w0).
    """
    franja = sorted(franja, key=lambda p: p.ancho)
    peso = 0
    origenes: Counter[str] = Counter()
    medidas: Counter[tuple[float, float]] = Counter()
    n_origenes = 0
    n_medidas = 0
    derecha = 0
    izquierda = 0
    mejor: tuple[_Puntuacion, float] | None = None
    for w0 in sorted({p.ancho for p in franja}):
        while izquierda < len(franja) and franja[izquierda].ancho < w0:
            saliente = franja[izquierda]
            peso -= unidades(saliente.pieza)
            origenes[saliente.pieza.origen_id] -= 1
            n_origenes -= origenes[saliente.pieza.origen_id] == 0
            medidas[(saliente.largo, saliente.ancho)] -= 1
            n_medidas -= medidas[(saliente.largo, saliente.ancho)] == 0
            izquierda += 1
        while derecha < len(franja) and franja[derecha].ancho <= w0 + tol_w:
            entrante = franja[derecha]
            peso += unidades(entrante.pieza)
            origenes[entrante.pieza.origen_id] += 1
            n_origenes += origenes[entrante.pieza.origen_id] == 1
            medidas[(entrante.largo, entrante.ancho)] += 1
            n_medidas += medidas[(entrante.largo, entrante.ancho)] == 1
            derecha += 1
        if n_origenes < 2 or n_medidas < 2:
            continue
        puntuacion = (peso, n_origenes, -l0, -w0)
        if mejor is None or puntuacion > mejor[0]:
            mejor = (puntuacion, w0)
    return mejor


def _agrupar_parte(
    piezas: list[_Orientada], tol_l: float, tol_w: float, presupuesto: _Presupuesto
) -> tuple[list[list[_Orientada]], list[_Orientada]]:
    """Voraz por ventanas dentro de una parte; cachea el mejor de cada ancla de largo.

    Al retirar un grupo solo cambian las anclas cuya franja contenía alguna
    pieza retirada (l0 en [min_retirado - tol, max_retirado]); el resto se reutiliza.
    Devuelve (grupos, piezas no evaluadas si se agota el presupuesto).
    """
    restantes = sorted(piezas, key=lambda p: (p.largo, _clave_pieza(p)))
    cache: dict[float, tuple[_Puntuacion, float] | None] = {}
    grupos: list[list[_Orientada]] = []
    while len(restantes) >= 2:
        largos = [p.largo for p in restantes]
        mejor: tuple[_Puntuacion, float, float] | None = None
        for l0 in sorted(set(largos)):
            if l0 not in cache:
                inicio = bisect_left(largos, l0)
                fin = bisect_right(largos, l0 + tol_l)
                if not presupuesto.consumir(fin - inicio + 1):
                    return grupos, restantes
                cache[l0] = (
                    _mejor_en_franja(restantes[inicio:fin], l0, tol_w)
                    if fin - inicio >= 2
                    else None
                )
            resultado = cache[l0]
            if resultado is not None and (mejor is None or resultado[0] > mejor[0]):
                mejor = (resultado[0], l0, resultado[1])
        if mejor is None:
            break
        _, l0, w0 = mejor
        elegidas = [
            p
            for p in restantes
            if l0 <= p.largo <= l0 + tol_l and w0 <= p.ancho <= w0 + tol_w
        ]
        grupos.append(sorted(elegidas, key=_clave_pieza))
        ids = {_clave_pieza(p) for p in elegidas}
        restantes = [p for p in restantes if _clave_pieza(p) not in ids]
        minimo = min(p.largo for p in elegidas) - tol_l
        maximo = max(p.largo for p in elegidas)
        for ancla in [a for a in cache if minimo <= a <= maximo]:
            del cache[ancla]
    return grupos, []


def _agrupar_clave(
    piezas: list[_Orientada],
    configuracion: ConfiguracionGemelas,
    presupuesto: _Presupuesto,
) -> tuple[list[list[_Orientada]], list[_Orientada]]:
    tol_l = configuracion.tolerancia_largo_mm + EPSILON_MM
    tol_w = configuracion.tolerancia_ancho_mm + EPSILON_MM
    grupos: list[list[_Orientada]] = []
    no_evaluadas: list[_Orientada] = []
    for parte in _particionar(piezas, tol_l, tol_w):
        if no_evaluadas:
            no_evaluadas.extend(parte)
            continue
        if len({p.pieza.origen_id for p in parte}) < 2:
            continue
        grupos_parte, pendientes = _agrupar_parte(parte, tol_l, tol_w, presupuesto)
        grupos.extend(grupos_parte)
        no_evaluadas.extend(pendientes)
    return grupos, no_evaluadas


def _construir_grupo(
    miembros: list[_Orientada], espesor: float, material: str
) -> GrupoGemelas:
    largo_std, ancho_std = _medida_estandar(miembros)
    ordenados = sorted(miembros, key=_clave_pieza)
    referencias = len({(m.largo, m.ancho) for m in ordenados})
    medida = MedidaEstandar(
        largo_mm=largo_std, ancho_mm=ancho_std, espesor_mm=espesor, material=material
    )
    return GrupoGemelas(
        grupo_id="",
        medida_estandar=medida,
        miembros=tuple(
            MiembroGemela(
                pieza=m.pieza,
                largo_orientado_mm=m.largo,
                ancho_orientado_mm=m.ancho,
                girada=m.girada,
                desviacion_largo_mm=round(m.largo - largo_std, 6),
                desviacion_ancho_mm=round(m.ancho - ancho_std, 6),
            )
            for m in ordenados
        ),
        origenes=tuple(sorted({m.pieza.origen_id for m in ordenados})),
        unidades=sum(unidades(m.pieza) for m in ordenados),
        referencias_actuales=referencias,
        ahorro_referencias=referencias - 1,
    )


def detectar_gemelas(
    piezas: Sequence[PiezaRef],
    configuracion: ConfiguracionGemelas,
    presupuesto_trabajo: int = PRESUPUESTO_TRABAJO,
) -> ResultadoGemelas:
    """Función pura: agrupa piezas casi idénticas y propone una medida estándar."""
    presupuesto = _Presupuesto(presupuesto_trabajo)
    no_evaluadas: list[_Orientada] = []
    descartadas: list[PiezaDescartada] = []
    por_clave: dict[tuple[float, str], list[_Orientada]] = defaultdict(list)
    for pieza in piezas:
        motivo = _motivo_descarte(pieza)
        if motivo is not None:
            descartadas.append(
                PiezaDescartada(
                    origen_id=pieza.origen_id, pieza_id=pieza.pieza_id, motivo=motivo
                )
            )
            continue
        material = normalizar_texto(pieza.material)
        assert material is not None and pieza.espesor_mm is not None
        por_clave[(pieza.espesor_mm, material)].append(
            _orientar(pieza, configuracion.permitir_giro)
        )

    grupos: list[GrupoGemelas] = []
    for espesor, material in sorted(por_clave):
        if no_evaluadas:
            no_evaluadas.extend(por_clave[(espesor, material)])
            continue
        grupos_clave, pendientes = _agrupar_clave(
            por_clave[(espesor, material)], configuracion, presupuesto
        )
        no_evaluadas.extend(pendientes)
        for miembros in grupos_clave:
            grupos.append(_construir_grupo(miembros, espesor, material))

    grupos.sort(
        key=lambda g: (
            -g.ahorro_referencias,
            -g.unidades,
            g.medida_estandar.espesor_mm,
            g.medida_estandar.material,
            g.medida_estandar.largo_mm,
            g.medida_estandar.ancho_mm,
            g.miembros[0].pieza.origen_id,
            g.miembros[0].pieza.pieza_id,
        )
    )
    numerados = tuple(
        g.model_copy(update={"grupo_id": f"gemelas-{indice:03d}"})
        for indice, g in enumerate(grupos, start=1)
    )
    return ResultadoGemelas(
        configuracion=configuracion,
        grupos=numerados,
        piezas_analizadas=len(piezas),
        piezas_descartadas=tuple(
            sorted(descartadas, key=lambda d: (d.origen_id, d.pieza_id))
        ),
        ahorro_referencias_total=sum(g.ahorro_referencias for g in numerados),
        origen_datos=contar_origen(piezas),
        parcial=bool(no_evaluadas),
        piezas_no_evaluadas=tuple(
            sorted(
                (
                    PiezaDescartada(
                        origen_id=p.pieza.origen_id,
                        pieza_id=p.pieza.pieza_id,
                        motivo="presupuesto de cálculo agotado",
                    )
                    for p in no_evaluadas
                ),
                key=lambda d: (d.origen_id, d.pieza_id),
            )
        ),
    )
