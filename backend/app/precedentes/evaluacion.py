"""Evaluación reproducible de recuperación de precedentes (idea 2.7).

Formato de juicios graduados y métricas puras de ranking. Convenciones:

- Relevancia graduada por candidato: 0 (no comparable), 1 (parcialmente), 2 (comparable).
- Un candidato del ranking sin juicio cuenta como no relevante (grado 0), pero se
  reporta en ``candidatos_sin_juicio`` para medir la cobertura de los juicios.
- Relevante para precision/recall/MRR significa grado >= 1.
- precision@k divide siempre entre ``k`` aunque el ranking tenga menos elementos.
- recall@k, MRR y nDCG@k son ``None`` (indefinidos) si la consulta no tiene ningún
  candidato juzgado como relevante; esas consultas se excluyen de la media
  correspondiente y se cuentan en ``consultas_sin_relevantes``.
- MRR usa el ranking completo (sin corte en ``k``); 0 si hay relevantes juzgados pero ninguno aparece.
- nDCG usa ganancia exponencial ``2^grado - 1`` y descuento ``log2(posición + 1)``;
  el DCG ideal se calcula con todos los grados juzgados, no solo con los del ranking.

Un conjunto ``synthetic`` solo sirve para probar el mecanismo; no es evidencia de calidad.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import Field, model_validator

from backend.app.precedentes.comun import ModeloEstricto

Grado = Literal[0, 1, 2]


class JuiciosConsulta(ModeloEstricto):
    consulta_id: str = Field(min_length=1)
    relevancias: dict[str, Grado]
    nota: str | None = None

    @model_validator(mode="after")
    def _sin_autojuicio(self) -> JuiciosConsulta:
        if self.consulta_id in self.relevancias:
            raise ValueError("una consulta no puede juzgarse a sí misma")
        return self


class ConjuntoJuicios(ModeloEstricto):
    version: str = Field(min_length=1)
    origen: Literal["synthetic", "team_reviewed", "derived_reference"]
    descripcion: str = Field(min_length=1)
    consultas: tuple[JuiciosConsulta, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consultas_unicas(self) -> ConjuntoJuicios:
        ids = [item.consulta_id for item in self.consultas]
        if len(ids) != len(set(ids)):
            raise ValueError("consulta_id duplicado en el conjunto de juicios")
        return self


class MetricasConsulta(ModeloEstricto):
    consulta_id: str
    k: int
    precision_k: float
    recall_k: float | None
    mrr: float | None
    ndcg_k: float | None
    candidatos_rankeados: int
    candidatos_sin_juicio: int
    relevantes_juzgados: int


class MetricasAgregadas(ModeloEstricto):
    k: int
    consultas: int
    consultas_sin_relevantes: int
    precision_k: float | None
    recall_k: float | None
    mrr: float | None
    ndcg_k: float | None
    candidatos_sin_juicio: int
    candidatos_rankeados: int
    cobertura_juicios: float | None


def precision_en_k(ranking: tuple[str, ...], relevancias: dict[str, int], k: int) -> float:
    _validar_k(k)
    return sum(1 for item in ranking[:k] if relevancias.get(item, 0) >= 1) / k


def recall_en_k(ranking: tuple[str, ...], relevancias: dict[str, int], k: int) -> float | None:
    _validar_k(k)
    total = sum(1 for grado in relevancias.values() if grado >= 1)
    if total == 0:
        return None
    return sum(1 for item in ranking[:k] if relevancias.get(item, 0) >= 1) / total


def rango_reciproco(ranking: tuple[str, ...], relevancias: dict[str, int]) -> float:
    for posicion, item in enumerate(ranking, start=1):
        if relevancias.get(item, 0) >= 1:
            return 1.0 / posicion
    return 0.0


def _dcg(grados: list[int]) -> float:
    return sum((2**grado - 1) / math.log2(posicion + 1) for posicion, grado in enumerate(grados, start=1))


def ndcg_en_k(ranking: tuple[str, ...], relevancias: dict[str, int], k: int) -> float | None:
    _validar_k(k)
    ideal = _dcg(sorted(relevancias.values(), reverse=True)[:k])
    if ideal == 0:
        return None
    return _dcg([relevancias.get(item, 0) for item in ranking[:k]]) / ideal


def _validar_k(k: int) -> None:
    if k < 1:
        raise ValueError("k debe ser >= 1")


def evaluar_consulta(consulta_id: str, ranking: tuple[str, ...], relevancias: dict[str, int], k: int) -> MetricasConsulta:
    """Métricas de una consulta. ``ranking`` es la lista de ids ordenada (mejor primero)."""
    if len(ranking) != len(set(ranking)):
        raise ValueError("el ranking contiene ids duplicados")
    return MetricasConsulta(
        consulta_id=consulta_id,
        k=k,
        precision_k=round(precision_en_k(ranking, relevancias, k), 6),
        recall_k=_redondear(recall_en_k(ranking, relevancias, k)),
        mrr=round(rango_reciproco(ranking, relevancias), 6) if any(grado >= 1 for grado in relevancias.values()) else None,
        ndcg_k=_redondear(ndcg_en_k(ranking, relevancias, k)),
        candidatos_rankeados=len(ranking),
        candidatos_sin_juicio=sum(1 for item in ranking if item not in relevancias),
        relevantes_juzgados=sum(1 for grado in relevancias.values() if grado >= 1),
    )


def _redondear(valor: float | None) -> float | None:
    return None if valor is None else round(valor, 6)


def _media(valores: list[float | None]) -> float | None:
    definidos = [item for item in valores if item is not None]
    return round(sum(definidos) / len(definidos), 6) if definidos else None


def agregar(metricas: tuple[MetricasConsulta, ...], k: int) -> MetricasAgregadas:
    """Media aritmética por consulta; recall/nDCG ignoran consultas sin relevantes."""
    ordenadas = sorted(metricas, key=lambda item: item.consulta_id)
    rankeados = sum(item.candidatos_rankeados for item in ordenadas)
    sin_juicio = sum(item.candidatos_sin_juicio for item in ordenadas)
    return MetricasAgregadas(
        k=k,
        consultas=len(ordenadas),
        consultas_sin_relevantes=sum(1 for item in ordenadas if item.relevantes_juzgados == 0),
        precision_k=_media([item.precision_k for item in ordenadas]),
        recall_k=_media([item.recall_k for item in ordenadas]),
        mrr=_media([item.mrr for item in ordenadas]),
        ndcg_k=_media([item.ndcg_k for item in ordenadas]),
        candidatos_sin_juicio=sin_juicio,
        candidatos_rankeados=rankeados,
        cobertura_juicios=round((rankeados - sin_juicio) / rankeados, 6) if rankeados else None,
    )
