"""Idea 3.3: mecanismo de embeddings de imagen del plano (sin red, proveedor falso)."""

from __future__ import annotations

import math
from hashlib import sha256
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.contratos.modelos import (
    Bounds2D,
    DrawingContour,
    DrawingEntity,
    DrawingExtraction,
    DrawingObservation,
    DrawingView,
    Point2D,
)
from backend.app.precedentes.api_imagen import crear_router_imagen
from backend.app.precedentes.imagen import (
    AlmacenImagen,
    ErrorImagen,
    VistaPng,
    VistasDeRun,
    agregar_por_run,
    renderizar_vistas,
    validar_y_normalizar,
)

URL_INDEXAR = "/api/v1/precedentes/imagen/indexar"
URL_SIMILARES = "/api/v1/precedentes/imagen/similares"


class ProveedorFalso:
    def __init__(
        self, vectores: dict[bytes, tuple[float, ...]], espacio_id: str = "falso-v1", dimensiones: int = 3
    ) -> None:
        self.vectores = vectores
        self.espacio_id = espacio_id
        self.dimensiones = dimensiones
        self.llamadas: list[bytes] = []

    def embeber(self, png: bytes) -> tuple[float, ...]:
        self.llamadas.append(png)
        return self.vectores[png]


def _vista(vista_id: str, png: bytes) -> VistaPng:
    return VistaPng(vista_id=vista_id, png=png, sha256=sha256(png).hexdigest())


def _catalogo(**runs: tuple[tuple[str, bytes], ...]):
    def obtener(run_id: str) -> VistasDeRun:
        if run_id not in runs:
            raise KeyError(run_id)
        return VistasDeRun(run_id=run_id, vistas=tuple(_vista(v, p) for v, p in runs[run_id]))

    return obtener


def _cliente(tmp_path, proveedor=None, obtener_vistas=None, repositorio=None) -> TestClient:
    app = FastAPI()
    app.include_router(
        crear_router_imagen(
            repositorio, tmp_path / "precedentes_imagen.sqlite3", proveedor, obtener_vistas=obtener_vistas
        )
    )
    return TestClient(app)


VECTORES = {
    b"q": (1.0, 0.0, 0.0),
    b"a": (2.0, 0.0, 0.0),  # coseno 1.0 con q (no normalizado a propósito)
    b"b": (1.0, 1.0, 0.0),  # coseno ~0.707
    b"c": (0.0, 0.0, 1.0),  # coseno 0
    b"d": (0.0, 3.0, 0.0),
}
CATALOGO = _catalogo(
    q=(("v1", b"q"),),
    run_b=(("v1", b"b"), ("v2", b"c")),
    run_a=(("v1", b"a"),),
    run_a2=(("v9", b"a"),),
    run_c=(("v1", b"c"),),
    run_d=(("v1", b"d"),),
)


def _indexar_todo(cliente: TestClient) -> None:
    for run_id in ("q", "run_b", "run_a", "run_a2", "run_c", "run_d"):
        assert cliente.post(URL_INDEXAR, json={"run_id": run_id}).status_code == 200


def test_indexar_sin_proveedor_devuelve_503(tmp_path) -> None:
    cliente = _cliente(tmp_path, obtener_vistas=CATALOGO)
    respuesta = cliente.post(URL_INDEXAR, json={"run_id": "q"})
    assert respuesta.status_code == 503
    assert respuesta.json()["error"]["code"] == "proveedor_imagen_no_disponible"


def test_indexar_usa_cache_por_hash(tmp_path) -> None:
    proveedor = ProveedorFalso(VECTORES)
    cliente = _cliente(tmp_path, proveedor, CATALOGO)
    primera = cliente.post(URL_INDEXAR, json={"run_id": "run_a"}).json()["data"]
    assert primera["vistas"][0]["desde_cache"] is False
    assert proveedor.llamadas == [b"a"]
    # Mismo PNG en otro run y reindexado del mismo run: no se reembebe.
    segunda = cliente.post(URL_INDEXAR, json={"run_id": "run_a2"}).json()["data"]
    cliente.post(URL_INDEXAR, json={"run_id": "run_a"})
    assert segunda["vistas"][0]["desde_cache"] is True
    assert proveedor.llamadas == [b"a"]


def test_reindexar_con_revision_nula_no_duplica(tmp_path) -> None:
    proveedor = ProveedorFalso(VECTORES)
    cliente = _cliente(tmp_path, proveedor, CATALOGO)
    for _ in range(3):
        cliente.post(URL_INDEXAR, json={"run_id": "run_b"})
    almacen = AlmacenImagen(tmp_path / "precedentes_imagen.sqlite3")
    vistas = almacen.vectores_del_espacio("falso-v1")["run_b"]
    assert [v.vista_id for v in vistas] == ["v1", "v2"]
    assert all(v.result_revision is None for v in vistas)


def test_run_inexistente_devuelve_404(tmp_path) -> None:
    cliente = _cliente(tmp_path, ProveedorFalso(VECTORES), CATALOGO)
    respuesta = cliente.post(URL_INDEXAR, json={"run_id": "no-existe"})
    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "run_no_encontrado"


def test_similares_orden_desempate_exclusion_y_nota(tmp_path) -> None:
    cliente = _cliente(tmp_path, ProveedorFalso(VECTORES), CATALOGO)
    _indexar_todo(cliente)
    datos = cliente.post(URL_SIMILARES, json={"run_id": "q", "limite": 10, "umbral_minimo": 0.5}).json()["data"]
    assert datos["estado"] == "ok"
    assert datos["metrica"] == "coseno"
    assert datos["es_probabilidad"] is False
    assert "no es una probabilidad" in datos["nota"]
    ids = [p["run_id"] for p in datos["precedentes"]]
    assert ids == ["run_a", "run_a2", "run_b"]  # empate en 1.0 resuelto por id; q excluido
    assert datos["precedentes"][0]["score_coseno"] == pytest.approx(1.0)
    # Agregación por máximo: run_b tiene v2 ortogonal pero cuenta su mejor vista.
    run_b = datos["precedentes"][2]
    assert run_b["score_coseno"] == pytest.approx(1 / math.sqrt(2))
    assert (run_b["vista_consulta"], run_b["vista_candidata"]) == ("v1", "v1")
    assert datos["candidatos_evaluados"] == 5


def test_similares_limite(tmp_path) -> None:
    cliente = _cliente(tmp_path, ProveedorFalso(VECTORES), CATALOGO)
    _indexar_todo(cliente)
    datos = cliente.post(URL_SIMILARES, json={"run_id": "q", "limite": 1, "umbral_minimo": -1}).json()["data"]
    assert [p["run_id"] for p in datos["precedentes"]] == ["run_a"]


def test_similares_se_abstiene_bajo_umbral(tmp_path) -> None:
    cliente = _cliente(tmp_path, ProveedorFalso(VECTORES), CATALOGO)
    _indexar_todo(cliente)
    respuesta = cliente.post(URL_SIMILARES, json={"run_id": "run_d", "umbral_minimo": 0.99})
    assert respuesta.status_code == 200
    datos = respuesta.json()["data"]
    assert datos["estado"] == "sin_precedentes_suficientes"
    assert datos["precedentes"] == []


def test_buscar_sin_proveedor_sobre_vectores_guardados(tmp_path) -> None:
    _indexar_todo(_cliente(tmp_path, ProveedorFalso(VECTORES), CATALOGO))

    def prohibido(run_id: str) -> VistasDeRun:
        raise AssertionError("no debe renderizar")

    cliente = _cliente(tmp_path, None, prohibido)
    datos = cliente.post(URL_SIMILARES, json={"run_id": "q", "umbral_minimo": 0.9}).json()["data"]
    assert datos["espacio_id"] == "falso-v1"
    assert [p["run_id"] for p in datos["precedentes"]] == ["run_a", "run_a2"]


def test_buscar_sin_proveedor_run_no_indexado_503(tmp_path) -> None:
    cliente = _cliente(tmp_path, None, CATALOGO)
    respuesta = cliente.post(URL_SIMILARES, json={"run_id": "q", "umbral_minimo": 0.5})
    assert respuesta.status_code == 503
    assert respuesta.json()["error"]["code"] == "proveedor_imagen_no_disponible"


def test_buscar_con_proveedor_indexa_bajo_demanda(tmp_path) -> None:
    proveedor = ProveedorFalso(VECTORES)
    cliente = _cliente(tmp_path, proveedor, CATALOGO)
    cliente.post(URL_INDEXAR, json={"run_id": "run_a"})
    datos = cliente.post(URL_SIMILARES, json={"run_id": "q", "umbral_minimo": 0.5}).json()["data"]
    assert [p["run_id"] for p in datos["precedentes"]] == ["run_a"]
    assert proveedor.llamadas == [b"a", b"q"]


def test_solo_compara_mismo_espacio(tmp_path) -> None:
    _indexar_todo(_cliente(tmp_path, ProveedorFalso(VECTORES), CATALOGO))
    otro = ProveedorFalso({b"q": (0.0, 1.0, 0.0), b"d": (0.0, 1.0, 0.0)}, espacio_id="otro-v1")
    cliente = _cliente(tmp_path, otro, _catalogo(q=(("v1", b"q"),), run_d=(("v1", b"d"),)))
    cliente.post(URL_INDEXAR, json={"run_id": "run_d"})
    datos = cliente.post(URL_SIMILARES, json={"run_id": "q", "umbral_minimo": -1}).json()["data"]
    assert datos["espacio_id"] == "otro-v1"
    assert [p["run_id"] for p in datos["precedentes"]] == ["run_d"]
    # Sin proveedor y con el run en dos espacios hay que elegir.
    ambiguo = _cliente(tmp_path, None, CATALOGO).post(URL_SIMILARES, json={"run_id": "q", "umbral_minimo": 0})
    assert ambiguo.status_code == 422
    assert ambiguo.json()["error"]["code"] == "espacio_ambiguo"
    explicito = _cliente(tmp_path, None, CATALOGO).post(
        URL_SIMILARES, json={"run_id": "q", "umbral_minimo": 0.9, "espacio_id": "falso-v1"}
    )
    assert [p["run_id"] for p in explicito.json()["data"]["precedentes"]] == ["run_a", "run_a2"]


@pytest.mark.parametrize(
    "vector",
    [(1.0, 0.0), (float("nan"), 0.0, 1.0), (0.0, 0.0, 0.0), (float("inf"), 1.0, 1.0)],
)
def test_vector_invalido_se_rechaza_y_no_persiste(tmp_path, vector) -> None:
    proveedor = ProveedorFalso({b"q": vector})
    cliente = _cliente(tmp_path, proveedor, CATALOGO)
    respuesta = cliente.post(URL_INDEXAR, json={"run_id": "q"})
    assert respuesta.status_code == 502
    assert respuesta.json()["error"]["code"] == "vector_invalido"
    almacen = AlmacenImagen(tmp_path / "precedentes_imagen.sqlite3")
    assert almacen.vectores_del_espacio("falso-v1") == {}


def test_fallo_del_proveedor_502(tmp_path) -> None:
    cliente = _cliente(tmp_path, ProveedorFalso({}), CATALOGO)
    respuesta = cliente.post(URL_INDEXAR, json={"run_id": "q"})
    assert respuesta.status_code == 502
    assert respuesta.json()["error"]["code"] == "proveedor_imagen_fallo"


def test_peticion_invalida_422(tmp_path) -> None:
    cliente = _cliente(tmp_path, ProveedorFalso(VECTORES), CATALOGO)
    assert cliente.post(URL_SIMILARES, json={"run_id": "q"}).status_code == 422
    assert cliente.post(URL_SIMILARES, json={"run_id": "q", "umbral_minimo": 2}).status_code == 422
    assert cliente.post(URL_SIMILARES, json={"run_id": "q", "umbral_minimo": 0, "limite": 0}).status_code == 422


def test_funciones_puras() -> None:
    assert validar_y_normalizar([3, 4], 2) == pytest.approx((0.6, 0.8))
    with pytest.raises(ErrorImagen):
        validar_y_normalizar((True, 1.0), 2)
    assert agregar_por_run({"v": (1.0, 0.0)}, {}, excluir_run_id="x") == ()


# --- Render real desde la extracción del run (agente/vision.py) ------------------------


def _extraccion(desplazamiento: float, vistas: int = 1) -> DrawingExtraction:
    entidades, contornos, vistas_plano, observaciones = [], [], [], []
    for indice in range(vistas):
        vista_id = f"view-{indice}"
        puntos = tuple(
            Point2D(x=x + desplazamiento, y=y)
            for x, y in ((0, 0), (100, 0), (100, 60 + desplazamiento), (0, 60 + desplazamiento))
        )
        entidad = DrawingEntity(
            id=f"entity-{indice}", kind="LWPOLYLINE", layer="0", source_points=puntos, points_mm=puntos
        )
        entidades.append(entidad)
        contornos.append(
            DrawingContour(
                id=f"contour-{indice}",
                view_id=vista_id,
                source_entity_ids=(entidad.id,),
                points_source=puntos,
                points_mm=puntos,
                closed=True,
            )
        )
        vistas_plano.append(
            DrawingView(
                id=vista_id,
                label="FRONT",
                entity_ids=(entidad.id,),
                bounds_source=Bounds2D(min_x=0, min_y=0, max_x=200, max_y=200),
                bounds_mm=Bounds2D(min_x=0, min_y=0, max_x=200, max_y=200),
            )
        )
        observaciones.append(
            DrawingObservation(id=f"obs-{indice}", view_id=vista_id, contour_ids=(f"contour-{indice}",), dimension_ids=())
        )
    return DrawingExtraction(
        drawing_id="drawing",
        status="ready",
        source_unit="mm",
        unit_scale_to_mm=1.0,
        coordinate_unit="mm",
        entities=tuple(entidades),
        views=tuple(vistas_plano),
        contours=tuple(contornos),
        dimensions=(),
        evidence=(),
        observations=tuple(observaciones),
    )


class RepositorioFalso:
    def __init__(self, extracciones: dict[str, DrawingExtraction]) -> None:
        self.extracciones = extracciones

    def get_run(self, run_id: str):
        if run_id not in self.extracciones:
            raise KeyError(run_id)
        return SimpleNamespace(result_revision=1)

    def get_extraction(self, run_id: str) -> DrawingExtraction:
        return self.extracciones[run_id]


class ProveedorPorBytes:
    espacio_id = "bytes-v1"
    dimensiones = 4

    def embeber(self, png: bytes) -> tuple[float, ...]:
        digest = sha256(png).digest()
        return tuple(float(b) + 1.0 for b in digest[:4])


def test_renderizar_vistas_limita_a_tres_y_es_determinista() -> None:
    extraccion = _extraccion(0, vistas=5)
    vistas, omitidas = renderizar_vistas(extraccion)
    assert [v.vista_id for v in vistas] == ["view-0", "view-1", "view-2"]
    assert omitidas == ()
    assert vistas == renderizar_vistas(extraccion)[0]
    assert all(v.png.startswith(b"\x89PNG") for v in vistas)


def test_indexar_desde_repositorio_renderiza_vistas(tmp_path) -> None:
    repositorio = RepositorioFalso({"r1": _extraccion(0), "r2": _extraccion(0), "r3": _extraccion(40)})
    cliente = _cliente(tmp_path, ProveedorPorBytes(), repositorio=repositorio)
    for run_id in ("r1", "r2", "r3"):
        datos = cliente.post(URL_INDEXAR, json={"run_id": run_id}).json()["data"]
        assert datos["result_revision"] == 1
        assert [v["vista_id"] for v in datos["vistas"]] == ["view-0"]
    datos = cliente.post(URL_SIMILARES, json={"run_id": "r1", "umbral_minimo": 0.999999}).json()["data"]
    # r2 tiene el mismo plano: mismo PNG, coseno 1.
    assert datos["precedentes"][0]["run_id"] == "r2"
    assert datos["precedentes"][0]["score_coseno"] == pytest.approx(1.0)
    assert datos["precedentes"][0]["result_revision"] == 1
