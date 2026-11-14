"""Router de infraestructura de embeddings: score híbrido (2.3), regeneración (2.5) y espacio (2.6)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import Field

from backend.app.contratos.modelos import LibraryItem
from backend.app.precedentes.comun import (
    PREFIJO_API,
    ModeloEstricto,
    respuesta_error,
    respuesta_ok,
)
from backend.app.precedentes.espacio import (
    TOLERANCIA_POR_DEFECTO,
    AlmacenEspacio,
    resumir,
    verificar_espacio,
)
from backend.app.precedentes.hibrido import (
    CandidatoHibrido,
    MotivoSemantico,
    RespuestaSimilaresHibrido,
    VectorEtiquetado,
    normalizar_pesos,
    puntuar_hibrido,
)
from backend.app.precedentes.regeneracion import (
    ProveedorEmbeddings,
    RepositorioBiblioteca,
    ahora_utc,
    regenerar_obsoletos,
)
from backend.app.semantic.descriptor import build_descriptor
from backend.app.semantic.embeddings import EmbeddingProviderError


class SolicitudSimilaresHibrido(ModeloEstricto):
    run_id: str = Field(min_length=1)
    result_revision: int = Field(gt=0)
    limite: int = Field(default=5, ge=1, le=50)
    peso_geometrico: float = Field(default=0.5, ge=0, allow_inf_nan=False)
    peso_semantico: float = Field(default=0.5, ge=0, allow_inf_nan=False)


class SolicitudRegeneracion(ModeloEstricto):
    simular: bool = True
    limite: int = Field(default=50, ge=1, le=500)


class SolicitudVerificacionEspacio(ModeloEstricto):
    tolerancia: float = Field(default=TOLERANCIA_POR_DEFECTO, gt=0, le=1, allow_inf_nan=False)


def _error(estado: int, codigo: str, mensaje: str) -> JSONResponse:
    return JSONResponse(status_code=estado, content=respuesta_error(codigo, mensaje))


def _vector(repositorio: RepositorioBiblioteca, elemento: LibraryItem) -> tuple[VectorEtiquetado | None, MotivoSemantico | None]:
    metadatos = elemento.embedding
    if metadatos is None:
        return None, "candidato_sin_embedding"
    try:
        vector = repositorio.get_embedding(metadatos.cache_key, metadatos.model, metadatos.dimensions, metadatos.descriptor_version)
    except KeyError:
        return None, "candidato_sin_embedding"
    except ValueError as exc:
        return None, "embedding_space_incompatible" if str(exc) == "embedding_space_incompatible" else "invalid_embedding"
    except EmbeddingProviderError:
        return None, "invalid_embedding"
    return VectorEtiquetado(metadatos=metadatos, vector=vector), None


def crear_router_embeddings(
    repositorio: RepositorioBiblioteca,
    proveedor: ProveedorEmbeddings | None,
    almacen_espacio: AlmacenEspacio,
    ahora: Callable[[], str] = ahora_utc,
) -> APIRouter:
    router = APIRouter(prefix=PREFIJO_API, tags=["precedentes-embeddings"])

    @router.post("/similares-hibrido")
    def similares_hibrido(solicitud: SolicitudSimilaresHibrido):
        try:
            pesos = normalizar_pesos(solicitud.peso_geometrico, solicitud.peso_semantico)
        except ValueError:
            return _error(422, "pesos_invalidos", "Los pesos deben ser ≥0 y sumar más de 0.")
        try:
            resultado = repositorio.get_result(solicitud.run_id, solicitud.result_revision)
        except KeyError:
            return _error(404, "result_not_found", "Revisión inexistente.")
        try:
            descriptor = build_descriptor(resultado)
        except ValueError as exc:
            return _error(409, "descriptor_no_disponible", f"La revisión no admite descriptor: {exc}.")
        vector_consulta: VectorEtiquetado | None = None
        motivo_consulta: MotivoSemantico | None = "consulta_sin_embedding"
        consulta = next((item for item in repositorio.get_library_items() if item.run_id == solicitud.run_id), None)
        if consulta is not None and consulta.result_revision == solicitud.result_revision:
            vector_consulta, motivo = _vector(repositorio, consulta)
            motivo_consulta = None if vector_consulta is not None else ("consulta_sin_embedding" if motivo == "candidato_sin_embedding" else motivo)
        otros = [item for item in repositorio.get_library_items() if item.run_id != solicitud.run_id]
        mismos = sorted((item for item in otros if item.descriptor.descriptor_version == descriptor.descriptor_version), key=lambda item: item.id)
        candidatos = []
        for item in mismos:
            vector, motivo = _vector(repositorio, item)
            candidatos.append(CandidatoHibrido(elemento=item, vector=vector, motivo_sin_vector=motivo))
        coincidencias = puntuar_hibrido(descriptor, vector_consulta, tuple(candidatos), pesos)
        if vector_consulta is None:
            coincidencias = tuple(item.model_copy(update={"motivo_semantico_no_disponible": motivo_consulta}) for item in coincidencias)
        respuesta = RespuestaSimilaresHibrido(
            run_id=solicitud.run_id,
            result_revision=solicitud.result_revision,
            descriptor_version=descriptor.descriptor_version,
            pesos_solicitados=pesos,
            consulta_semantica_disponible=vector_consulta is not None,
            motivo_consulta_sin_semantica=motivo_consulta,
            excluidos_por_descriptor=len(otros) - len(mismos),
            coincidencias=coincidencias[:solicitud.limite],
        )
        return respuesta_ok(respuesta)

    @router.post("/embeddings/regenerar")
    def regenerar(solicitud: SolicitudRegeneracion):
        try:
            informe = regenerar_obsoletos(repositorio, proveedor, solicitud.simular, solicitud.limite, ahora)
        except LookupError:
            return _error(503, "proveedor_no_disponible", "No hay proveedor de embeddings configurado; usa simular=true.")
        return respuesta_ok(informe)

    @router.post("/embeddings/espacio/verificar")
    def verificar(solicitud: SolicitudVerificacionEspacio | None = None):
        if proveedor is None:
            return _error(503, "proveedor_no_disponible", "No hay proveedor de embeddings configurado.")
        tolerancia = (solicitud or SolicitudVerificacionEspacio()).tolerancia
        try:
            resultado = verificar_espacio(proveedor, almacen_espacio, tolerancia, ahora)
        except EmbeddingProviderError as exc:
            codigo = str(exc) or "semantic_provider_failed"
            return _error(409 if codigo == "embedding_space_incompatible" else 502, codigo, "El proveedor no devolvió embeddings utilizables para las frases de control.")
        return respuesta_ok(resultado)

    @router.get("/embeddings/espacio")
    def referencia_espacio(
        modelo: str | None = None,
        dimensiones: int | None = Query(default=None, gt=0),
        incluir_vectores: bool = False,
    ):
        referencias = [
            item for item in almacen_espacio.listar()
            if (modelo is None or item.modelo == modelo) and (dimensiones is None or item.dimensiones == dimensiones)
        ]
        if (modelo is not None or dimensiones is not None) and not referencias:
            return _error(404, "referencia_no_encontrada", "No hay huella de referencia para ese espacio.")
        return respuesta_ok([resumir(item, incluir_vectores).model_dump(mode="json") for item in referencias])

    return router
