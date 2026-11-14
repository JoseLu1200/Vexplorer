from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.contratos.modelos import (
    DescriptorDimensions,
    FurnitureDescriptor,
    FurnitureDescriptorV2,
    LibraryItem,
    RoleQuantity,
)
from backend.app.precedentes.api_sugerencias import crear_router_sugerencias
from backend.app.precedentes.comun import PREFIJO_API
from backend.app.precedentes.sugerencias import (
    SCORE_MINIMO_PROVISIONAL,
    ParametrosSugerencia,
    sugerir_valores,
)
from backend.app.semantic.descriptor import descriptor_fingerprint


def _v2(*, width=800.0, depth=300.0, height=1800.0, thicknesses=(18.0,), material="roble", finish="natural", structure="top_base_between_sides", unknown=()):
    return FurnitureDescriptorV2(
        family="rectangular_shelving",
        dimensions=DescriptorDimensions(width_mm=width, depth_mm=depth, height_mm=height),
        roles=(RoleQuantity(role="shelf", quantity=4), RoleQuantity(role="side_panel", quantity=2)),
        structure=structure,
        material=material,
        finish=finish,
        thicknesses_mm=tuple(thicknesses),
        classification_status="confirmed",
        unknown_fields=tuple(unknown),
    )


def _item(identificador: str, descriptor, revision: int = 1) -> LibraryItem:
    return LibraryItem(
        id=f"library-{identificador}",
        run_id=identificador,
        result_revision=revision,
        label=identificador,
        descriptor=descriptor,
        descriptor_fingerprint=descriptor_fingerprint(descriptor),
        created_at="2026-11-14T00:00:00+00:00",
    )


CONSULTA = _v2(thicknesses=(), material=None, finish="natural", unknown=("material", "thicknesses_mm"))

BIBLIOTECA = (
    _item("run-a", _v2(thicknesses=(18.0,), material="roble")),
    _item("run-b", _v2(width=820.0, thicknesses=(18.0,), material="roble")),
    _item("run-c", _v2(width=780.0, thicknesses=(18.0,), material="pino")),
    _item("run-d", _v2(width=900.0, thicknesses=(16.0,), material="pino")),
    _item("run-q", _v2(thicknesses=(25.0,), material="haya")),  # el propio run
    _item("run-viejo", _v2(thicknesses=(25.0,), material="haya")),  # revisión obsoleta
    _item("run-otra-estructura", _v2(structure="top_base_cap_sides", thicknesses=(25.0,), material="haya")),
    _item("run-v1", FurnitureDescriptor(family="rectangular_shelving", dimensions=DescriptorDimensions(width_mm=800.0), roles=(), structure="top_base_between_sides", material="haya", unknown_fields=())),
)

VIGENTES = {"run-a": 1, "run-b": 1, "run-c": 1, "run-d": 1, "run-q": 1, "run-viejo": 2, "run-otra-estructura": 1, "run-v1": 1}


def _sugerir(elementos=BIBLIOTECA, **parametros):
    return sugerir_valores(CONSULTA, elementos, run_id="run-q", result_revision=1, revisiones_vigentes=VIGENTES, parametros=ParametrosSugerencia(**parametros))


def test_sugiere_espesor_y_se_abstiene_en_material_empatado():
    resultado = _sugerir()
    assert [vecino.run_id for vecino in resultado.vecinos] == ["run-a", "run-b", "run-c", "run-d"]
    assert resultado.exclusiones.mismo_run == 1
    assert resultado.exclusiones.revision_obsoleta == 1
    assert resultado.exclusiones.estructura_distinta == 1
    assert resultado.exclusiones.otra_version == 1
    por_campo = {item.campo: item for item in resultado.sugerencias}
    assert set(por_campo) == {"thicknesses_mm", "material"}
    espesor = por_campo["thicknesses_mm"]
    assert espesor.estado == "hipotesis"
    assert espesor.valor == (18.0,)
    assert (espesor.soporte, espesor.total) == (3, 4)
    assert (espesor.rango_min, espesor.rango_max) == (16.0, 18.0)
    assert espesor.vecinos_a_favor_ids == ("library-run-a", "library-run-b", "library-run-c")
    material = por_campo["material"]
    assert material.estado == "abstencion"
    assert material.valor is None
    assert material.motivo.startswith("soporte_insuficiente")
    assert material.vecinos_ids == ("library-run-a", "library-run-b", "library-run-c", "library-run-d")


def test_es_determinista_ante_el_orden_de_entrada():
    assert _sugerir() == _sugerir(elementos=tuple(reversed(BIBLIOTECA)))


def test_abstencion_por_vecinos_insuficientes():
    resultado = _sugerir(vecinos_minimos=5)
    assert all(item.estado == "abstencion" and item.motivo.startswith("vecinos_insuficientes") for item in resultado.sugerencias)


ROLES = (RoleQuantity(role="shelf", quantity=4),)


def test_k_limita_vecinos_y_mediana_numerica():
    consulta = FurnitureDescriptor(family="rectangular_shelving", dimensions=DescriptorDimensions(width_mm=800.0, height_mm=1800.0), roles=ROLES, structure="unknown", material="roble", finish="natural", unknown_fields=("dimensions.depth_mm",))
    elementos = tuple(
        _item(f"run-{indice}", FurnitureDescriptor(family="rectangular_shelving", dimensions=DescriptorDimensions(width_mm=800.0, depth_mm=fondo, height_mm=1800.0), roles=ROLES, structure="top_base_between_sides", material="roble", finish="natural", unknown_fields=()))
        for indice, fondo in enumerate((300.0, 310.0, 320.0, 600.0))
    )
    resultado = sugerir_valores(consulta, elementos, run_id="run-x", result_revision=1, revisiones_vigentes={item.run_id: 1 for item in elementos}, parametros=ParametrosSugerencia(k=3, vecinos_minimos=3, soporte_minimo=0.6))
    assert len(resultado.vecinos) == 3
    assert resultado.exclusiones.fuera_de_k == 1
    (fondo,) = resultado.sugerencias
    assert fondo.campo == "dimensions.depth_mm"
    assert fondo.estado == "hipotesis"
    assert fondo.valor == 310.0
    assert (fondo.soporte, fondo.total) == (3, 3)


def test_parametros_por_defecto_exigen_score_minimo_provisional():
    assert ParametrosSugerencia().score_minimo == SCORE_MINIMO_PROVISIONAL > 0


def test_muebles_muy_distintos_no_producen_hipotesis():
    distintos = tuple(
        _item(f"run-dist-{indice}", _v2(width=ancho, depth=ancho / 4, height=ancho / 2, thicknesses=(18.0,), material="roble"))
        for indice, ancho in enumerate((150.0, 160.0, 170.0, 5000.0))
    )
    vigentes = {item.run_id: 1 for item in distintos}
    resultado = sugerir_valores(CONSULTA, distintos, run_id="run-q", result_revision=1, revisiones_vigentes=vigentes, parametros=ParametrosSugerencia())
    assert resultado.vecinos == ()
    assert resultado.exclusiones.score_insuficiente == 4
    assert all(item.estado == "abstencion" for item in resultado.sugerencias)


def test_consulta_sin_familia_abstencion_global():
    consulta = CONSULTA.model_copy(update={"family": "unknown"})
    resultado = sugerir_valores(consulta, BIBLIOTECA, run_id="run-q", result_revision=1, revisiones_vigentes=VIGENTES, parametros=ParametrosSugerencia())
    assert resultado.motivo_abstencion_global.startswith("familia_desconocida")
    assert resultado.vecinos == ()
    assert {item.campo for item in resultado.sugerencias} == {"thicknesses_mm", "material"}
    assert all(item.estado == "abstencion" for item in resultado.sugerencias)


def test_vecino_sin_familia_se_excluye():
    sin_familia = _item("run-sin-familia", _v2().model_copy(update={"family": "unknown"}))
    resultado = sugerir_valores(CONSULTA, (*BIBLIOTECA, sin_familia), run_id="run-q", result_revision=1, revisiones_vigentes=VIGENTES | {"run-sin-familia": 1}, parametros=ParametrosSugerencia())
    assert resultado.exclusiones.familia_distinta_o_desconocida == 1
    assert "run-sin-familia" not in {vecino.run_id for vecino in resultado.vecinos}


def test_material_se_normaliza_antes_de_contar():
    elementos = tuple(
        _item(f"run-m{indice}", _v2(thicknesses=(18.0,), material=material))
        for indice, material in enumerate(("Melamina", "melamina ", "MELAMINA", "pino"))
    )
    resultado = sugerir_valores(CONSULTA, elementos, run_id="run-q", result_revision=1, revisiones_vigentes={item.run_id: 1 for item in elementos}, parametros=ParametrosSugerencia())
    material = next(item for item in resultado.sugerencias if item.campo == "material")
    assert (material.estado, material.valor, material.soporte, material.total) == ("hipotesis", "melamina", 3, 4)


class RepositorioFalso:
    def __init__(self, elementos, vigentes):
        self.elementos = elementos
        self.vigentes = vigentes

    def get_result(self, run_id, revision=None):
        if run_id != "run-q" or revision != 1:
            raise KeyError(run_id)
        return "resultado-falso"

    def get_run(self, run_id):
        if run_id not in self.vigentes:
            raise KeyError(run_id)
        return SimpleNamespace(result_revision=self.vigentes[run_id])

    def get_library_items(self):
        return self.elementos


def _cliente():
    app = FastAPI()
    app.include_router(crear_router_sugerencias(RepositorioFalso(BIBLIOTECA, VIGENTES), construir_descriptor=lambda resultado: CONSULTA))
    return TestClient(app)


def test_endpoint_devuelve_sugerencias():
    respuesta = _cliente().post(PREFIJO_API + "/sugerencias", json={"run_id": "run-q", "result_revision": 1})
    assert respuesta.status_code == 200
    datos = respuesta.json()["data"]
    assert datos["descriptor_version"] == "furniture-v2"
    assert {item["campo"]: item["estado"] for item in datos["sugerencias"]} == {"thicknesses_mm": "hipotesis", "material": "abstencion"}
    assert datos["parametros"]["k"] == 8


def test_endpoint_resultado_inexistente():
    respuesta = _cliente().post(PREFIJO_API + "/sugerencias", json={"run_id": "run-z", "result_revision": 1})
    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "resultado_no_encontrado"


def test_endpoint_rechaza_campos_extra():
    respuesta = _cliente().post(PREFIJO_API + "/sugerencias", json={"run_id": "run-q", "result_revision": 1, "otro": 1})
    assert respuesta.status_code == 422
