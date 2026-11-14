"""Router de la idea 2.2: presupuesto por analogía con alerta de desviación."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.app.historico.real_service import HistoricalStore
from backend.app.precedentes.analogia import (
    ConfiguracionAnalogia,
    ErrorAnalogia,
    SolicitudPresupuestoAnalogia,
    presupuestar_por_analogia,
)
from backend.app.precedentes.comun import PREFIJO_API, respuesta_error, respuesta_ok

_ESTADO_POR_CODIGO = {
    "semantic_provider_unavailable": 503,
    "embedding_space_incompatible": 409,
}


def crear_router_analogia(
    store: HistoricalStore,
    configuracion: ConfiguracionAnalogia | None = None,
) -> APIRouter:
    config = configuracion or ConfiguracionAnalogia()
    router = APIRouter(prefix=PREFIJO_API, tags=["precedentes"])

    @router.post("/presupuesto-analogia")
    def presupuesto_analogia(solicitud: SolicitudPresupuestoAnalogia):
        try:
            resultado = presupuestar_por_analogia(store, solicitud, config)
        except ErrorAnalogia as error:
            return JSONResponse(
                status_code=error.estado_http,
                content=respuesta_error(error.codigo, error.mensaje),
            )
        except ValueError as error:
            codigo = str(error)
            return JSONResponse(
                status_code=_ESTADO_POR_CODIGO.get(codigo, 422),
                content=respuesta_error(codigo),
            )
        return respuesta_ok(resultado)

    return router
