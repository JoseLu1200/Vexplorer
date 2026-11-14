"""Tests de la idea 3.5. Solo datos sintéticos, marcados como tales; sin red."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.historico.models import (
    HistoricalComparable,
    HistoricalImport,
    HistoricalRecord,
)
from backend.app.historico.real_service import HistoricalStore
from backend.app.precedentes.api_herrajes import crear_router_herrajes
from backend.app.precedentes.comun import PREFIJO_API
from backend.app.precedentes.herrajes import (
    AlmacenHerrajes,
    RegistroHerrajes,
    agregar_sugerencias,
)

RUTA = PREFIJO_API + "/herrajes"


def _registro_historico(record_id: str) -> dict:
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
        "currency": "EUR",
        "actual_cost": 100,
        "cost_basis": "actual",
        "origin": "synthetic",
        "provenance": {"source": "demo fixture sintético", "source_date": "2026-10-01"},
        "included_scope": ["total"],
        "cost_scope": ["total"],
    }


def _herrajes(record_id: str, herrajes: list[dict], origen: str = "synthetic") -> dict:
    return {
        "record_id": record_id,
        "origen": origen,
        "procedencia": {"fuente": "demo fixture sintético", "fecha": "2026-10-01"},
        "herrajes": herrajes,
    }


OBJETIVO = {
    "family": "armario",
    "width_mm": 800,
    "depth_mm": 400,
    "height_mm": 1800,
    "basis_revision": "objetivo-r1",
}


def _montar(tmp_path) -> tuple[TestClient, AlmacenHerrajes]:
    store = HistoricalStore(tmp_path / "historico.sqlite3")
    store.import_records(
        HistoricalImport.model_validate(
            {"records": [_registro_historico(f"s-{i}") for i in (1, 2, 3, 4)]}
        )
    )
    almacen = AlmacenHerrajes(tmp_path / "precedentes_herrajes.sqlite3")
    app = FastAPI()
    app.include_router(crear_router_herrajes(store, almacen))
    return TestClient(app), almacen


def _datos_demo() -> dict:
    return {
        "registros": [
            _herrajes(
                "s-1",
                [
                    {"tipo": "Bisagra cazoleta 35", "cantidad": 2, "por_unidad_de": "Puerta"},
                    {"tipo": "Tirador", "cantidad": 1, "por_unidad_de": "puerta"},
                ],
            ),
            _herrajes(
                "s-2",
                [{"tipo": "bisagra  cazoleta 35", "cantidad": 2, "por_unidad_de": "puerta"}],
            ),
            _herrajes(
                "s-3",
                [
                    {"tipo": "BISAGRA CAZOLETA 35", "cantidad": 3, "por_unidad_de": "puerta"},
                    {"tipo": "taladro baldas", "notas": "sistema 32"},
                ],
            ),
        ]
    }


def test_importacion_idempotente_y_normalizada(tmp_path) -> None:
    cliente, _ = _montar(tmp_path)
    primera = cliente.post(RUTA + "/registros", json=_datos_demo()).json()["data"]
    assert primera == {"insertados": 3, "actualizados": 0, "sin_cambios": 0}
    segunda = cliente.post(RUTA + "/registros", json=_datos_demo()).json()["data"]
    assert segunda == {"insertados": 0, "actualizados": 0, "sin_cambios": 3}
    # Mismo contenido con otra grafía y otro orden: misma huella.
    variante = _herrajes(
        "s-1",
        [
            {"tipo": "tirador ", "cantidad": 1, "por_unidad_de": "PUERTA"},
            {"tipo": "bisagra cazoleta 35", "cantidad": 2, "por_unidad_de": "puerta"},
        ],
    )
    assert cliente.post(RUTA + "/registros", json={"registros": [variante]}).json()[
        "data"
    ]["sin_cambios"] == 1
    cambiado = _herrajes(
        "s-1", [{"tipo": "bisagra cazoleta 35", "cantidad": 4, "por_unidad_de": "puerta"}]
    )
    assert cliente.post(RUTA + "/registros", json={"registros": [cambiado]}).json()[
        "data"
    ]["actualizados"] == 1


def test_listado_paginado_y_ordenado(tmp_path) -> None:
    cliente, _ = _montar(tmp_path)
    cliente.post(RUTA + "/registros", json=_datos_demo())
    pagina = cliente.get(RUTA + "/registros", params={"limite": 2}).json()["data"]
    assert pagina["total"] == 3
    assert [r["record_id"] for r in pagina["items"]] == ["s-1", "s-2"]
    assert pagina["items"][0]["herrajes"][0]["tipo"] == "bisagra cazoleta 35"
    assert pagina["items"][0]["origen"] == "synthetic"


def test_tipos_duplicados_y_cantidad_invalida_se_rechazan(tmp_path) -> None:
    cliente, _ = _montar(tmp_path)
    duplicado = _herrajes(
        "s-1", [{"tipo": "Tirador"}, {"tipo": "tirador"}]
    )
    assert cliente.post(RUTA + "/registros", json={"registros": [duplicado]}).status_code == 422
    invalido = _herrajes("s-1", [{"tipo": "tirador", "cantidad": 0}])
    assert cliente.post(RUTA + "/registros", json={"registros": [invalido]}).status_code == 422
    demasiados = _herrajes("s-1", [{"tipo": f"herraje {i}"} for i in range(51)])
    assert cliente.post(RUTA + "/registros", json={"registros": [demasiados]}).status_code == 422
    notas_largas = _herrajes("s-1", [{"tipo": "tirador", "notas": "x" * 501}])
    assert cliente.post(RUTA + "/registros", json={"registros": [notas_largas]}).status_code == 422
    muchos = {"registros": [_herrajes(f"s-{i}", [{"tipo": "tirador"}]) for i in range(1001)]}
    assert cliente.post(RUTA + "/registros", json=muchos).status_code == 422


def test_minimo_soporte_no_puede_superar_limite(tmp_path) -> None:
    cliente, _ = _montar(tmp_path)
    respuesta = cliente.post(
        RUTA + "/sugerencias",
        json={"objetivo": OBJETIVO, "limite": 2, "minimo_soporte": 3},
    )
    assert respuesta.status_code == 422
    assert "minimo_soporte no puede superar limite" in respuesta.text


def test_proporcion_minima_exige_ademas_soporte_relativo() -> None:
    comparables = tuple(
        HistoricalComparable(
            record=HistoricalRecord.model_validate(_registro_historico(f"s-{i}")),
            score=0.9,
            score_components={},
            differences=(),
            missing_fields=(),
        )
        for i in range(5)
    )
    registros = {
        f"s-{i}": RegistroHerrajes.model_validate(
            _herrajes(
                f"s-{i}",
                [{"tipo": "bisagra"}] + ([{"tipo": "tirador"}] if i < 2 else []),
            )
        )
        for i in range(5)
    }
    resultado = agregar_sugerencias(
        comparables, registros, minimo_soporte=2, incluir_sinteticos=True
    )
    por_tipo = {s.tipo: s for s in resultado.sugerencias}
    assert resultado.proporcion_minima == 0.5
    assert por_tipo["bisagra"].estado == "hipotesis"
    assert por_tipo["tirador"].soporte_texto == "2/5"
    assert por_tipo["tirador"].estado == "abstencion"
    assert "Proporción 2/5" in por_tipo["tirador"].motivo_abstencion
    laxo = agregar_sugerencias(
        comparables,
        registros,
        minimo_soporte=2,
        incluir_sinteticos=True,
        proporcion_minima=0.4,
    )
    assert {s.tipo: s.estado for s in laxo.sugerencias}["tirador"] == "hipotesis"


def test_sugerencias_con_soporte_cantidades_y_abstencion(tmp_path) -> None:
    cliente, _ = _montar(tmp_path)
    cliente.post(RUTA + "/registros", json=_datos_demo())
    respuesta = cliente.post(
        RUTA + "/sugerencias",
        json={"objetivo": OBJETIVO, "incluir_sinteticos": True, "minimo_soporte": 2},
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()["data"]
    assert datos["naturaleza"] == "hipotesis"
    assert datos["comparables_recuperados"] == 4
    assert datos["comparables_con_datos"] == 3
    assert datos["record_ids_sin_datos"] == ["s-4"]
    por_tipo = {s["tipo"]: s for s in datos["sugerencias"]}
    bisagra = por_tipo["bisagra cazoleta 35"]
    assert bisagra["estado"] == "hipotesis"
    assert bisagra["soporte_texto"] == "3/3"
    assert bisagra["cantidades"] == [
        {"por_unidad_de": "puerta", "n": 3, "mediana": 2.0, "minimo": 2, "maximo": 3}
    ]
    assert bisagra["solo_sintetico"] is True
    assert por_tipo["tirador"]["estado"] == "abstencion"
    assert por_tipo["tirador"]["cantidades"] == []
    assert por_tipo["taladro baldas"]["estado"] == "abstencion"
    assert datos["sugerencias"][0]["tipo"] == "bisagra cazoleta 35"
    assert any("Todo el soporte es sintético" in a for a in datos["avisos"])


def test_sin_sinteticos_no_hay_soporte(tmp_path) -> None:
    cliente, _ = _montar(tmp_path)
    cliente.post(RUTA + "/registros", json=_datos_demo())
    datos = cliente.post(
        RUTA + "/sugerencias", json={"objetivo": OBJETIVO}
    ).json()["data"]
    assert datos["comparables_recuperados"] == 0
    assert datos["sugerencias"] == []
    assert any("Ningún comparable" in a for a in datos["avisos"])


def test_herrajes_sinteticos_se_descartan_sin_opt_in() -> None:
    registro = HistoricalRecord.model_validate(_registro_historico("s-1"))
    comparable = HistoricalComparable(
        record=registro, score=0.9, score_components={}, differences=(), missing_fields=()
    )
    herrajes = RegistroHerrajes.model_validate(
        _herrajes("s-1", [{"tipo": "tirador", "cantidad": 1}])
    )
    resultado = agregar_sugerencias(
        (comparable,), {"s-1": herrajes}, minimo_soporte=1, incluir_sinteticos=False
    )
    assert resultado.comparables_con_datos == 0
    assert resultado.sugerencias == ()
    assert any("sintéticos excluidos" in a for a in resultado.avisos)
    con_opt_in = agregar_sugerencias(
        (comparable,), {"s-1": herrajes}, minimo_soporte=1, incluir_sinteticos=True
    )
    assert con_opt_in.sugerencias[0].estado == "hipotesis"
    assert con_opt_in == agregar_sugerencias(
        (comparable,), {"s-1": herrajes}, minimo_soporte=1, incluir_sinteticos=True
    )


def test_importacion_concurrente_idempotente(tmp_path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from backend.app.precedentes.herrajes import (
        AlmacenHerrajes,
        ImportacionHerrajes,
        RegistroHerrajes,
    )

    almacen = AlmacenHerrajes(tmp_path / "herrajes.sqlite3")
    datos = ImportacionHerrajes(
        registros=(
            RegistroHerrajes.model_validate(_herrajes("rec-1", [{"tipo": "bisagra", "cantidad": 2}])),
            RegistroHerrajes.model_validate(_herrajes("rec-2", [{"tipo": "tirador", "cantidad": 1}])),
        )
    )

    def tarea() -> None:
        almacen.importar(datos)

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(lambda _: tarea(), range(20)))

    pagina = almacen.listar()
    assert pagina.total == 2
