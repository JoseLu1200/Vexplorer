"""Integración de ``backend/app/precedentes`` en la aplicación completa."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.estimacion.table_costs import get_table_cost_catalog
from backend.app.main import create_app

PREFIJO_PRECEDENTES = "/api/v1/precedentes"


def _rutas_precedentes(app) -> list[tuple[str, str]]:
    """Todas las rutas (método, ruta) que la app publica bajo el prefijo de precedentes (según su OpenAPI)."""
    return sorted(
        (metodo.upper(), ruta)
        for ruta, operaciones in app.openapi()["paths"].items()
        if ruta == PREFIJO_PRECEDENTES or ruta.startswith(PREFIJO_PRECEDENTES + "/")
        for metodo in operaciones
        if metodo.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    )


def test_rutas_de_precedentes_registradas_en_local(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none")
    rutas = _rutas_precedentes(app)
    assert ("GET", "/api/v1/precedentes/embeddings/mantenimiento") in rutas
    assert len(rutas) >= 19
    client = TestClient(app)
    for method, path in rutas:
        response = client.request(method, path)
        assert response.status_code not in (404, 405), (method, path, response.status_code)


def test_busqueda_sin_proveedor_responde_503_sin_llamar_a_la_red(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none"))
    response = client.post("/api/v1/precedentes/busqueda", json={"consulta": "estanterías altas"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "proveedor_no_disponible"


def test_precedentes_bloqueados_en_acceso_publico(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_AUTH_ENABLED", "false")
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    app = create_app(data_dir=tmp_path / "data")
    with TestClient(app) as client:
        for method, path in _rutas_precedentes(app):
            response = client.request(method, path)
            assert response.status_code == 403, (path, response.text)
            assert response.json()["error"]["code"] == "private_feature_unavailable"


@pytest.mark.parametrize("prefijo_peticion", ["", "/vx", "/vx/vx"])
def test_bloqueo_publico_no_se_evade_con_root_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefijo_peticion: str) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_AUTH_ENABLED", "false")
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setenv("VEXPLORER_ROOT_PATH", "/vx")
    app = create_app(data_dir=tmp_path / "data")
    privadas = _rutas_precedentes(app) + [
        ("GET", "/api/v1/history"),
        ("GET", "/api/v1/history/records"),
        ("GET", "/api/v1/library"),
        ("POST", "/api/v1/library/groups"),
        ("POST", "/api/v1/semantic-explorer/review"),
        ("POST", "/api/v1/runs/run-abc/library"),
        ("POST", "/api/v1/runs/run-abc/similarity"),
    ]
    with TestClient(app) as client:
        for method, path in privadas:
            response = client.request(method, prefijo_peticion + path)
            assert response.status_code == 403, (method, prefijo_peticion + path, response.status_code)
            assert response.json()["error"]["code"] == "private_feature_unavailable"
        # Las rutas públicas legítimas con prefijo siguen funcionando.
        assert client.get("/vx/api/v1/health").status_code == 200
        assert client.get("/api/v1/health").status_code == 200


def test_routers_de_precedentes_bloquean_por_si_mismos_en_acceso_publico(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Defensa en profundidad: aunque el middleware no reconozca la ruta, la dependencia del router responde 403."""
    from backend.app import main as main_module

    catalog = tmp_path / "catalog.json"
    catalog.write_text(get_table_cost_catalog().model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("VEXPLORER_COST_CATALOG", str(catalog))
    monkeypatch.setenv("VEXPLORER_ENV", "production")
    monkeypatch.setenv("VEXPLORER_AUTH_ENABLED", "false")
    monkeypatch.setenv("VEXPLORER_ALLOWED_ORIGINS", "https://vexplorer.example")
    monkeypatch.setattr(main_module, "_es_ruta_compartida", lambda path: False)
    app = create_app(data_dir=tmp_path / "data")
    with TestClient(app) as client:
        for method, path in _rutas_precedentes(app):
            response = client.request(method, path)
            assert response.status_code == 403, (method, path, response.status_code)


def test_lifespan_apaga_la_cola_aunque_falle_el_apagado_del_ejecutor(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none")
    apagada: list[bool] = []

    def falla() -> None:
        raise RuntimeError("fallo al apagar el ejecutor")

    app.state.job_executor.shutdown = falla
    app.state.cola_mantenimiento.apagar = lambda: apagada.append(True)
    with pytest.raises(RuntimeError, match="fallo al apagar"):
        with TestClient(app):
            pass
    assert apagada == [True]
