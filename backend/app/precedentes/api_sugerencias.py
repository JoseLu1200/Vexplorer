"""Router FastAPI de la idea 2.1 (sugerencias de valores que faltan por precedentes)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.app.contratos.modelos import LibraryItem, Result, RunSnapshot
from backend.app.precedentes.campos_descriptor import Descriptor
from backend.app.precedentes.comun import PREFIJO_API, respuesta_error, respuesta_ok
from backend.app.precedentes.sugerencias import (
    ParametrosSugerencia,
    PeticionSugerencias,
    sugerir_valores,
)
from backend.app.semantic.descriptor import build_descriptor


class RepositorioSugerencias(Protocol):
    def get_result(self, run_id: str, revision: int | None = None) -> Result: ...

    def get_run(self, run_id: str) -> RunSnapshot: ...

    def get_library_items(self) -> tuple[LibraryItem, ...]: ...


def revisiones_vigentes(repositorio: Any, elementos: tuple[LibraryItem, ...]) -> dict[str, int]:
    """Revisión vigente de cada run de la biblioteca; los runs que ya no existen se omiten."""
    vigentes: dict[str, int] = {}
    for run_id in sorted({item.run_id for item in elementos}):
        try:
            vigentes[run_id] = repositorio.get_run(run_id).result_revision
        except KeyError:
            continue
    return vigentes


def crear_router_sugerencias(
    repositorio: RepositorioSugerencias,
    construir_descriptor: Callable[[Any], Descriptor] = build_descriptor,
) -> APIRouter:
    router = APIRouter(prefix=PREFIJO_API + "/sugerencias", tags=["precedentes"])

    @router.post("")
    def sugerir(peticion: PeticionSugerencias) -> JSONResponse:
        try:
            resultado = repositorio.get_result(peticion.run_id, peticion.result_revision)
        except KeyError:
            return JSONResponse(status_code=404, content=respuesta_error("resultado_no_encontrado", "Run o revisión inexistente."))
        try:
            descriptor = construir_descriptor(resultado)
        except ValueError as exc:
            return JSONResponse(status_code=409, content=respuesta_error("descriptor_no_disponible", str(exc)))
        elementos = repositorio.get_library_items()
        parametros = ParametrosSugerencia(**peticion.model_dump(exclude={"run_id", "result_revision"}))
        valor = sugerir_valores(
            descriptor,
            elementos,
            run_id=peticion.run_id,
            result_revision=peticion.result_revision,
            revisiones_vigentes=revisiones_vigentes(repositorio, elementos),
            parametros=parametros,
        )
        return JSONResponse(status_code=200, content=respuesta_ok(valor))

    return router
