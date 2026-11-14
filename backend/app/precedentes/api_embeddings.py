"""Router de infraestructura de embeddings: score híbrido (2.3), regeneración (2.5) y espacio (2.6)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

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
    rotar_espacio,
    verificar_espacio,
)
from backend.app.precedentes.hibrido import (
    CandidatoHibrido,
    MotivoSemantico,
    RespuestaSimilaresHibrido,
    UmbralesHibridos,
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
from backend.app.similarity.thresholds import (
    ABSTENTION_REASON_NO_PRECEDENTS,
    resolve_similarity_threshold,
)

LIMITE_MAXIMO_REGENERACION = 100
INTERVALO_MINIMO_VERIFICACION_S = 60.0


class OperacionEnCurso(RuntimeError):
    pass


class _Exclusivo:
    """Candado no bloqueante: una sola ejecución concurrente por operación."""

    def __init__(self) -> None:
        self._candado = threading.Lock()

    @contextmanager
    def ocupar(self) -> Iterator[None]:
        if not self._candado.acquire(blocking=False):
            raise OperacionEnCurso
        try:
            yield
        finally:
            self._candado.release()


def _es_vigente(repositorio: RepositorioBiblioteca, elemento: LibraryItem) -> bool:
    try:
        return repositorio.get_run(elemento.run_id).result_revision == elemento.result_revision
    except KeyError:
        return False


class SolicitudSimilaresHibrido(ModeloEstricto):
    run_id: str = Field(min_length=1)
    result_revision: int = Field(gt=0)
    limite: int = Field(default=5, ge=1, le=50)
    peso_geometrico: float = Field(default=0.5, ge=0, allow_inf_nan=False)
    peso_semantico: float = Field(default=0.5, ge=0, allow_inf_nan=False)
    solo_sobre_umbral: bool = False


class SolicitudRegeneracion(ModeloEstricto):
    simular: bool = True
    limite: int = Field(default=50, ge=1, le=LIMITE_MAXIMO_REGENERACION)


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
    intervalo_minimo_verificacion_s: float = INTERVALO_MINIMO_VERIFICACION_S,
    reloj_monotono: Callable[[], float] = time.monotonic,
) -> APIRouter:
    """Las operaciones de pago (regenerar sin simular, verificar, rotar) se serializan con candados
    no bloqueantes (409 ``operacion_en_curso``); verificar y rotar comparten además un intervalo
    mínimo entre llamadas al proveedor (429 ``verificacion_reciente``)."""
    router = APIRouter(prefix=PREFIJO_API, tags=["precedentes-embeddings"])
    candado_regeneracion = _Exclusivo()
    candado_espacio = _Exclusivo()
    ultima_llamada_espacio: list[float] = []

    def _ocupado() -> JSONResponse:
        return _error(409, "operacion_en_curso", "Ya hay una ejecución de esta operación en curso.")

    def _espera_restante() -> float:
        if not ultima_llamada_espacio:
            return 0.0
        return max(0.0, intervalo_minimo_verificacion_s - (reloj_monotono() - ultima_llamada_espacio[0]))

    def _registrar_llamada_espacio() -> None:
        ultima_llamada_espacio[:] = [reloj_monotono()]

    def _fallo_proveedor(exc: EmbeddingProviderError) -> JSONResponse:
        codigo = str(exc) or "semantic_provider_failed"
        return _error(409 if codigo == "embedding_space_incompatible" else 502, codigo, "El proveedor no devolvió embeddings utilizables para las frases de control.")

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
        mismos = [item for item in otros if item.descriptor.descriptor_version == descriptor.descriptor_version]
        vigentes = sorted((item for item in mismos if _es_vigente(repositorio, item)), key=lambda item: item.id)
        candidatos = []
        for item in vigentes:
            vector, motivo = _vector(repositorio, item)
            candidatos.append(CandidatoHibrido(elemento=item, vector=vector, motivo_sin_vector=motivo))
        modelo = vector_consulta.metadatos.model if vector_consulta is not None else None
        umbrales = UmbralesHibridos(
            geometrico=resolve_similarity_threshold("geometric", descriptor.descriptor_version),
            semantico=resolve_similarity_threshold("semantic", descriptor.descriptor_version, model=modelo),
        )
        coincidencias = puntuar_hibrido(descriptor, vector_consulta, tuple(candidatos), pesos, umbrales)
        abstencion = not any(item.supera_umbral for item in coincidencias)
        if solicitud.solo_sobre_umbral:
            coincidencias = tuple(item for item in coincidencias if item.supera_umbral)
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
            excluidos_por_revision_obsoleta=len(mismos) - len(vigentes),
            umbrales=umbrales,
            abstencion=abstencion,
            motivo_abstencion=ABSTENTION_REASON_NO_PRECEDENTS if abstencion else None,
            coincidencias=coincidencias[:solicitud.limite],
        )
        return respuesta_ok(respuesta)

    @router.post("/embeddings/regenerar")
    def regenerar(solicitud: SolicitudRegeneracion):
        if solicitud.simular:
            return respuesta_ok(regenerar_obsoletos(repositorio, proveedor, True, solicitud.limite, ahora))
        if proveedor is None:
            return _error(503, "proveedor_no_disponible", "No hay proveedor de embeddings configurado; usa simular=true.")
        try:
            with candado_regeneracion.ocupar():
                informe = regenerar_obsoletos(repositorio, proveedor, False, solicitud.limite, ahora)
        except OperacionEnCurso:
            return _ocupado()
        return respuesta_ok(informe)

    def _operacion_espacio(operacion: Callable[[], object]) -> object:
        if proveedor is None:
            return _error(503, "proveedor_no_disponible", "No hay proveedor de embeddings configurado.")
        try:
            with candado_espacio.ocupar():
                espera = _espera_restante()
                if espera > 0:
                    return _error(429, "verificacion_reciente", f"Espera {espera:.0f} s antes de volver a consultar el proveedor.")
                _registrar_llamada_espacio()
                try:
                    return respuesta_ok(operacion())
                except EmbeddingProviderError as exc:
                    return _fallo_proveedor(exc)
        except OperacionEnCurso:
            return _ocupado()

    @router.post("/embeddings/espacio/verificar")
    def verificar(solicitud: SolicitudVerificacionEspacio | None = None):
        tolerancia = (solicitud or SolicitudVerificacionEspacio()).tolerancia
        return _operacion_espacio(lambda: verificar_espacio(proveedor, almacen_espacio, tolerancia, ahora))

    @router.post("/embeddings/espacio/rotar")
    def rotar():
        """Rotación explícita: guarda la huella actual como referencia y archiva la anterior con fecha."""
        return _operacion_espacio(lambda: rotar_espacio(proveedor, almacen_espacio, ahora))

    @router.get("/embeddings/espacio/historico")
    def historico_espacio():
        return respuesta_ok([item.model_dump(mode="json") for item in almacen_espacio.listar_historico()])

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
