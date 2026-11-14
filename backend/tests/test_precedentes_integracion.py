"""Integración de ``backend/app/precedentes`` en la aplicación completa."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.estimacion.table_costs import get_table_cost_catalog
from backend.app.main import create_app

RUTAS_PRECEDENTES = [
    ("POST", "/api/v1/precedentes/sugerencias"),
    ("POST", "/api/v1/precedentes/presupuesto-analogia"),
    ("POST", "/api/v1/precedentes/similares-hibrido"),
    ("POST", "/api/v1/precedentes/embeddings/regenerar"),
    ("POST", "/api/v1/precedentes/embeddings/espacio/verificar"),
    ("GET", "/api/v1/precedentes/embeddings/espacio"),
    ("POST", "/api/v1/precedentes/embeddings/espacio/rotar"),
    ("GET", "/api/v1/precedentes/embeddings/espacio/historico"),
    ("POST", "/api/v1/precedentes/piezas/gemelas"),
    ("POST", "/api/v1/precedentes/piezas/lotes"),
    ("POST", "/api/v1/precedentes/busqueda"),
    ("POST", "/api/v1/precedentes/imagen/indexar"),
    ("POST", "/api/v1/precedentes/imagen/similares"),
    ("POST", "/api/v1/precedentes/decisiones"),
    ("GET", "/api/v1/precedentes/decisiones/resumen"),
    ("POST", "/api/v1/precedentes/herrajes/registros"),
    ("GET", "/api/v1/precedentes/herrajes/registros"),
    ("POST", "/api/v1/precedentes/herrajes/sugerencias"),
]


def test_rutas_de_precedentes_registradas_en_local(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path / "data", frontend_dir=tmp_path / "none"))
    for method, path in RUTAS_PRECEDENTES:
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
    with TestClient(create_app(data_dir=tmp_path / "data")) as client:
        for method, path in RUTAS_PRECEDENTES:
            response = client.request(method, path)
            assert response.status_code == 403, (path, response.text)
            assert response.json()["error"]["code"] == "private_feature_unavailable"
