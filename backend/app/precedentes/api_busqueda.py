"""Router FastAPI de la idea 3.2 (búsqueda en lenguaje natural sobre la biblioteca)."""

from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.app.agente.config import ProviderSettings
from backend.app.contratos.modelos import LibraryItem, RunSnapshot
from backend.app.precedentes.api_sugerencias import revisiones_vigentes
from backend.app.precedentes.busqueda import (
    INSTRUCCIONES_TRADUCTOR,
    ErrorTraduccion,
    PeticionBusqueda,
    ProveedorTraduccion,
    ResultadoBusqueda,
    filtrar_biblioteca,
    reubicar_roles_desconocidos,
    traducir_consulta,
)
from backend.app.precedentes.comun import PREFIJO_API, respuesta_error, respuesta_ok


class RepositorioBusqueda(Protocol):
    def get_run(self, run_id: str) -> RunSnapshot: ...

    def get_library_items(self) -> tuple[LibraryItem, ...]: ...


def crear_proveedor_traductor(settings: ProviderSettings) -> ProveedorTraduccion | None:
    """Proveedor OpenAI con las instrucciones del traductor, o ``None`` si no hay configuración."""
    if not settings.available:
        return None
    from backend.app.agente.provider import OpenAIResponsesProvider

    return OpenAIResponsesProvider(settings, instructions=INSTRUCCIONES_TRADUCTOR)


def crear_router_busqueda(
    repositorio: RepositorioBusqueda,
    proveedor: ProveedorTraduccion | None = None,
    *,
    timeout_s: float = 20.0,
    max_intentos: int = 2,
) -> APIRouter:
    router = APIRouter(prefix=PREFIJO_API + "/busqueda", tags=["precedentes"])

    @router.post("")
    def buscar(peticion: PeticionBusqueda) -> JSONResponse:
        usado_llm = False
        if peticion.filtros is not None:
            filtros = peticion.filtros
        else:
            if proveedor is None:
                return JSONResponse(status_code=503, content=respuesta_error("proveedor_no_disponible", "No hay proveedor LLM configurado; envía filtros estructurados."))
            try:
                filtros = traducir_consulta(peticion.consulta or "", proveedor, timeout_s=timeout_s, max_intentos=max_intentos)
            except ErrorTraduccion as exc:
                return JSONResponse(status_code=502, content=respuesta_error(exc.codigo, exc.mensaje))
            usado_llm = True
        elementos = repositorio.get_library_items()
        vigentes = revisiones_vigentes(repositorio, elementos)
        filtros, avisos = reubicar_roles_desconocidos(
            filtros, tuple(item for item in elementos if vigentes.get(item.run_id) == item.result_revision)
        )
        resultados, obsoletos, descartados = filtrar_biblioteca(filtros, elementos, vigentes, peticion.limite)
        valor = ResultadoBusqueda(
            consulta=peticion.consulta,
            usado_llm=usado_llm,
            filtros_aplicados=filtros.model_copy(update={"terminos_no_interpretados": ()}),
            terminos_no_interpretados=filtros.terminos_no_interpretados,
            avisos=avisos,
            total_candidatos=len(elementos),
            excluidos_revision_obsoleta=obsoletos,
            excluidos_por_filtros=descartados,
            resultados=resultados,
        )
        return JSONResponse(status_code=200, content=respuesta_ok(valor))

    return router
