"""Router de la idea 3.5: herrajes y mecanizados por precedentes."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.app.historico.real_service import HistoricalStore
from backend.app.precedentes.comun import PREFIJO_API, respuesta_error, respuesta_ok
from backend.app.precedentes.herrajes import (
    AlmacenHerrajes,
    ImportacionHerrajes,
    SolicitudSugerenciasHerrajes,
    sugerir_herrajes,
)


def crear_router_herrajes(
    store: HistoricalStore, almacen: AlmacenHerrajes
) -> APIRouter:
    router = APIRouter(prefix=PREFIJO_API + "/herrajes", tags=["precedentes"])

    @router.post("/registros")
    def importar_registros(importacion: ImportacionHerrajes):
        return respuesta_ok(almacen.importar(importacion))

    @router.get("/registros")
    def listar_registros(
        limite: int = Query(default=100, ge=1, le=1000),
        desplazamiento: int = Query(default=0, ge=0),
    ):
        return respuesta_ok(almacen.listar(limite=limite, desplazamiento=desplazamiento))

    @router.post("/sugerencias")
    def sugerencias(solicitud: SolicitudSugerenciasHerrajes):
        try:
            resultado = sugerir_herrajes(store, almacen, solicitud)
        except ValueError as error:
            return JSONResponse(status_code=422, content=respuesta_error(str(error)))
        return respuesta_ok(resultado)

    return router
