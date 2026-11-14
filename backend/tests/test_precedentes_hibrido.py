from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.contratos.modelos import EmbeddingMetadata
from backend.app.main import create_app
from backend.app.precedentes.api_embeddings import crear_router_embeddings
from backend.app.precedentes.comun import PREFIJO_API
from backend.app.precedentes.espacio import AlmacenEspacio
from backend.app.precedentes.hibrido import (
    CandidatoHibrido,
    VectorEtiquetado,
    componente_semantico,
    normalizar_pesos,
)
from backend.app.semantic.embeddings import EmbeddingResult

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"
URL = f"{PREFIJO_API}/similares-hibrido"


class ProveedorFalso:
    model = "modelo-falso"
    dimensions = 4

    def embed(self, text: str) -> EmbeddingResult:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = tuple(1.0 + digest[index] / 255 for index in range(self.dimensions))
        return EmbeddingResult(vector=vector, model=self.model, dimensions=self.dimensions)


def _entorno(tmp_path: Path, monkeypatch, proveedor=None) -> tuple[TestClient, TestClient]:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    principal = create_app(data_dir=tmp_path, embedding_provider=proveedor)
    app = FastAPI()
    app.include_router(crear_router_embeddings(principal.state.repository, proveedor, AlmacenEspacio(tmp_path / "precedentes_espacio.sqlite3")))
    return TestClient(principal), TestClient(app)


def _run_revisado(cliente: TestClient, etiqueta: str, material: str = "tablero") -> str:
    with FIXTURE.open("rb") as stream:
        document_id = cliente.post("/api/v1/documents", files={"file": (f"{etiqueta}.dxf", stream, "application/dxf")}).json()["data"]["document_id"]
    creado = cliente.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"}).json()["data"]
    run_id = creado["run"]["id"]
    escenario = creado["result"]["scenarios"][0]["id"]
    respuesta = cliente.post(f"/api/v1/runs/{run_id}/reviews", json={"base_result_revision": 1, "reviewer_name": "Técnica", "scenario_id": escenario, "confirmed_thickness_mm": 18, "material": material, "finish": "melamina", "notes": "ok"})
    assert respuesta.status_code == 201
    return run_id


def test_score_hibrido_combina_componentes_visibles(tmp_path: Path, monkeypatch) -> None:
    principal, cliente = _entorno(tmp_path, monkeypatch, ProveedorFalso())
    consulta = _run_revisado(principal, "a", "tablero")
    otro = _run_revisado(principal, "b", "pino")
    for run_id in (consulta, otro):
        assert principal.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 2, "label": run_id, "embedding_mode": "openai"}).status_code == 201

    respuesta = cliente.post(URL, json={"run_id": consulta, "result_revision": 2, "limite": 5, "peso_geometrico": 3, "peso_semantico": 1})
    assert respuesta.status_code == 200
    datos = respuesta.json()["data"]
    assert datos["pesos_solicitados"] == {"geometrico": 0.75, "semantico": 0.25}
    assert datos["consulta_semantica_disponible"] is True
    [coincidencia] = datos["coincidencias"]
    assert coincidencia["run_id"] == otro
    assert coincidencia["score_kind"] == "hibrido"
    assert coincidencia["semantico_disponible"] is True
    assert coincidencia["semantico"] is not None and coincidencia["semantico"] < 1
    esperado = round(0.75 * coincidencia["geometrico"] + 0.25 * coincidencia["semantico"], 6)
    assert coincidencia["score"] == pytest.approx(esperado, abs=1e-6)
    assert any(item["field"] == "material" for item in coincidencia["diferencias"])
    assert "dimensions" in coincidencia["componentes_geometricos"]
    # Determinismo.
    assert cliente.post(URL, json={"run_id": consulta, "result_revision": 2, "peso_geometrico": 3, "peso_semantico": 1}).json() == respuesta.json()


def test_sin_embedding_el_score_es_geometrico_y_se_marca(tmp_path: Path, monkeypatch) -> None:
    principal, cliente = _entorno(tmp_path, monkeypatch)
    consulta = _run_revisado(principal, "a")
    otro = _run_revisado(principal, "b")
    for run_id in (consulta, otro):
        principal.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 2, "label": run_id, "embedding_mode": "offline"})

    datos = cliente.post(URL, json={"run_id": consulta, "result_revision": 2}).json()["data"]
    assert datos["consulta_semantica_disponible"] is False
    assert datos["motivo_consulta_sin_semantica"] == "consulta_sin_embedding"
    [coincidencia] = datos["coincidencias"]
    assert coincidencia["semantico"] is None
    assert coincidencia["semantico_disponible"] is False
    assert coincidencia["motivo_semantico_no_disponible"] == "consulta_sin_embedding"
    assert coincidencia["score"] == coincidencia["geometrico"]
    assert coincidencia["pesos_efectivos"] == {"geometrico": 1.0, "semantico": 0.0}


def test_pesos_invalidos_y_revision_inexistente(tmp_path: Path, monkeypatch) -> None:
    principal, cliente = _entorno(tmp_path, monkeypatch)
    run_id = _run_revisado(principal, "a")
    nulos = cliente.post(URL, json={"run_id": run_id, "result_revision": 2, "peso_geometrico": 0, "peso_semantico": 0})
    assert nulos.status_code == 422 and nulos.json()["error"]["code"] == "pesos_invalidos"
    assert cliente.post(URL, json={"run_id": run_id, "result_revision": 2, "peso_geometrico": -1}).status_code == 422
    ausente = cliente.post(URL, json={"run_id": run_id, "result_revision": 99})
    assert ausente.status_code == 404 and ausente.json()["error"]["code"] == "result_not_found"


def test_normalizar_pesos() -> None:
    assert normalizar_pesos(1, 1).model_dump() == {"geometrico": 0.5, "semantico": 0.5}
    assert normalizar_pesos(0, 2).model_dump() == {"geometrico": 0.0, "semantico": 1.0}
    for pesos in ((0, 0), (-1, 2), (float("nan"), 1), (float("inf"), 1)):
        with pytest.raises(ValueError, match="pesos_invalidos"):
            normalizar_pesos(*pesos)


def test_espacio_incompatible_no_se_oculta(tmp_path: Path, monkeypatch) -> None:
    principal, _ = _entorno(tmp_path, monkeypatch)
    run_id = _run_revisado(principal, "a")
    principal.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": 2, "label": "x", "embedding_mode": "offline"})
    elemento = principal.app.state.repository.get_library_item(run_id)
    meta_a = EmbeddingMetadata(model="m1", dimensions=2, descriptor_version="furniture-v1", cache_key="a", status="generated")
    meta_b = EmbeddingMetadata(model="m2", dimensions=2, descriptor_version="furniture-v1", cache_key="b", status="generated")
    consulta = VectorEtiquetado(metadatos=meta_a, vector=(1.0, 0.0))
    candidato = CandidatoHibrido(elemento=elemento, vector=VectorEtiquetado(metadatos=meta_b, vector=(1.0, 0.0)))
    assert componente_semantico(consulta, candidato) == (None, "embedding_space_incompatible")
    mismo = CandidatoHibrido(elemento=elemento, vector=VectorEtiquetado(metadatos=meta_a, vector=(0.0, 1.0)))
    assert componente_semantico(consulta, mismo) == (0.0, None)
