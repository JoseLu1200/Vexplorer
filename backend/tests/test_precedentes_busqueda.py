from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.agente.provider import ProviderError, ProviderResponse, ToolCall
from backend.app.contratos.modelos import (
    DescriptorDimensions,
    FurnitureDescriptor,
    FurnitureDescriptorV2,
    FurnitureDescriptorV3,
    LibraryItem,
    RoleQuantity,
    TableDescriptorComponentFeature,
)
from backend.app.precedentes.api_busqueda import crear_router_busqueda
from backend.app.precedentes.busqueda import (
    NOMBRE_HERRAMIENTA,
    FiltrosBusqueda,
    esquema_herramienta,
    filtrar_biblioteca,
)
from backend.app.precedentes.comun import PREFIJO_API
from backend.app.semantic.descriptor import descriptor_fingerprint

RUTA = PREFIJO_API + "/busqueda"


def _item(identificador, descriptor, revision=1):
    return LibraryItem(id=f"library-{identificador}", run_id=identificador, result_revision=revision, label=identificador, descriptor=descriptor, descriptor_fingerprint=descriptor_fingerprint(descriptor), created_at="2026-11-14T00:00:00+00:00")


def _estanteria(alto, baldas, *, espesores=(18.0,), material="Roble "):
    return FurnitureDescriptorV2(family="rectangular_shelving", dimensions=DescriptorDimensions(width_mm=800.0, depth_mm=300.0, height_mm=alto), roles=(RoleQuantity(role="shelf", quantity=baldas), RoleQuantity(role="side_panel", quantity=2)), structure="top_base_between_sides", material=material, finish=None, thicknesses_mm=espesores, classification_status="confirmed", unknown_fields=())


MESA = FurnitureDescriptorV3(
    dimensions=DescriptorDimensions(width_mm=1600.0, depth_mm=800.0, height_mm=750.0),
    structure="side_support_table",
    components=(TableDescriptorComponentFeature(role="tabletop", quantity=1, length_mm=1600.0, width_mm=800.0, thickness_mm=30.0, field_states={"quantity": "calculated", "length_mm": "calculated", "width_mm": "calculated", "thickness_mm": "calculated"}),),
)

BIBLIOTECA = (
    _item("run-alta", _estanteria(2200.0, 5)),
    _item("run-centrada", _estanteria(2100.0, 4)),
    _item("run-baja", _estanteria(1500.0, 4)),
    _item("run-pocas-baldas", _estanteria(2200.0, 2)),
    _item("run-v1", FurnitureDescriptor(family="rectangular_shelving", dimensions=DescriptorDimensions(width_mm=800.0, height_mm=2050.0), roles=(RoleQuantity(role="shelf", quantity=4),), structure="unknown", material="roble", unknown_fields=())),
    _item("run-mesa", MESA),
    _item("run-viejo", _estanteria(2200.0, 6), revision=1),
)
VIGENTES = {item.run_id: 1 for item in BIBLIOTECA} | {"run-viejo": 2}

FILTROS = {
    "familia": "rectangular_shelving",
    "alto": {"minimo_mm": 2000, "maximo_mm": 2200},
    "roles": [{"rol": "shelf", "cantidad_minima": 4}],
    "espesor": {"minimo_mm": 18, "maximo_mm": 18},
    "material": "  ROBLE",
    "terminos_no_interpretados": ["zócalo cerrado"],
}


class RepositorioFalso:
    def get_run(self, run_id):
        return SimpleNamespace(result_revision=VIGENTES[run_id])

    def get_library_items(self):
        return BIBLIOTECA


class ProveedorFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.llamadas.append({"input_items": input_items, "tools": tools, "timeout_s": timeout_s})
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


def _respuesta(argumentos, nombre=NOMBRE_HERRAMIENTA):
    return ProviderResponse(id="resp-1", tool_calls=(ToolCall(call_id="call-1", name=nombre, arguments_json=json.dumps(argumentos)),))


def _cliente(proveedor=None):
    app = FastAPI()
    app.include_router(crear_router_busqueda(RepositorioFalso(), proveedor, timeout_s=5.0))
    return TestClient(app)


def test_filtrado_determinista_marca_no_evaluables_y_ordena():
    filtros = FiltrosBusqueda.model_validate(FILTROS)
    assert filtros.material == "roble"
    resultados, obsoletos, descartados = filtrar_biblioteca(filtros, BIBLIOTECA, VIGENTES, limite=20)
    assert obsoletos == 1
    assert descartados == 3  # baja, pocas baldas, mesa (familia)
    assert [item.run_id for item in resultados] == ["run-centrada", "run-alta", "run-v1"]
    v1 = resultados[-1]
    espesor = next(item for item in v1.criterios if item.criterio == "espesor")
    assert (espesor.estado, espesor.motivo) == ("no_evaluable", "campo_inexistente")
    assert v1.criterios_no_evaluables == 1
    assert resultados[0].distancia == 0.0


def test_esquema_de_herramienta_estricto():
    esquema = esquema_herramienta()
    assert esquema["name"] == "aplicar_filtros_busqueda"
    assert esquema["strict"] is True
    parametros = esquema["parameters"]
    assert parametros["additionalProperties"] is False
    assert set(parametros["required"]) == set(FiltrosBusqueda.model_fields)
    assert "default" not in json.dumps(parametros)


def test_endpoint_con_filtros_no_llama_al_llm():
    proveedor = ProveedorFalso([])
    respuesta = _cliente(proveedor).post(RUTA, json={"consulta": "lo que sea", "filtros": FILTROS})
    assert respuesta.status_code == 200
    datos = respuesta.json()["data"]
    assert datos["usado_llm"] is False
    assert proveedor.llamadas == []
    assert datos["terminos_no_interpretados"] == ["zócalo cerrado"]
    assert datos["filtros_aplicados"]["terminos_no_interpretados"] == []
    assert [item["run_id"] for item in datos["resultados"]] == ["run-centrada", "run-alta", "run-v1"]


def test_endpoint_traduce_con_proveedor_simulado():
    argumentos = {"familia": "rectangular_shelving", "estructura": None, "ancho": None, "fondo": None, "alto": {"minimo_mm": 2000, "maximo_mm": None}, "roles": [{"rol": "shelf", "cantidad_minima": 4}], "espesor": None, "material": None, "acabado": None, "terminos_no_interpretados": ["zócalo cerrado"]}
    proveedor = ProveedorFalso([_respuesta(argumentos)])
    respuesta = _cliente(proveedor).post(RUTA, json={"consulta": "estanterías de más de 2 m con al menos 4 baldas y zócalo cerrado"})
    assert respuesta.status_code == 200
    datos = respuesta.json()["data"]
    assert datos["usado_llm"] is True
    assert datos["terminos_no_interpretados"] == ["zócalo cerrado"]
    assert [item["run_id"] for item in datos["resultados"]] == ["run-alta", "run-centrada", "run-v1"]
    assert len(proveedor.llamadas) == 1
    assert proveedor.llamadas[0]["tools"][0]["name"] == NOMBRE_HERRAMIENTA
    assert proveedor.llamadas[0]["timeout_s"] <= 5.0


def test_salida_invalida_reintenta_una_vez_y_falla():
    proveedor = ProveedorFalso([_respuesta({"familia": "sofa"}), _respuesta({}, nombre="otra_herramienta")])
    respuesta = _cliente(proveedor).post(RUTA, json={"consulta": "sofás"})
    assert respuesta.status_code == 502
    assert respuesta.json()["error"]["code"] == "traduccion_invalida"
    assert len(proveedor.llamadas) == 2
    assert "no era válida" in proveedor.llamadas[1]["input_items"][-1]["content"]


def test_salida_invalida_y_segundo_intento_valido():
    proveedor = ProveedorFalso([_respuesta({"familia": "sofa"}), _respuesta({"familia": "rectangular_table"})])
    respuesta = _cliente(proveedor).post(RUTA, json={"consulta": "mesas"})
    assert respuesta.status_code == 200
    assert [item["run_id"] for item in respuesta.json()["data"]["resultados"]] == ["run-mesa"]


def test_error_del_proveedor():
    proveedor = ProveedorFalso([ProviderError("provider_request_timeout")])
    respuesta = _cliente(proveedor).post(RUTA, json={"consulta": "mesas"})
    assert respuesta.status_code == 502
    assert respuesta.json()["error"]["code"] == "proveedor_fallo"


def test_sin_proveedor_y_solo_consulta():
    respuesta = _cliente(None).post(RUTA, json={"consulta": "mesas"})
    assert respuesta.status_code == 503
    assert respuesta.json()["error"]["code"] == "proveedor_no_disponible"


@pytest.mark.parametrize("cuerpo", [{}, {"consulta": "x" * 501}, {"filtros": {"alto": {}}}, {"filtros": {"alto": {"minimo_mm": 10, "maximo_mm": 5}}}])
def test_peticiones_invalidas(cuerpo):
    assert _cliente(None).post(RUTA, json=cuerpo).status_code == 422
