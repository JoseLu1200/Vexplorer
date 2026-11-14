from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.precedentes.api_embeddings import crear_router_embeddings
from backend.app.precedentes.comun import PREFIJO_API
from backend.app.precedentes.espacio import (
    FRASES_CONTROL,
    VERSION_FRASES_CONTROL,
    AlmacenEspacio,
    calcular_huella,
    comparar_huellas,
)
from backend.app.semantic.embeddings import EmbeddingResult

VERIFICAR = f"{PREFIJO_API}/embeddings/espacio/verificar"
REFERENCIA = f"{PREFIJO_API}/embeddings/espacio"


class ProveedorFalso:
    model = "modelo-falso"
    dimensions = 4

    def __init__(self, deriva: float = 0.0) -> None:
        self.deriva = deriva

    def embed(self, text: str) -> EmbeddingResult:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = [1.0 + digest[index] / 255 for index in range(4)]
        vector[0] += self.deriva
        return EmbeddingResult(vector=tuple(vector), model=self.model, dimensions=4)


class RepositorioVacio:
    def get_library_items(self):
        return ()


def _cliente(tmp_path: Path, proveedor) -> TestClient:
    app = FastAPI()
    app.include_router(crear_router_embeddings(RepositorioVacio(), proveedor, AlmacenEspacio(tmp_path / "precedentes_espacio.sqlite3"), ahora=lambda: "2026-11-14T00:00:00+00:00"))
    return TestClient(app)


def test_frases_control_fijas_y_versionadas() -> None:
    assert VERSION_FRASES_CONTROL == "control-v1"
    assert len(FRASES_CONTROL) >= 5 and len(set(FRASES_CONTROL)) == len(FRASES_CONTROL)
    assert all(frase.startswith("descriptor=furniture-v1; family=") for frase in FRASES_CONTROL)


def test_verificar_crea_referencia_luego_estable_y_detecta_deriva(tmp_path: Path) -> None:
    creada = _cliente(tmp_path, ProveedorFalso()).post(VERIFICAR, json={})
    assert creada.status_code == 200
    assert creada.json()["data"]["estado"] == "referencia_creada"

    estable = _cliente(tmp_path, ProveedorFalso()).post(VERIFICAR, json={}).json()["data"]
    assert estable["estado"] == "estable"
    assert estable["coseno_minimo"] == pytest.approx(1.0)
    assert len(estable["detalle"]) == len(FRASES_CONTROL)
    assert estable["huella_actual"] == estable["huella_referencia"]

    deriva = _cliente(tmp_path, ProveedorFalso(deriva=0.5)).post(VERIFICAR, json={"tolerancia": 0.999}).json()["data"]
    assert deriva["estado"] == "deriva_detectada"
    assert deriva["coseno_minimo"] < 0.999
    assert any(not item["estable"] for item in deriva["detalle"])
    assert deriva["huella_actual"] != deriva["huella_referencia"]

    # La referencia no se sobrescribe con la deriva.
    listado = _cliente(tmp_path, None).get(REFERENCIA).json()["data"]
    assert len(listado) == 1
    assert listado[0]["huella_id"] == estable["huella_referencia"]
    assert listado[0]["num_frases"] == len(FRASES_CONTROL) and listado[0]["vectores"] is None


def test_sin_proveedor_verificar_devuelve_503_y_get_funciona(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path, None)
    respuesta = cliente.post(VERIFICAR, json={})
    assert respuesta.status_code == 503 and respuesta.json()["error"]["code"] == "proveedor_no_disponible"
    assert cliente.get(REFERENCIA).json()["data"] == []
    assert cliente.get(REFERENCIA, params={"modelo": "otro"}).status_code == 404


def test_get_filtra_e_incluye_vectores(tmp_path: Path) -> None:
    _cliente(tmp_path, ProveedorFalso()).post(VERIFICAR)
    datos = _cliente(tmp_path, None).get(REFERENCIA, params={"modelo": "modelo-falso", "dimensiones": 4, "incluir_vectores": True}).json()["data"]
    assert len(datos) == 1 and len(datos[0]["vectores"]) == len(FRASES_CONTROL)


def test_comparar_huellas_es_pura(tmp_path: Path) -> None:
    reloj = lambda: "t"
    referencia = calcular_huella(ProveedorFalso(), reloj)
    assert calcular_huella(ProveedorFalso(), reloj) == referencia
    resultado = comparar_huellas(referencia, calcular_huella(ProveedorFalso(deriva=0.5), reloj), 0.999)
    assert resultado.estado == "deriva_detectada"
    assert [item.indice for item in resultado.detalle] == list(range(len(FRASES_CONTROL)))
    otro = referencia.model_copy(update={"modelo": "otro"})
    with pytest.raises(ValueError, match="embedding_space_incompatible"):
        comparar_huellas(referencia, otro, 0.999)
