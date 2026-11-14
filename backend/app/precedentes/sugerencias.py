"""Idea 2.1: sugerencias de valores que faltan a partir de precedentes de la biblioteca.

Los vecinos se eligen filtrando por versión de descriptor, familia conocida y coincidente
(si la consulta no tiene familia, abstención global), estructura coincidente cuando ambas se
conocen y un score geométrico mínimo, ordenando por ``geometric_match`` (que sólo puntúa medidas conocidas). Nunca se ordena por el
coseno del texto completo, que incluye las propias incógnitas.

Cada sugerencia es una ``hipotesis`` con soporte n/N, rango e ids de los vecinos; si el soporte
o el número de vecinos no alcanzan el mínimo configurado, el campo queda en ``abstencion``.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import Field, model_validator

from backend.app.contratos.modelos import LibraryItem
from backend.app.precedentes.campos_descriptor import (
    Descriptor,
    TipoCampo,
    campo_desconocido,
    campos_sugeribles,
    estructura,
    familia,
    valor_campo,
)
from backend.app.precedentes.comun import ModeloEstricto, normalizar_texto
from backend.app.semantic.descriptor import descriptor_fingerprint
from backend.app.similarity.service import geometric_match
from backend.app.similarity.thresholds import resolve_similarity_threshold

ValorSugerido = float | str | tuple[float, ...]

# Sin ``score_minimo`` explícito se usa el umbral de similitud geométrica calibrado por la idea 1.2
# (``similarity.thresholds``, configurable con ``VEXPLORER_SIMILARITY_THRESHOLDS_FILE`` por versión de
# descriptor). Las medidas desconocidas de la consulta puntúan 0 en ``geometric_match``, así que una
# consulta muy incompleta tenderá a abstenerse.


def techo_geometrico(consulta: Descriptor) -> float:
    """Máximo ``geometric_match`` alcanzable por la consulta: su similitud consigo misma.

    ``geometric_match`` puntúa 0 las medidas desconocidas, y en 2.1 la consulta tiene precisamente
    los campos que se quieren sugerir. Sin este techo, un vecino idéntico en todo lo conocido no
    alcanzaría nunca el umbral calibrado para muebles completos.
    """
    propio = LibraryItem(
        id="consulta",
        run_id="consulta",
        result_revision=1,
        label="consulta",
        descriptor=consulta,
        descriptor_fingerprint=descriptor_fingerprint(consulta),
        created_at="1970-01-01T00:00:00+00:00",
    )
    return geometric_match(consulta, propio).score


def umbral_vecinos(descriptor_version: str, score_minimo: float | None) -> float:
    """Umbral geométrico aplicado: el explícito o el calibrado para la versión de descriptor."""
    if score_minimo is not None:
        return score_minimo
    return resolve_similarity_threshold("geometric", descriptor_version)

# Campos categóricos de texto libre que se comparan tras ``normalizar_texto``.
CAMPOS_TEXTO_NORMALIZADO = frozenset({"material", "finish"})


class ParametrosSugerencia(ModeloEstricto):
    k: int = Field(default=8, ge=1, le=50)
    soporte_minimo: float = Field(default=0.6, gt=0, le=1, allow_inf_nan=False)
    vecinos_minimos: int = Field(default=3, ge=1, le=50)
    score_minimo: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    tolerancia_relativa: float = Field(default=0.05, ge=0, le=1, allow_inf_nan=False)


class PeticionSugerencias(ParametrosSugerencia):
    run_id: str = Field(min_length=1)
    result_revision: int = Field(gt=0)


class VecinoUsado(ModeloEstricto):
    library_item_id: str
    run_id: str
    result_revision: int
    score: float  # relativo al techo alcanzable por la consulta; es el que se compara con el umbral
    score_geometrico: float  # ``geometric_match`` tal cual


class Exclusiones(ModeloEstricto):
    mismo_run: int = 0
    otra_version: int = 0
    revision_obsoleta: int = 0
    familia_distinta_o_desconocida: int = 0
    estructura_distinta: int = 0
    score_insuficiente: int = 0
    fuera_de_k: int = 0


class SugerenciaCampo(ModeloEstricto):
    campo: str
    tipo: TipoCampo
    estado: Literal["hipotesis", "abstencion"]
    valor: ValorSugerido | None = None
    soporte: int = Field(ge=0, description="Vecinos cuyo valor coincide con el sugerido (n).")
    total: int = Field(ge=0, description="Vecinos con el campo conocido (N).")
    proporcion: float = Field(ge=0, le=1)
    rango_min: float | None = None
    rango_max: float | None = None
    vecinos_ids: tuple[str, ...] = Field(description="Vecinos con el campo conocido (procedencia).")
    vecinos_a_favor_ids: tuple[str, ...] = Field(description="Vecinos que respaldan el valor sugerido.")
    motivo: str | None = None

    @model_validator(mode="after")
    def coherencia(self) -> SugerenciaCampo:
        if self.estado == "hipotesis" and self.valor is None:
            raise ValueError("una hipotesis necesita valor")
        if self.estado == "abstencion" and self.motivo is None:
            raise ValueError("una abstencion necesita motivo")
        return self


class ResultadoSugerencias(ModeloEstricto):
    run_id: str
    result_revision: int
    descriptor_version: str
    parametros: ParametrosSugerencia
    vecinos: tuple[VecinoUsado, ...]
    exclusiones: Exclusiones
    motivo_abstencion_global: str | None = None
    sugerencias: tuple[SugerenciaCampo, ...]
    aviso: str = (
        "Sugerencias derivadas de precedentes: son hipótesis, no medidas observadas. "
        "Deben aceptarse explícitamente en Revisar."
    )


def seleccionar_vecinos(
    consulta: Descriptor,
    elementos: tuple[LibraryItem, ...],
    *,
    run_id: str,
    revisiones_vigentes: dict[str, int],
    k: int,
    score_minimo: float,
) -> tuple[tuple[tuple[LibraryItem, float], ...], Exclusiones]:
    """Vecinos ordenados por score relativo al techo de la consulta (desc.) y desempate por id. Función pura."""
    contadores = Counter[str]()
    candidatos: list[tuple[LibraryItem, float]] = []
    techo = techo_geometrico(consulta)
    familia_consulta, estructura_consulta = familia(consulta), estructura(consulta)
    for item in elementos:
        if item.run_id == run_id:
            contadores["mismo_run"] += 1
            continue
        if item.descriptor.descriptor_version != consulta.descriptor_version:
            contadores["otra_version"] += 1
            continue
        if revisiones_vigentes.get(item.run_id) != item.result_revision:
            contadores["revision_obsoleta"] += 1
            continue
        familia_item, estructura_item = familia(item.descriptor), estructura(item.descriptor)
        if familia_consulta is None or familia_item != familia_consulta:
            contadores["familia_distinta_o_desconocida"] += 1
            continue
        if estructura_consulta and estructura_item and estructura_consulta != estructura_item:
            contadores["estructura_distinta"] += 1
            continue
        bruto = geometric_match(consulta, item).score
        score = min(1.0, round(bruto / techo, 6)) if techo > 0 else 0.0
        if score < score_minimo:
            contadores["score_insuficiente"] += 1
            continue
        candidatos.append((item, score))
    candidatos.sort(key=lambda par: (-par[1], par[0].id))
    contadores["fuera_de_k"] = max(0, len(candidatos) - k)
    return tuple(candidatos[:k]), Exclusiones(**contadores)


def _mediana(valores: list[float]) -> float:
    ordenados = sorted(valores)
    mitad = len(ordenados) // 2
    if len(ordenados) % 2:
        return ordenados[mitad]
    return (ordenados[mitad - 1] + ordenados[mitad]) / 2


def sugerir_campo(
    campo: str,
    tipo: TipoCampo,
    vecinos: tuple[tuple[LibraryItem, float], ...],
    parametros: ParametrosSugerencia,
) -> SugerenciaCampo:
    """Moda (categórico/lista) o mediana (numérico) del campo entre los vecinos que lo conocen."""
    conocidos: list[tuple[str, ValorSugerido]] = []
    for item, _score in vecinos:
        if campo_desconocido(item.descriptor, campo):
            continue
        valor = valor_campo(item.descriptor, campo)
        if campo in CAMPOS_TEXTO_NORMALIZADO and isinstance(valor, str):
            valor = normalizar_texto(valor)
        if valor is not None:
            conocidos.append((item.id, valor))
    ids = tuple(sorted(item_id for item_id, _ in conocidos))
    total = len(conocidos)
    base = {"campo": campo, "tipo": tipo, "total": total, "vecinos_ids": ids}
    if total == 0:
        return SugerenciaCampo(**base, estado="abstencion", soporte=0, proporcion=0.0, vecinos_a_favor_ids=(), motivo="ningun_vecino_conoce_el_campo")

    rango_min = rango_max = None
    if tipo == "numerico":
        numeros = [float(valor) for _, valor in conocidos]  # type: ignore[arg-type]
        sugerido: ValorSugerido = round(_mediana(numeros), 3)
        tolerancia = abs(sugerido) * parametros.tolerancia_relativa
        a_favor = tuple(sorted(item_id for item_id, valor in conocidos if abs(float(valor) - sugerido) <= tolerancia))  # type: ignore[arg-type]
        rango_min, rango_max = min(numeros), max(numeros)
    else:
        frecuencias = Counter(valor for _, valor in conocidos)
        sugerido = min(frecuencias, key=lambda valor: (-frecuencias[valor], repr(valor)))
        a_favor = tuple(sorted(item_id for item_id, valor in conocidos if valor == sugerido))
        if tipo == "lista_mm":
            espesores = [espesor for _, valor in conocidos for espesor in valor]  # type: ignore[union-attr]
            rango_min, rango_max = min(espesores), max(espesores)
    soporte = len(a_favor)
    proporcion = round(soporte / total, 6)
    motivo = None
    if total < parametros.vecinos_minimos:
        motivo = f"vecinos_insuficientes: {total} < {parametros.vecinos_minimos}"
    elif proporcion < parametros.soporte_minimo:
        motivo = f"soporte_insuficiente: {soporte}/{total} < {parametros.soporte_minimo:g}"
    return SugerenciaCampo(
        **base,
        estado="abstencion" if motivo else "hipotesis",
        valor=None if motivo else sugerido,
        soporte=soporte,
        proporcion=proporcion,
        rango_min=rango_min,
        rango_max=rango_max,
        vecinos_a_favor_ids=a_favor,
        motivo=motivo,
    )


def sugerir_valores(
    consulta: Descriptor,
    elementos: tuple[LibraryItem, ...],
    *,
    run_id: str,
    result_revision: int,
    revisiones_vigentes: dict[str, int],
    parametros: ParametrosSugerencia,
) -> ResultadoSugerencias:
    """Sugerencias para cada campo desconocido del descriptor de consulta.

    Determinista para una misma configuración de umbrales calibrados (``similarity.thresholds``).
    """
    parametros = parametros.model_copy(
        update={"score_minimo": umbral_vecinos(consulta.descriptor_version, parametros.score_minimo)}
    )
    desconocidos = tuple((campo, tipo) for campo, tipo in campos_sugeribles(consulta) if campo_desconocido(consulta, campo))
    if familia(consulta) is None:
        motivo = "familia_desconocida: sin familia no hay precedentes comparables"
        return ResultadoSugerencias(
            run_id=run_id,
            result_revision=result_revision,
            descriptor_version=consulta.descriptor_version,
            parametros=parametros,
            vecinos=(),
            exclusiones=Exclusiones(),
            motivo_abstencion_global=motivo,
            sugerencias=tuple(
                SugerenciaCampo(campo=campo, tipo=tipo, estado="abstencion", soporte=0, total=0, proporcion=0.0, vecinos_ids=(), vecinos_a_favor_ids=(), motivo=motivo)
                for campo, tipo in desconocidos
            ),
        )
    vecinos, exclusiones = seleccionar_vecinos(
        consulta,
        elementos,
        run_id=run_id,
        revisiones_vigentes=revisiones_vigentes,
        k=parametros.k,
        score_minimo=parametros.score_minimo,
    )
    sugerencias = tuple(sugerir_campo(campo, tipo, vecinos, parametros) for campo, tipo in desconocidos)
    return ResultadoSugerencias(
        run_id=run_id,
        result_revision=result_revision,
        descriptor_version=consulta.descriptor_version,
        parametros=parametros,
        vecinos=tuple(
            VecinoUsado(
                library_item_id=item.id,
                run_id=item.run_id,
                result_revision=item.result_revision,
                score=score,
                score_geometrico=geometric_match(consulta, item).score,
            )
            for item, score in vecinos
        ),
        exclusiones=exclusiones,
        sugerencias=sugerencias,
    )
