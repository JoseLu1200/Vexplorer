"""Endpoints de la idea 3.3 (embeddings de imagen del plano). Ver ``imagen.py``."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import Field

from backend.app.precedentes.comun import (
    PREFIJO_API,
    ModeloEstricto,
    respuesta_error,
    respuesta_ok,
)
from backend.app.precedentes.imagen import (
    AlmacenImagen,
    ErrorImagen,
    ProveedorEmbeddingImagen,
    RepositorioRuns,
    VistasDeRun,
    buscar_similares,
    indexar_vistas,
    vistas_desde_repositorio,
)

_ESTADOS_ERROR = {
    "run_no_encontrado": 404,
    "run_no_indexado": 409,
    "dimension_incompatible": 409,
    "espacio_ambiguo": 422,
    "sin_vistas_renderizables": 422,
    "proveedor_imagen_no_disponible": 503,
    "proveedor_imagen_invalido": 500,
    "proveedor_imagen_fallo": 502,
    "vector_invalido": 502,
}


class PeticionIndexar(ModeloEstricto):
    run_id: str = Field(min_length=1, max_length=160)


class PeticionSimilares(ModeloEstricto):
    run_id: str = Field(min_length=1, max_length=160)
    limite: int = Field(default=5, ge=1, le=50)
    umbral_minimo: float = Field(ge=-1.0, le=1.0, allow_inf_nan=False)
    espacio_id: str | None = Field(default=None, min_length=1, max_length=200)


def _error(error: ErrorImagen) -> JSONResponse:
    return JSONResponse(
        status_code=_ESTADOS_ERROR.get(error.codigo, 500),
        content=respuesta_error(error.codigo, error.mensaje),
    )


def crear_router_imagen(
    repositorio: RepositorioRuns | None,
    ruta_almacen: Path,
    proveedor: ProveedorEmbeddingImagen | None = None,
    *,
    obtener_vistas: Callable[[str], VistasDeRun] | None = None,
) -> APIRouter:
    """Router de ``{PREFIJO_API}/imagen``.

    ``obtener_vistas`` sustituye al render desde el repositorio (por defecto se renderizan las
    vistas de la extracción del run con ``agente/vision.py``). Debe lanzar ``KeyError`` si el
    run no existe.
    """
    if obtener_vistas is None:
        if repositorio is None:
            raise ValueError("Se necesita repositorio u obtener_vistas.")

        def obtener_vistas(run_id: str) -> VistasDeRun:
            return vistas_desde_repositorio(repositorio, run_id)

    almacen = AlmacenImagen(ruta_almacen)
    router = APIRouter(prefix=PREFIJO_API + "/imagen", tags=["precedentes"])

    def _indexar(run_id: str, proveedor_activo: ProveedorEmbeddingImagen):
        try:
            vistas = obtener_vistas(run_id)
        except KeyError as error:
            raise ErrorImagen("run_no_encontrado", "El run no existe.") from error
        return indexar_vistas(almacen, proveedor_activo, vistas)

    @router.post("/indexar")
    def indexar(peticion: PeticionIndexar):
        if proveedor is None:
            return _error(
                ErrorImagen(
                    "proveedor_imagen_no_disponible",
                    "No hay proveedor de embeddings de imagen configurado.",
                )
            )
        try:
            return respuesta_ok(_indexar(peticion.run_id, proveedor))
        except ErrorImagen as error:
            return _error(error)

    @router.post("/similares")
    def similares(peticion: PeticionSimilares):
        try:
            espacio_id = peticion.espacio_id or (proveedor.espacio_id if proveedor else None)
            if espacio_id is None:
                espacios = almacen.espacios_de_run(peticion.run_id)
                if len(espacios) > 1:
                    raise ErrorImagen(
                        "espacio_ambiguo", "El run está indexado en varios espacios; indica espacio_id."
                    )
                if not espacios:
                    raise ErrorImagen(
                        "proveedor_imagen_no_disponible",
                        "El run no está indexado y no hay proveedor para embeberlo.",
                    )
                espacio_id = espacios[0]
            dimensiones_run = almacen.dimensiones_de_run(peticion.run_id, espacio_id)
            # Proveedor del mismo espacio pero con otra dimensión: se reembebe el run.
            proveedor_reconfigurado = (
                proveedor is not None
                and proveedor.espacio_id == espacio_id
                and dimensiones_run != (proveedor.dimensiones,)
            )
            if not dimensiones_run or proveedor_reconfigurado:
                if proveedor is None:
                    raise ErrorImagen(
                        "proveedor_imagen_no_disponible",
                        "El run no está indexado y no hay proveedor para embeberlo.",
                    )
                if proveedor.espacio_id != espacio_id:
                    raise ErrorImagen(
                        "run_no_indexado",
                        "El run no está indexado en ese espacio y el proveedor usa otro.",
                    )
                # Indexado bajo demanda: se persiste como si se hubiera llamado a /indexar.
                _indexar(peticion.run_id, proveedor)
            return respuesta_ok(
                buscar_similares(
                    almacen,
                    peticion.run_id,
                    espacio_id,
                    limite=peticion.limite,
                    umbral_minimo=peticion.umbral_minimo,
                )
            )
        except ErrorImagen as error:
            return _error(error)

    return router
