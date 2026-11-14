"""Idea 3.2: búsqueda en lenguaje natural sobre la biblioteca de muebles.

Un LLM sólo traduce la consulta a ``FiltrosBusqueda`` mediante la herramienta
``aplicar_filtros_busqueda`` (esquema JSON estricto). El filtrado y el orden son deterministas.
Los conceptos que el descriptor no puede expresar se devuelven en
``terminos_no_interpretados``; nunca se descartan en silencio.

Un criterio sobre un campo que la versión del descriptor no tiene (o cuyo valor es desconocido)
no excluye el elemento: se marca como ``no_evaluable``.
"""

from __future__ import annotations

import json
import time
from typing import Annotated, Any, Literal, Protocol, get_args

from pydantic import (
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from backend.app.agente.provider import ProviderError, ProviderResponse
from backend.app.agente.tools import _schema
from backend.app.contratos.modelos import (
    AssemblyPartUse,
    LibraryItem,
    TableDescriptorComponentFeature,
)
from backend.app.precedentes import campos_descriptor as campos
from backend.app.precedentes.comun import ModeloEstricto, normalizar_texto

NOMBRE_HERRAMIENTA = "aplicar_filtros_busqueda"
MAX_CONSULTA = 500
MAX_TERMINOS = 10
MAX_LONGITUD_TERMINO = 100
MAX_ROLES = 10

# Vocabulario de roles del contrato (``Literal`` en ``contratos/modelos.py``), sin "unknown".
ROLES_CONOCIDOS: tuple[str, ...] = tuple(
    sorted(
        (set(get_args(AssemblyPartUse.model_fields["role"].annotation)) | set(get_args(TableDescriptorComponentFeature.model_fields["role"].annotation)))
        - {"unknown"}
    )
)

Termino = Annotated[str, StringConstraints(max_length=MAX_LONGITUD_TERMINO)]

Familia = Literal["rectangular_shelving", "rectangular_table"]
Estructura = Literal["top_base_between_sides", "top_base_cap_sides", "side_support_table", "corner_support_table"]


class RangoMm(ModeloEstricto):
    minimo_mm: float | None = Field(default=None, description="Límite inferior inclusivo en mm, o null.")
    maximo_mm: float | None = Field(default=None, description="Límite superior inclusivo en mm, o null.")

    @model_validator(mode="after")
    def rango_valido(self) -> RangoMm:
        if self.minimo_mm is None and self.maximo_mm is None:
            raise ValueError("el rango necesita al menos un límite")
        for valor in (self.minimo_mm, self.maximo_mm):
            if valor is not None and not 0 < valor < 100_000:
                raise ValueError("límite fuera de (0, 100000) mm")
        if self.minimo_mm is not None and self.maximo_mm is not None and self.minimo_mm > self.maximo_mm:
            raise ValueError("minimo_mm > maximo_mm")
        return self

    def contiene(self, valor: float) -> bool:
        return (self.minimo_mm is None or valor >= self.minimo_mm) and (self.maximo_mm is None or valor <= self.maximo_mm)

    def distancia_relativa(self, valor: float) -> float:
        """Distancia al centro del rango relativa al centro; 0 si el rango es abierto."""
        if self.minimo_mm is None or self.maximo_mm is None:
            return 0.0
        centro = (self.minimo_mm + self.maximo_mm) / 2
        return abs(valor - centro) / centro


class RolMinimo(ModeloEstricto):
    # El esquema de la herramienta restringe ``rol`` al vocabulario del contrato; la validación
    # acepta texto libre para que un rol desconocido se reubique como término no interpretado
    # (``reubicar_roles_desconocidos``) en lugar de rechazar toda la traducción.
    rol: str = Field(
        min_length=1,
        max_length=64,
        description="Rol de pieza del vocabulario del contrato.",
        json_schema_extra={"enum": list(ROLES_CONOCIDOS)},
    )
    cantidad_minima: int = Field(ge=1, le=1000, description="Cantidad mínima inclusiva de piezas con ese rol.")


class FiltrosBusqueda(ModeloEstricto):
    familia: Familia | None = Field(default=None, description="Familia de mueble, o null.")
    estructura: Estructura | None = Field(default=None, description="Estructura de montaje, o null.")
    ancho: RangoMm | None = Field(default=None, description="Rango de ancho total en mm, o null.")
    fondo: RangoMm | None = Field(default=None, description="Rango de fondo total en mm, o null.")
    alto: RangoMm | None = Field(default=None, description="Rango de alto total en mm, o null.")
    roles: tuple[RolMinimo, ...] = Field(default=(), max_length=MAX_ROLES, description="Roles con cantidad mínima.")
    espesor: RangoMm | None = Field(default=None, description="Espesor de tablero en mm; exacto con minimo_mm = maximo_mm.")
    material: str | None = Field(default=None, max_length=120, description="Material en texto, o null.")
    acabado: str | None = Field(default=None, max_length=120, description="Acabado en texto, o null.")
    terminos_no_interpretados: tuple[Termino, ...] = Field(
        default=(),
        max_length=MAX_TERMINOS,
        description="Conceptos de la consulta que ningún otro campo puede expresar (p. ej. 'zócalo cerrado').",
    )

    @field_validator("material", "acabado")
    @classmethod
    def normalizar(cls, valor: str | None) -> str | None:
        return normalizar_texto(valor)

    @field_validator("terminos_no_interpretados")
    @classmethod
    def terminos_limpios(cls, valor: tuple[str, ...]) -> tuple[str, ...]:
        limpios = tuple(" ".join(item.split()) for item in valor)
        return tuple(dict.fromkeys(item for item in limpios if item))

    @field_validator("roles")
    @classmethod
    def roles_unicos(cls, valor: tuple[RolMinimo, ...]) -> tuple[RolMinimo, ...]:
        if len({item.rol for item in valor}) != len(valor):
            raise ValueError("roles repetidos")
        return tuple(sorted(valor, key=lambda item: item.rol))


class PeticionBusqueda(ModeloEstricto):
    consulta: str | None = Field(default=None, min_length=1, max_length=MAX_CONSULTA)
    filtros: FiltrosBusqueda | None = None
    limite: int = Field(default=20, ge=1, le=200)

    @model_validator(mode="after")
    def alguna_entrada(self) -> PeticionBusqueda:
        if self.consulta is None and self.filtros is None:
            raise ValueError("indica consulta o filtros")
        return self


EstadoCriterio = Literal["cumple", "no_cumple", "no_evaluable"]


class EvaluacionCriterio(ModeloEstricto):
    criterio: str
    estado: EstadoCriterio
    motivo: Literal["campo_inexistente", "valor_desconocido"] | None = None


class ResultadoElemento(ModeloEstricto):
    library_item_id: str
    run_id: str
    result_revision: int
    label: str
    descriptor_version: str
    criterios_cumplidos: int
    criterios_no_evaluables: int
    distancia: float
    criterios: tuple[EvaluacionCriterio, ...]


class ResultadoBusqueda(ModeloEstricto):
    consulta: str | None
    usado_llm: bool
    filtros_aplicados: FiltrosBusqueda
    terminos_no_interpretados: tuple[str, ...]
    avisos: tuple[str, ...] = ()
    total_candidatos: int
    excluidos_revision_obsoleta: int
    excluidos_por_filtros: int
    resultados: tuple[ResultadoElemento, ...]


# ---------------------------------------------------------------------------
# Filtrado determinista
# ---------------------------------------------------------------------------


def reubicar_roles_desconocidos(
    filtros: FiltrosBusqueda,
    elementos_vigentes: tuple[LibraryItem, ...],
) -> tuple[FiltrosBusqueda, tuple[str, ...]]:
    """Mueve a ``terminos_no_interpretados`` los roles que no están en el vocabulario del contrato
    ni en ningún descriptor vigente, en vez de filtrar por ellos (lo que excluiría todo y perdería
    el concepto). Devuelve los filtros corregidos y los avisos. Función pura."""
    validos = set(ROLES_CONOCIDOS)
    for item in elementos_vigentes:
        validos.update(campos.roles(item.descriptor))
    desconocidos = [item for item in filtros.roles if item.rol not in validos]
    if not desconocidos:
        return filtros, ()
    avisos = [
        f"El rol '{item.rol}' no existe en el vocabulario ni en la biblioteca; se trata como término no interpretado."
        for item in desconocidos
    ]
    terminos = list(filtros.terminos_no_interpretados)
    for item in desconocidos:
        termino = " ".join(item.rol.replace("_", " ").split())[:MAX_LONGITUD_TERMINO]
        if termino not in terminos:
            terminos.append(termino)
    if len(terminos) > MAX_TERMINOS:
        avisos.append(f"Términos no interpretados por encima del máximo ({MAX_TERMINOS}): {'; '.join(terminos[MAX_TERMINOS:])}")
        terminos = terminos[:MAX_TERMINOS]
    datos = filtros.model_dump()
    datos["roles"] = [item.model_dump() for item in filtros.roles if item.rol in validos]
    datos["terminos_no_interpretados"] = terminos
    return FiltrosBusqueda.model_validate(datos), tuple(avisos)


def _criterio(nombre: str, existe: bool, valor: Any, cumple: Any) -> EvaluacionCriterio:
    if not existe:
        return EvaluacionCriterio(criterio=nombre, estado="no_evaluable", motivo="campo_inexistente")
    if valor is None:
        return EvaluacionCriterio(criterio=nombre, estado="no_evaluable", motivo="valor_desconocido")
    return EvaluacionCriterio(criterio=nombre, estado="cumple" if cumple(valor) else "no_cumple")


def evaluar_elemento(filtros: FiltrosBusqueda, item: LibraryItem) -> tuple[tuple[EvaluacionCriterio, ...], float]:
    """Evalúa cada criterio del filtro sobre un elemento. Devuelve criterios y distancia a los centros."""
    descriptor = item.descriptor
    evaluaciones: list[EvaluacionCriterio] = []
    distancia = 0.0
    if filtros.familia is not None:
        evaluaciones.append(_criterio("familia", True, campos.familia(descriptor), lambda v: v == filtros.familia))
    if filtros.estructura is not None:
        evaluaciones.append(_criterio("estructura", True, campos.estructura(descriptor), lambda v: v == filtros.estructura))
    for nombre, eje in (("ancho", "width_mm"), ("fondo", "depth_mm"), ("alto", "height_mm")):
        rango: RangoMm | None = getattr(filtros, nombre)
        if rango is None:
            continue
        valor = campos.dimension(descriptor, eje)
        evaluacion = _criterio(nombre, True, valor, rango.contiene)
        if evaluacion.estado == "cumple":
            distancia += rango.distancia_relativa(valor)
        evaluaciones.append(evaluacion)
    cantidades = campos.roles(descriptor)
    for requisito in filtros.roles:
        cantidad = cantidades.get(requisito.rol, 0)
        evaluaciones.append(_criterio(f"roles.{requisito.rol}", True, cantidad, lambda v, minimo=requisito.cantidad_minima: v >= minimo))
    if filtros.espesor is not None:
        rango_espesor = filtros.espesor
        evaluaciones.append(_criterio("espesor", campos.tiene_espesores(descriptor), campos.espesores(descriptor), lambda v: any(rango_espesor.contiene(e) for e in v)))
    for nombre, lector in (("material", campos.material), ("acabado", campos.acabado)):
        buscado = getattr(filtros, nombre)
        if buscado is None:
            continue
        evaluaciones.append(_criterio(nombre, campos.tiene_material_texto(descriptor), normalizar_texto(lector(descriptor)), lambda v, b=buscado: v == b))
    return tuple(evaluaciones), round(distancia, 6)


def filtrar_biblioteca(
    filtros: FiltrosBusqueda,
    elementos: tuple[LibraryItem, ...],
    revisiones_vigentes: dict[str, int],
    limite: int,
) -> tuple[tuple[ResultadoElemento, ...], int, int]:
    """Aplica los filtros. Devuelve (resultados ordenados, excluidos por revisión obsoleta, excluidos por filtros)."""
    obsoletos = 0
    descartados = 0
    resultados: list[ResultadoElemento] = []
    for item in elementos:
        if revisiones_vigentes.get(item.run_id) != item.result_revision:
            obsoletos += 1
            continue
        evaluaciones, distancia = evaluar_elemento(filtros, item)
        if any(item.estado == "no_cumple" for item in evaluaciones):
            descartados += 1
            continue
        resultados.append(ResultadoElemento(
            library_item_id=item.id,
            run_id=item.run_id,
            result_revision=item.result_revision,
            label=item.label,
            descriptor_version=item.descriptor.descriptor_version,
            criterios_cumplidos=sum(1 for e in evaluaciones if e.estado == "cumple"),
            criterios_no_evaluables=sum(1 for e in evaluaciones if e.estado == "no_evaluable"),
            distancia=distancia,
            criterios=evaluaciones,
        ))
    resultados.sort(key=lambda r: (-r.criterios_cumplidos, r.criterios_no_evaluables, r.distancia, r.library_item_id))
    return tuple(resultados[:limite]), obsoletos, descartados


# ---------------------------------------------------------------------------
# Traductor de lenguaje natural (LLM con herramienta de esquema estricto)
# ---------------------------------------------------------------------------

INSTRUCCIONES_TRADUCTOR = """Eres un traductor de consultas de búsqueda de muebles a filtros estructurados.
Debes llamar exactamente una vez a la herramienta aplicar_filtros_busqueda y no responder con texto.

Reglas:
- Todas las medidas en milímetros (1 m = 1000 mm, 1 cm = 10 mm). "más de 2 m" -> alto.minimo_mm = 2000.
- ancho = dimensión horizontal frontal, fondo = profundidad, alto = altura total.
- familia: "rectangular_shelving" (estanterías, librerías, armarios con baldas, muebles de TV
  o bajos de tipo caja) o "rectangular_table" (mesas). null si la consulta no lo indica.
- estructura: sólo si la consulta lo dice explícitamente; si no, null.
- roles: side_panel (lateral), shelf (balda/estante), top_panel (techo/tapa), base_panel (base/suelo),
  back_panel (trasera), door (puerta), divider (división), tabletop (tablero de mesa),
  side_support (pata lateral/costado de mesa), corner_support (pata de esquina).
  "al menos 4 baldas" -> {"rol": "shelf", "cantidad_minima": 4}.
- espesor exacto: minimo_mm = maximo_mm.
- material/acabado: copia el término tal cual (p. ej. "roble", "lacado blanco").
- roles: usa SOLO los valores del enum; si un elemento no es uno de esos roles, no lo pongas en roles.
- Todo concepto que no encaje en ningún campo (zócalo, simetría, tiradores, estilo, color si no es
  acabado, precio, herrajes...) va LITERALMENTE en terminos_no_interpretados. Nunca lo omitas ni lo
  conviertas en otro filtro.
- No inventes filtros que la consulta no pide: usa null o lista vacía.
"""


class ProveedorTraduccion(Protocol):
    def create_response(self, *, input_items: list[dict[str, Any]], tools: list[dict[str, Any]], previous_response_id: str | None, timeout_s: float) -> ProviderResponse: ...


class ErrorTraduccion(Exception):
    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo
        self.mensaje = mensaje


def esquema_herramienta() -> dict[str, Any]:
    return _schema(
        NOMBRE_HERRAMIENTA,
        "Aplica a la biblioteca de muebles los filtros estructurados que expresa la consulta del usuario. "
        "Los conceptos no expresables van en terminos_no_interpretados.",
        FiltrosBusqueda,
    )


def _extraer_filtros(respuesta: ProviderResponse) -> FiltrosBusqueda:
    llamadas = [llamada for llamada in respuesta.tool_calls if llamada.name == NOMBRE_HERRAMIENTA]
    if len(llamadas) != 1:
        raise ValueError(f"se esperaba una llamada a {NOMBRE_HERRAMIENTA}, hubo {len(llamadas)}")
    llamada = llamadas[0]
    argumentos = json.loads(llamada.arguments_json) if llamada.arguments_json is not None else llamada.arguments
    if not isinstance(argumentos, dict):
        raise TypeError("argumentos no son un objeto JSON")
    return FiltrosBusqueda.model_validate(argumentos)


def traducir_consulta(
    consulta: str,
    proveedor: ProveedorTraduccion,
    *,
    timeout_s: float = 20.0,
    max_intentos: int = 2,
) -> FiltrosBusqueda:
    """Traduce la consulta con como mucho ``max_intentos`` llamadas y un presupuesto total ``timeout_s``."""
    herramientas = [esquema_herramienta()]
    entrada: list[dict[str, Any]] = [{"role": "user", "content": consulta}]
    limite = time.monotonic() + timeout_s
    ultimo_error = "sin respuesta"
    for _ in range(max(1, max_intentos)):
        restante = limite - time.monotonic()
        if restante <= 0.5:
            break
        try:
            respuesta = proveedor.create_response(input_items=entrada, tools=herramientas, previous_response_id=None, timeout_s=restante)
        except ProviderError as exc:
            raise ErrorTraduccion("proveedor_fallo", exc.code) from None
        try:
            return _extraer_filtros(respuesta)
        except (TypeError, ValueError, ValidationError) as exc:
            ultimo_error = str(exc).splitlines()[0][:300]
            entrada = entrada[:1] + [{
                "role": "user",
                "content": f"La llamada anterior no era válida ({ultimo_error}). Llama una sola vez a {NOMBRE_HERRAMIENTA} con argumentos válidos.",
            }]
    raise ErrorTraduccion("traduccion_invalida", ultimo_error)
