"""Tests de la idea 2.2. Solo datos sintéticos, marcados como tales; sin red."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.historico.models import HistoricalImport, HistoricalTarget
from backend.app.historico.real_service import HistoricalStore
from backend.app.precedentes.analogia import (
    ConfiguracionAnalogia,
    calcular_estadisticos,
    clasificar_desviacion,
)
from backend.app.precedentes.api_analogia import crear_router_analogia
from backend.app.precedentes.comun import PREFIJO_API

RUTA = PREFIJO_API + "/presupuesto-analogia"


def _registro_sintetico(
    record_id: str, coste: float, *, moneda: str = "EUR", cost_basis: str = "actual"
) -> dict:
    return {
        "record_id": record_id,
        "project_id": f"proyecto-{record_id}",
        "revision": "r1",
        "family": "armario",
        "width_mm": 800,
        "depth_mm": 400,
        "height_mm": 1800,
        "quantity": 1,
        "material": "melamina blanca",
        "finish": "mate",
        "currency": moneda,
        "actual_cost": coste,
        "cost_basis": cost_basis,
        "origin": "synthetic",
        "provenance": {"source": "demo fixture sintético", "source_date": "2026-10-01"},
        "included_scope": ["total"],
        "cost_scope": ["total"],
    }


def _objetivo(**cambios) -> dict:
    base = {
        "family": "armario",
        "width_mm": 800,
        "depth_mm": 400,
        "height_mm": 1800,
        "quantity": 1,
        "material": "melamina blanca",
        "finish": "mate",
        "currency": "EUR",
        "basis_revision": "objetivo-r1",
        "required_cost_scope": ["total"],
    }
    base.update(cambios)
    return base


def _cliente(tmp_path, registros: list[dict], **kwargs) -> TestClient:
    store = HistoricalStore(tmp_path / "historico.sqlite3")
    if registros:
        store.import_records(HistoricalImport.model_validate({"records": registros}))
    app = FastAPI()
    app.include_router(crear_router_analogia(store, **kwargs))
    return TestClient(app)


def _pedir(cliente: TestClient, coste: float, **extra):
    cuerpo = {
        "objetivo": extra.pop("objetivo", _objetivo()),
        "coste_calculado": coste,
        "incluir_sinteticos": True,
        **extra,
    }
    return cliente.post(RUTA, json=cuerpo)


def _tres(tmp_path) -> TestClient:
    return _cliente(
        tmp_path,
        [
            _registro_sintetico("s-1", 100),
            _registro_sintetico("s-2", 110),
            _registro_sintetico("s-3", 120),
        ],
    )


def test_dentro_de_rango_con_estadisticos_y_aviso_sintetico(tmp_path) -> None:
    respuesta = _pedir(_tres(tmp_path), 112)
    assert respuesta.status_code == 200
    datos = respuesta.json()["data"]
    assert datos["estado"] == "con_precedentes"
    assert datos["naturaleza"] == "hipotesis"
    assert [c["record_id"] for c in datos["comparables"]] == ["s-1", "s-2", "s-3"]
    assert {c["origen"] for c in datos["comparables"]} == {"synthetic"}
    assert datos["comparables"][0]["fuente"] == "demo fixture sintético"
    est = datos["estadisticos"]
    assert (est["mediana"], est["minimo"], est["maximo"], est["mad"]) == (110, 100, 120, 10)
    assert est["dispersion"] == 14.826
    assert datos["alerta"]["nivel"] == "dentro_de_rango"
    assert datos["alerta"]["desviacion_relativa"] == round(2 / 110, 4)
    assert datos["origenes"] == {"synthetic": 3}
    assert any("Todos los comparables son sintéticos" in a for a in datos["avisos"])
    assert "MAD" in datos["formula"] and "1.4826" in datos["formula"]


def test_niveles_aviso_y_alerta_por_multiplos_de_dispersion(tmp_path) -> None:
    cliente = _tres(tmp_path)
    aviso = _pedir(cliente, 147).json()["data"]["alerta"]
    assert aviso["nivel"] == "aviso"
    assert 2 < aviso["multiplos_de_dispersion"] <= 3
    alerta = _pedir(cliente, 200).json()["data"]["alerta"]
    assert alerta["nivel"] == "alerta"
    assert alerta["desviacion_relativa"] == round(90 / 110, 4)
    baja = _pedir(cliente, 60).json()["data"]["alerta"]
    assert baja["nivel"] == "alerta" and baja["desviacion_absoluta"] == -50


def test_suelo_relativo_cuando_la_dispersion_es_nula(tmp_path) -> None:
    cliente = _cliente(
        tmp_path,
        [_registro_sintetico(f"s-{i}", 100) for i in range(3)],
    )
    datos = _pedir(cliente, 108).json()["data"]
    assert datos["estadisticos"]["mad"] == 0
    assert datos["estadisticos"]["dispersion"] == 5
    assert datos["alerta"]["nivel"] == "dentro_de_rango"
    assert _pedir(cliente, 112).json()["data"]["alerta"]["nivel"] == "aviso"
    assert _pedir(cliente, 120).json()["data"]["alerta"]["nivel"] == "alerta"


def test_configuracion_inyectada_cambia_umbrales(tmp_path) -> None:
    config = ConfiguracionAnalogia(multiplo_aviso=0.5, multiplo_alerta=1.0)
    cliente = _cliente(
        tmp_path,
        [_registro_sintetico("s-1", 100), _registro_sintetico("s-2", 120)],
        configuracion=config,
    )
    datos = _pedir(cliente, 125).json()["data"]
    assert datos["alerta"]["nivel"] == "alerta"
    assert datos["configuracion"]["multiplo_aviso"] == 0.5


def test_moneda_incompatible_se_excluye_y_se_explica(tmp_path) -> None:
    cliente = _cliente(
        tmp_path,
        [
            _registro_sintetico("s-1", 100),
            _registro_sintetico("s-2", 110),
            _registro_sintetico("s-usd", 500, moneda="USD"),
        ],
    )
    datos = _pedir(cliente, 105).json()["data"]
    assert [c["record_id"] for c in datos["comparables"]] == ["s-1", "s-2"]
    assert datos["excluidos"] == [
        {"record_id": "s-usd", "origen": "synthetic", "motivos": ["moneda_incompatible"]}
    ]
    assert any("moneda distinta de EUR" in a for a in datos["avisos"])
    assert datos["estadisticos"]["maximo"] == 110


def test_sin_precedentes_suficientes_no_emite_alerta(tmp_path) -> None:
    cliente = _cliente(tmp_path, [_registro_sintetico("s-1", 100)])
    datos = _pedir(cliente, 1000).json()["data"]
    assert datos["estado"] == "sin_precedentes_suficientes"
    assert datos["alerta"] is None and datos["estadisticos"] is None
    assert len(datos["comparables"]) == 1


def test_sinteticos_excluidos_por_defecto(tmp_path) -> None:
    cliente = _tres(tmp_path)
    datos = _pedir(cliente, 110, incluir_sinteticos=False).json()["data"]
    assert datos["comparables_recuperados"] == 0
    assert datos["estado"] == "sin_precedentes_suficientes"


def test_presupuesto_quote_genera_aviso(tmp_path) -> None:
    cliente = _cliente(
        tmp_path,
        [
            _registro_sintetico("s-1", 100, cost_basis="quote"),
            _registro_sintetico("s-2", 110),
        ],
    )
    avisos = _pedir(cliente, 105).json()["data"]["avisos"]
    assert any("presupuesto u oferta" in a for a in avisos)


def test_errores_de_peticion(tmp_path) -> None:
    cliente = _tres(tmp_path)
    sin_moneda = _pedir(cliente, 100, objetivo=_objetivo(currency=None))
    assert sin_moneda.status_code == 422
    assert sin_moneda.json()["error"]["code"] == "moneda_requerida"
    conflicto = _pedir(cliente, 100, moneda="USD")
    assert conflicto.json()["error"]["code"] == "moneda_en_conflicto"
    sin_alcance = _pedir(cliente, 100, objetivo=_objetivo(required_cost_scope=[]))
    assert sin_alcance.json()["error"]["code"] == "alcance_coste_requerido"
    semantico = _pedir(cliente, 100, metodo_recuperacion="semantic")
    assert semantico.status_code == 503
    assert semantico.json()["error"]["code"] == "semantic_provider_unavailable"
    assert _pedir(cliente, 0).status_code == 422


def test_moneda_de_la_peticion_completa_el_objetivo(tmp_path) -> None:
    cliente = _tres(tmp_path)
    datos = _pedir(cliente, 110, objetivo=_objetivo(currency=None), moneda="EUR").json()
    assert datos["data"]["moneda"] == "EUR"
    assert datos["data"]["estado"] == "con_precedentes"


def test_funciones_puras_deterministas() -> None:
    config = ConfiguracionAnalogia()
    a = calcular_estadisticos((120.0, 100.0, 110.0, 130.0), config)
    b = calcular_estadisticos((130.0, 110.0, 100.0, 120.0), config)
    assert a == b
    assert a.mediana == 115
    assert clasificar_desviacion(115, a, config).nivel == "dentro_de_rango"
    cero = calcular_estadisticos((0.0, 0.0), config)
    alerta = clasificar_desviacion(10, cero, config)
    assert alerta.desviacion_relativa is None and alerta.nivel == "alerta"
    HistoricalTarget.model_validate(_objetivo())
