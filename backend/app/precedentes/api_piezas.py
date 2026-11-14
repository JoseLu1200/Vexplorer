"""Router de piezas: 2.4 (piezas casi idénticas) y 3.1 (lotes de corte)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import Field, model_validator

from backend.app.precedentes.comun import (
    PREFIJO_API,
    ModeloEstricto,
    respuesta_error,
    respuesta_ok,
)
from backend.app.precedentes.gemelas import (
    TOLERANCIA_MAXIMA_MM,
    ConfiguracionGemelas,
    detectar_gemelas,
)
from backend.app.precedentes.lotes import ConfiguracionLotes, preparar_lotes
from backend.app.precedentes.nesting import ParametrosNesting
from backend.app.precedentes.piezas import (
    LIMITE_PIEZAS,
    FuenteBiblioteca,
    PiezaPedido,
    PiezaPeticion,
    PiezaRef,
    ids_duplicados,
    piezas_desde_biblioteca,
    piezas_desde_item_biblioteca,
)


class PeticionGemelas(ModeloEstricto):
    piezas: tuple[PiezaPeticion, ...] = Field(default=(), max_length=LIMITE_PIEZAS)
    incluir_biblioteca: bool = False
    tolerancia_largo_mm: float = Field(
        default=3.0, ge=0, le=TOLERANCIA_MAXIMA_MM, allow_inf_nan=False
    )
    tolerancia_ancho_mm: float = Field(
        default=3.0, ge=0, le=TOLERANCIA_MAXIMA_MM, allow_inf_nan=False
    )
    permitir_giro: bool = False


MAXIMO_PEDIDOS = 200


class PedidoEntrada(ModeloEstricto):
    pedido_id: str = Field(min_length=1, max_length=200)
    piezas: tuple[PiezaPedido, ...] = Field(default=(), max_length=LIMITE_PIEZAS)


class PeticionLotes(ParametrosNesting):
    """Hereda los parámetros del nesting (tablero, kerf, margen, giro) y su validación."""

    pedidos: tuple[PedidoEntrada, ...] = Field(default=(), max_length=MAXIMO_PEDIDOS)
    run_ids: tuple[str, ...] = Field(default=(), max_length=MAXIMO_PEDIDOS)

    @model_validator(mode="before")
    @classmethod
    def limitar_total_antes_de_validar(cls, datos: object) -> object:
        """Corta peticiones enormes antes de validar cada pieza."""
        if isinstance(datos, dict):
            pedidos = datos.get("pedidos")
            if isinstance(pedidos, list | tuple):
                total = sum(
                    len(p.get("piezas") or ())
                    for p in pedidos
                    if isinstance(p, dict) and isinstance(p.get("piezas"), list | tuple)
                )
                if total > LIMITE_PIEZAS:
                    raise ValueError(
                        f"Máximo {LIMITE_PIEZAS} piezas entre todos los pedidos."
                    )
        return datos

    incluir_biblioteca: bool = False
    aprovechamiento: float = Field(default=0.8, gt=0, le=1, allow_inf_nan=False)


def _error(estado: int, codigo: str, mensaje: str) -> JSONResponse:
    return JSONResponse(status_code=estado, content=respuesta_error(codigo, mensaje))


def crear_router_piezas(fuente_biblioteca: FuenteBiblioteca | None = None) -> APIRouter:
    """``fuente_biblioteca``: objeto con ``get_library_items()`` (p. ej. el repositorio)."""
    router = APIRouter(prefix=PREFIJO_API + "/piezas", tags=["precedentes"])

    @router.post("/gemelas")
    def gemelas(peticion: PeticionGemelas) -> object:
        piezas: list[PiezaRef] = [p.a_ref() for p in peticion.piezas]
        if peticion.incluir_biblioteca:
            if fuente_biblioteca is None:
                return _error(
                    503, "biblioteca_no_disponible", "No hay biblioteca configurada."
                )
            piezas.extend(
                piezas_desde_biblioteca(fuente_biblioteca.get_library_items())
            )
        if not piezas:
            return _error(422, "sin_piezas", "No hay piezas que analizar.")
        if len(piezas) > LIMITE_PIEZAS:
            return _error(422, "demasiadas_piezas", f"Máximo {LIMITE_PIEZAS} piezas.")
        duplicados = ids_duplicados(piezas)
        if duplicados:
            return _error(
                422, "pieza_duplicada", "Piezas duplicadas: " + ", ".join(duplicados)
            )
        configuracion = ConfiguracionGemelas(
            tolerancia_largo_mm=peticion.tolerancia_largo_mm,
            tolerancia_ancho_mm=peticion.tolerancia_ancho_mm,
            permitir_giro=peticion.permitir_giro,
        )
        return respuesta_ok(detectar_gemelas(piezas, configuracion))

    @router.post("/lotes")
    def lotes(peticion: PeticionLotes) -> object:
        if (
            not peticion.pedidos
            and not peticion.run_ids
            and not peticion.incluir_biblioteca
        ):
            return _error(
                422, "peticion_vacia", "Indica pedidos, run_ids o incluir_biblioteca."
            )
        ids_explicitos = [p.pedido_id for p in peticion.pedidos] + list(
            peticion.run_ids
        )
        repetidos = sorted({i for i in ids_explicitos if ids_explicitos.count(i) > 1})
        if repetidos:
            return _error(
                422, "pedido_duplicado", "Pedidos repetidos: " + ", ".join(repetidos)
            )

        piezas: list[PiezaRef] = [
            pieza.a_pieza_ref(pedido.pedido_id)
            for pedido in peticion.pedidos
            for pieza in pedido.piezas
        ]
        runs: set[str] = set()
        if peticion.run_ids or peticion.incluir_biblioteca:
            if fuente_biblioteca is None:
                return _error(
                    503, "biblioteca_no_disponible", "No hay biblioteca configurada."
                )
            por_run = {
                item.run_id: item for item in fuente_biblioteca.get_library_items()
            }
            faltan = [r for r in peticion.run_ids if r not in por_run]
            if faltan:
                return _error(
                    404,
                    "run_no_encontrado",
                    "No están en la biblioteca: " + ", ".join(faltan),
                )
            # Cada run de biblioteca es un pedido; la unión evita contarlo dos veces.
            runs = set(peticion.run_ids)
            if peticion.incluir_biblioteca:
                runs |= set(por_run)
            choques = sorted(runs & {p.pedido_id for p in peticion.pedidos})
            if choques:
                return _error(
                    422, "pedido_duplicado", "Pedidos repetidos: " + ", ".join(choques)
                )
            for run_id in sorted(runs):
                piezas.extend(piezas_desde_item_biblioteca(por_run[run_id]))
        todos_ids = [p.pedido_id for p in peticion.pedidos] + sorted(runs)
        if len(piezas) > LIMITE_PIEZAS:
            return _error(422, "demasiadas_piezas", f"Máximo {LIMITE_PIEZAS} piezas.")
        duplicados = ids_duplicados(piezas)
        if duplicados:
            return _error(
                422, "pieza_duplicada", "Piezas duplicadas: " + ", ".join(duplicados)
            )
        configuracion = ConfiguracionLotes(
            tablero_largo_mm=peticion.tablero_largo_mm,
            tablero_ancho_mm=peticion.tablero_ancho_mm,
            aprovechamiento=peticion.aprovechamiento,
            kerf_mm=peticion.kerf_mm,
            margen_mm=peticion.margen_mm,
            permitir_rotacion=peticion.permitir_rotacion,
        )
        return respuesta_ok(preparar_lotes(piezas, configuracion, pedidos=todos_ids))

    return router
