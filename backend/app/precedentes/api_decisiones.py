"""Endpoints de decisiones de revisión (idea 3.4). El orquestador registra el router en main.py."""

from __future__ import annotations

import json

import anyio.from_thread
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.app.precedentes.comun import PREFIJO_API, respuesta_error, respuesta_ok
from backend.app.precedentes.decisiones import (
    AlmacenDecisiones,
    DecisionEntrada,
    resumir,
)

MAX_BYTES_CUERPO = 64 * 1024


async def _leer_cuerpo_limitado(request: Request, limite: int) -> bytes | None:
    """Lee el cuerpo sin superar ``limite`` bytes; ``None`` si lo supera."""
    declarado = request.headers.get("content-length")
    if declarado is not None and declarado.isdigit() and int(declarado) > limite:
        return None
    partes: list[bytes] = []
    total = 0
    async for trozo in request.stream():
        total += len(trozo)
        if total > limite:
            return None
        partes.append(trozo)
    return b"".join(partes)


def crear_router_decisiones(almacen: AlmacenDecisiones, minimo_decisiones: int = 30) -> APIRouter:
    router = APIRouter(prefix=PREFIJO_API + "/decisiones")

    @router.post("")
    def registrar_decision(request: Request) -> JSONResponse:
        crudo = anyio.from_thread.run(_leer_cuerpo_limitado, request, MAX_BYTES_CUERPO)
        if crudo is None:
            return JSONResponse(status_code=413, content=respuesta_error("cuerpo_demasiado_grande", f"El cuerpo supera {MAX_BYTES_CUERPO} bytes."))
        try:
            cuerpo = json.loads(crudo)
        except (ValueError, UnicodeDecodeError):
            return JSONResponse(status_code=422, content=respuesta_error("decision_invalida", "El cuerpo no es JSON válido."))
        if not isinstance(cuerpo, dict):
            return JSONResponse(status_code=422, content=respuesta_error("decision_invalida", "Se esperaba un objeto JSON."))
        # El actor sale SIEMPRE de la autenticación (None sin ella); el del cuerpo se ignora.
        cuerpo = {**cuerpo, "actor": getattr(request.state, "actor", None)}
        try:
            entrada = DecisionEntrada.model_validate(cuerpo)
        except ValidationError as error:
            campos = sorted({".".join(str(parte) for parte in item["loc"]) for item in error.errors()})
            return JSONResponse(status_code=422, content=respuesta_error("decision_invalida", f"Campos inválidos: {', '.join(campos)}"))
        resultado = almacen.registrar(entrada)
        return JSONResponse(status_code=201 if resultado.estado == "creada" else 200, content=respuesta_ok(resultado))

    @router.get("/resumen")
    def resumen(metodo: str | None = Query(default=None), minimo: str | None = Query(default=None)) -> JSONResponse:
        if not metodo:
            return JSONResponse(status_code=422, content=respuesta_error("metodo_requerido", "Indica ?metodo=..."))
        umbral = minimo_decisiones
        if minimo is not None:
            if not minimo.isdigit() or int(minimo) < 1:
                return JSONResponse(status_code=422, content=respuesta_error("minimo_invalido", "minimo debe ser un entero >= 1."))
            umbral = int(minimo)
        return JSONResponse(status_code=200, content=respuesta_ok(resumir(almacen.listar(metodo), metodo, umbral)))

    return router
