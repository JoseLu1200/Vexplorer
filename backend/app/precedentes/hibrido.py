"""Idea 2.3: score híbrido = w_geo·geométrico + w_sem·semántico con componentes visibles.

El componente geométrico es el de ``geometric_match`` (determinista, sin IA). El semántico es el
coseno entre vectores ya guardados en el mismo espacio (modelo, dimensiones, versión de descriptor).
Si no hay embedding compatible, el componente semántico queda en ``None``, el score es solo
geométrico y se marca ``semantico_disponible=False`` con su motivo: nunca se oculta.

Limitación conocida: el texto embebido (``semantic_text``) sigue incluyendo medidas e incógnitas
(hallazgos H1/H2). Sacarlas requiere una nueva ``descriptor_version`` y volver a embeber.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import Field

from backend.app.contratos.modelos import (
    EmbeddingMetadata,
    LibraryItem,
    SimilarityDifference,
)
from backend.app.precedentes.comun import ModeloEstricto
from backend.app.similarity.service import (
    Descriptor,
    cosine_similarity,
    geometric_match,
)

MotivoSemantico = Literal[
    "consulta_sin_embedding",
    "candidato_sin_embedding",
    "embedding_space_incompatible",
    "invalid_embedding",
]


class PesosHibridos(ModeloEstricto):
    geometrico: float = Field(ge=0, le=1, allow_inf_nan=False)
    semantico: float = Field(ge=0, le=1, allow_inf_nan=False)


class VectorEtiquetado(ModeloEstricto):
    """Vector guardado junto con los metadatos que definen su espacio."""

    metadatos: EmbeddingMetadata
    vector: tuple[float, ...]


class CandidatoHibrido(ModeloEstricto):
    elemento: LibraryItem
    vector: VectorEtiquetado | None = None
    motivo_sin_vector: MotivoSemantico | None = None


class CoincidenciaHibrida(ModeloEstricto):
    library_item_id: str
    run_id: str
    result_revision: int
    score: float = Field(allow_inf_nan=False)
    score_kind: Literal["hibrido"] = "hibrido"
    geometrico: float = Field(allow_inf_nan=False)
    semantico: float | None = None
    semantico_disponible: bool
    motivo_semantico_no_disponible: MotivoSemantico | None = None
    pesos_efectivos: PesosHibridos
    componentes_geometricos: dict[str, float]
    diferencias: tuple[SimilarityDifference, ...]


class RespuestaSimilaresHibrido(ModeloEstricto):
    run_id: str
    result_revision: int
    descriptor_version: str
    pesos_solicitados: PesosHibridos
    consulta_semantica_disponible: bool
    motivo_consulta_sin_semantica: MotivoSemantico | None = None
    excluidos_por_descriptor: int = Field(ge=0)
    coincidencias: tuple[CoincidenciaHibrida, ...]


def normalizar_pesos(peso_geometrico: float, peso_semantico: float) -> PesosHibridos:
    """Valida (≥0, finitos, suma >0) y normaliza para que sumen 1."""
    valores = (peso_geometrico, peso_semantico)
    if any(not math.isfinite(valor) or valor < 0 for valor in valores):
        raise ValueError("pesos_invalidos")
    total = peso_geometrico + peso_semantico
    if total <= 0:
        raise ValueError("pesos_invalidos")
    geometrico = round(peso_geometrico / total, 6)
    return PesosHibridos(geometrico=geometrico, semantico=round(1 - geometrico, 6))


def _espacio(metadatos: EmbeddingMetadata) -> tuple[str, int, str]:
    return (metadatos.model, metadatos.dimensions, metadatos.descriptor_version)


def componente_semantico(
    consulta: VectorEtiquetado | None,
    candidato: CandidatoHibrido,
) -> tuple[float | None, MotivoSemantico | None]:
    """Coseno si ambos vectores existen y comparten espacio; si no, ``None`` y motivo."""
    if consulta is None:
        return None, "consulta_sin_embedding"
    if candidato.vector is None:
        return None, candidato.motivo_sin_vector or "candidato_sin_embedding"
    if _espacio(consulta.metadatos) != _espacio(candidato.vector.metadatos):
        return None, "embedding_space_incompatible"
    try:
        valor = cosine_similarity(consulta.vector, candidato.vector.vector)
    except ValueError as exc:
        codigo = str(exc)
        return None, "embedding_space_incompatible" if codigo == "embedding_space_incompatible" else "invalid_embedding"
    return round(valor, 6), None


def puntuar_hibrido(
    descriptor_consulta: Descriptor,
    vector_consulta: VectorEtiquetado | None,
    candidatos: tuple[CandidatoHibrido, ...],
    pesos: PesosHibridos,
) -> tuple[CoincidenciaHibrida, ...]:
    """Función pura: puntúa candidatos del mismo ``descriptor_version`` y ordena por (-score, id).

    Si falta el componente semántico, los pesos efectivos pasan a (1, 0) para ese candidato.
    """
    coincidencias: list[CoincidenciaHibrida] = []
    for candidato in candidatos:
        geometrico = geometric_match(descriptor_consulta, candidato.elemento)
        semantico, motivo = componente_semantico(vector_consulta, candidato)
        if semantico is None:
            efectivos = PesosHibridos(geometrico=1.0, semantico=0.0)
            score = geometrico.score
        else:
            efectivos = pesos
            score = pesos.geometrico * geometrico.score + pesos.semantico * semantico
        coincidencias.append(CoincidenciaHibrida(
            library_item_id=candidato.elemento.id,
            run_id=candidato.elemento.run_id,
            result_revision=candidato.elemento.result_revision,
            score=round(score, 6),
            geometrico=geometrico.score,
            semantico=semantico,
            semantico_disponible=semantico is not None,
            motivo_semantico_no_disponible=motivo,
            pesos_efectivos=efectivos,
            componentes_geometricos=dict(geometrico.score_components),
            diferencias=geometrico.differences,
        ))
    coincidencias.sort(key=lambda item: (-item.score, item.library_item_id))
    return tuple(coincidencias)
