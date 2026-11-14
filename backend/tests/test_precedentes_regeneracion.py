from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.precedentes import regeneracion
from backend.app.precedentes.api_embeddings import crear_router_embeddings
from backend.app.precedentes.comun import PREFIJO_API
from backend.app.precedentes.espacio import AlmacenEspacio
from backend.app.precedentes.regeneracion import HechosElemento, detectar_obsoletos
from backend.app.semantic.embeddings import EmbeddingResult

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"
URL = f"{PREFIJO_API}/embeddings/regenerar"
ROTAR = f"{PREFIJO_API}/embeddings/espacio/rotar"
REFERENCIA = f"{PREFIJO_API}/embeddings/espacio"
RELOJ = "2026-11-14T00:00:00+00:00"


class ProveedorFalso:
    model = "modelo-falso"
    dimensions = 4

    def __init__(self, deriva: float = 0.0) -> None:
        self.llamadas = 0
        self.deriva = deriva

    def embed(self, text: str) -> EmbeddingResult:
        self.llamadas += 1
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = [1.0 + digest[index] / 255 for index in range(4)]
        vector[0] += self.deriva
        return EmbeddingResult(vector=tuple(vector), model=self.model, dimensions=4)


def _entorno(tmp_path: Path, monkeypatch, proveedor=None) -> tuple[TestClient, TestClient]:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    principal = create_app(data_dir=tmp_path)
    app = FastAPI()
    app.include_router(crear_router_embeddings(principal.state.repository, proveedor, AlmacenEspacio(tmp_path / "precedentes_espacio.sqlite3"), ahora=lambda: RELOJ, intervalo_minimo_verificacion_s=0))
    return TestClient(principal), TestClient(app)


def _run_revisado(cliente: TestClient, etiqueta: str) -> str:
    with FIXTURE.open("rb") as stream:
        document_id = cliente.post("/api/v1/documents", files={"file": (f"{etiqueta}.dxf", stream, "application/dxf")}).json()["data"]["document_id"]
    creado = cliente.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"}).json()["data"]
    run_id = creado["run"]["id"]
    escenario = creado["result"]["scenarios"][0]["id"]
    assert cliente.post(f"/api/v1/runs/{run_id}/reviews", json={"base_result_revision": 1, "reviewer_name": "Técnica", "scenario_id": escenario, "confirmed_thickness_mm": 18, "material": "tablero", "finish": "melamina", "notes": "ok"}).status_code == 201
    return run_id


def _guardar(principal: TestClient, run_id: str, revision: int) -> None:
    assert principal.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": revision, "label": f"et-{run_id}", "embedding_mode": "offline"}).status_code == 201


def test_simular_lista_sin_proveedor_y_no_simular_exige_proveedor(tmp_path: Path, monkeypatch) -> None:
    principal, cliente = _entorno(tmp_path, monkeypatch)
    run_id = _run_revisado(principal, "a")
    _guardar(principal, run_id, 1)

    respuesta = cliente.post(URL, json={})
    assert respuesta.status_code == 200
    datos = respuesta.json()["data"]
    assert datos["simular"] is True and datos["total_obsoletos"] == 1
    [elemento] = datos["elementos"]
    assert elemento["estado"] == "pendiente"
    assert elemento["motivos"] == ["revision_obsoleta", "embedding_ausente"]
    assert elemento["revision_guardada"] == 1 and elemento["revision_vigente"] == 2
    # Simular no modifica nada.
    assert principal.app.state.repository.get_library_item(run_id).result_revision == 1

    sin_proveedor = cliente.post(URL, json={"simular": False})
    assert sin_proveedor.status_code == 503
    assert sin_proveedor.json()["error"]["code"] == "proveedor_no_disponible"


def test_regenera_reutiliza_cache_y_queda_al_dia(tmp_path: Path, monkeypatch) -> None:
    proveedor = ProveedorFalso()
    principal, cliente = _entorno(tmp_path, monkeypatch, proveedor)
    primero, segundo = _run_revisado(principal, "a"), _run_revisado(principal, "b")
    _guardar(principal, primero, 1)
    _guardar(principal, segundo, 2)

    datos = cliente.post(URL, json={"simular": False}).json()["data"]
    estados = {item["run_id"]: item["estado"] for item in datos["elementos"]}
    # Ambos producen el mismo texto: uno se genera y el otro sale del caché (orden por id).
    assert sorted(estados.values()) == ["de_cache", "regenerado"]
    assert proveedor.llamadas == 1
    repositorio = principal.app.state.repository
    for run_id in (primero, segundo):
        item = repositorio.get_library_item(run_id)
        assert item.result_revision == 2 and item.embedding is not None
        assert item.label == f"et-{run_id}" and item.created_at == RELOJ
        assert len(repositorio.get_embedding(item.embedding.cache_key, item.embedding.model, item.embedding.dimensions, item.embedding.descriptor_version)) == 4

    despues = cliente.post(URL, json={}).json()["data"]
    assert despues["total_obsoletos"] == 0 and despues["elementos"] == []


def test_embedding_corrupto_se_detecta_y_sobrescribe(tmp_path: Path, monkeypatch) -> None:
    proveedor = ProveedorFalso()
    principal, cliente = _entorno(tmp_path, monkeypatch, proveedor)
    run_id = _run_revisado(principal, "a")
    _guardar(principal, run_id, 2)
    cliente.post(URL, json={"simular": False})
    clave = principal.app.state.repository.get_library_item(run_id).embedding.cache_key
    with sqlite3.connect(tmp_path / "vexplorer.sqlite3") as db:
        db.execute("UPDATE embedding_cache SET vector_json='[0,0,0,0]' WHERE cache_key=?", (clave,))

    simulado = cliente.post(URL, json={}).json()["data"]
    assert simulado["elementos"][0]["motivos"] == ["embedding_corrupto"]
    regenerado = cliente.post(URL, json={"simular": False}).json()["data"]
    assert regenerado["elementos"][0]["estado"] == "regenerado"
    assert cliente.post(URL, json={}).json()["data"]["total_obsoletos"] == 0


def test_revision_sin_descriptor_se_omite_con_motivo(tmp_path: Path, monkeypatch) -> None:
    principal, cliente = _entorno(tmp_path, monkeypatch, ProveedorFalso())
    run_id = _run_revisado(principal, "a")
    _guardar(principal, run_id, 1)

    def _rechaza(_resultado):
        raise ValueError("table_revision_not_accepted")

    monkeypatch.setattr(regeneracion, "build_descriptor", _rechaza)
    [elemento] = cliente.post(URL, json={"simular": False}).json()["data"]["elementos"]
    assert elemento["estado"] == "omitido"
    assert elemento["motivo_omision"] == "table_revision_not_accepted"
    assert principal.app.state.repository.get_library_item(run_id).result_revision == 1


def test_limite_y_deteccion_pura(tmp_path: Path, monkeypatch) -> None:
    principal, cliente = _entorno(tmp_path, monkeypatch)
    ids = [_run_revisado(principal, nombre) for nombre in ("a", "b")]
    for run_id in ids:
        _guardar(principal, run_id, 2)
    datos = cliente.post(URL, json={"limite": 1}).json()["data"]
    assert datos["total_obsoletos"] == 2 and len(datos["elementos"]) == 1
    assert datos["elementos"][0]["library_item_id"] == min(f"library-{run_id}" for run_id in ids)

    elemento = principal.app.state.repository.get_library_item(ids[0])
    hechos = (
        HechosElemento(elemento=elemento, revision_vigente=2, run_existe=True, estado_vector="ok"),
        HechosElemento(elemento=elemento.model_copy(update={"id": "library-z"}), revision_vigente=None, run_existe=False, estado_vector="ok"),
    )
    [obsoleto] = detectar_obsoletos(hechos)
    assert obsoleto.library_item_id == "library-z" and obsoleto.motivos == ("revision_obsoleta",)


class ProveedorOtroModelo(ProveedorFalso):
    model = "otro-modelo"

    def embed(self, text: str) -> EmbeddingResult:
        resultado = super().embed(text)
        return EmbeddingResult(vector=resultado.vector, model=self.model, dimensions=4)


def _router(principal: TestClient, tmp_path: Path, proveedor) -> TestClient:
    app = FastAPI()
    app.include_router(crear_router_embeddings(principal.app.state.repository, proveedor, AlmacenEspacio(tmp_path / "precedentes_espacio.sqlite3"), ahora=lambda: RELOJ, intervalo_minimo_verificacion_s=0))
    return TestClient(app)


def test_embedding_de_otro_espacio_es_obsoleto(tmp_path: Path, monkeypatch) -> None:
    principal, cliente = _entorno(tmp_path, monkeypatch, ProveedorFalso())
    run_id = _run_revisado(principal, "a")
    _guardar(principal, run_id, 2)
    cliente.post(URL, json={"simular": False})
    assert cliente.post(URL, json={}).json()["data"]["total_obsoletos"] == 0

    otro = _router(principal, tmp_path, ProveedorOtroModelo())
    [elemento] = otro.post(URL, json={}).json()["data"]["elementos"]
    assert elemento["motivos"] == ["espacio_distinto"]
    # Sin proveedor no se puede juzgar el espacio: no se marca.
    assert _router(principal, tmp_path, None).post(URL, json={}).json()["data"]["total_obsoletos"] == 0

    [regenerado] = otro.post(URL, json={"simular": False}).json()["data"]["elementos"]
    assert regenerado["estado"] == "regenerado"
    assert principal.app.state.repository.get_library_item(run_id).embedding.model == "otro-modelo"
    assert otro.post(URL, json={}).json()["data"]["total_obsoletos"] == 0


def test_limite_maximo_de_regeneracion(tmp_path: Path, monkeypatch) -> None:
    _, cliente = _entorno(tmp_path, monkeypatch, ProveedorFalso())
    assert cliente.post(URL, json={"limite": 100}).status_code == 200
    assert cliente.post(URL, json={"limite": 101}).status_code == 422


def test_regeneraciones_concurrentes_dan_409(tmp_path: Path, monkeypatch) -> None:
    import threading

    dentro, soltar = threading.Event(), threading.Event()

    class ProveedorLento(ProveedorFalso):
        def embed(self, text: str) -> EmbeddingResult:
            dentro.set()
            soltar.wait(5)
            return super().embed(text)

    principal, cliente = _entorno(tmp_path, monkeypatch, ProveedorLento())
    _guardar(principal, _run_revisado(principal, "a"), 2)
    respuestas = []
    hilo = threading.Thread(target=lambda: respuestas.append(cliente.post(URL, json={"simular": False})))
    hilo.start()
    assert dentro.wait(5)
    segunda = cliente.post(URL, json={"simular": False})
    simulada = cliente.post(URL, json={})
    soltar.set()
    hilo.join(5)
    assert segunda.status_code == 409 and segunda.json()["error"]["code"] == "operacion_en_curso"
    assert simulada.status_code == 200
    assert respuestas[0].status_code == 200


def test_rotar_invalida_cache_y_habilita_regeneracion_normal(tmp_path: Path, monkeypatch) -> None:
    proveedor = ProveedorFalso()
    principal, cliente = _entorno(tmp_path, monkeypatch, proveedor)
    run_id = _run_revisado(principal, "a")
    _guardar(principal, run_id, 2)
    cliente.post(URL, json={"simular": False})
    repositorio = principal.app.state.repository
    item = repositorio.get_library_item(run_id)
    vector_anterior = repositorio.get_embedding(item.embedding.cache_key, item.embedding.model, item.embedding.dimensions, item.embedding.descriptor_version)
    assert cliente.post(f"{REFERENCIA}/verificar").status_code == 200
    derivado = _router(principal, tmp_path, ProveedorFalso(deriva=0.5))
    rotado = derivado.post(ROTAR)
    assert rotado.status_code == 200
    assert rotado.json()["data"]["embeddings_invalidados"] == 1
    with pytest.raises(KeyError):
        repositorio.get_embedding(item.embedding.cache_key, item.embedding.model, item.embedding.dimensions, item.embedding.descriptor_version)
    simulado = derivado.post(URL, json={}).json()["data"]
    assert simulado["total_obsoletos"] == 1
    assert simulado["elementos"][0]["motivos"] == ["embedding_ausente"]
    derivado.post(URL, json={"simular": False})
    vector_nuevo = repositorio.get_embedding(item.embedding.cache_key, item.embedding.model, item.embedding.dimensions, item.embedding.descriptor_version)
    assert vector_nuevo != vector_anterior


def test_fallo_al_invalidar_no_rota_referencia_ni_expone_detalle(tmp_path: Path, monkeypatch) -> None:
    principal, cliente = _entorno(tmp_path, monkeypatch, ProveedorFalso())
    assert cliente.post(f"{REFERENCIA}/verificar").status_code == 200
    referencia_original = cliente.get(REFERENCIA).json()["data"][0]["huella_id"]

    def falla_invalidacion(modelo: str, dimensiones: int) -> int:
        raise RuntimeError("ruta-secreta-de-la-base")

    monkeypatch.setattr(principal.app.state.repository, "invalidate_embeddings", falla_invalidacion, raising=False)
    fallido = _router(principal, tmp_path, ProveedorFalso()).post(ROTAR)
    assert fallido.status_code == 503
    assert fallido.json()["error"]["code"] == "invalidacion_embeddings_fallida"
    assert "ruta-secreta" not in fallido.text
    assert cliente.get(REFERENCIA).json()["data"][0]["huella_id"] == referencia_original


def test_rotacion_y_regeneracion_comparten_exclusion_mutua(tmp_path: Path, monkeypatch) -> None:
    import threading

    dentro, soltar = threading.Event(), threading.Event()

    class ProveedorLentoUnaVez(ProveedorFalso):
        def embed(self, text: str) -> EmbeddingResult:
            if not dentro.is_set():
                dentro.set()
                soltar.wait(5)
            return super().embed(text)

    proveedor = ProveedorLentoUnaVez()
    principal, cliente = _entorno(tmp_path, monkeypatch, proveedor)
    _guardar(principal, _run_revisado(principal, "a"), 2)
    respuestas = []
    hilo = threading.Thread(target=lambda: respuestas.append(cliente.post(URL, json={"simular": False})))
    hilo.start()
    assert dentro.wait(5)
    rotacion = cliente.post(ROTAR)
    soltar.set()
    hilo.join(5)
    assert rotacion.status_code == 409
    assert rotacion.json()["error"]["code"] == "operacion_en_curso"
    assert respuestas[0].status_code == 200
