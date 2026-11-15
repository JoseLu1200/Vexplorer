from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.precedentes.api_decisiones import crear_router_decisiones
from backend.app.precedentes.decisiones import (
    AlmacenDecisiones,
    Decision,
    DecisionEntrada,
    recomendar_pesos,
    resumir,
)


def _reloj():
    contador = iter(f"2026-01-01T00:00:{segundo:02d}+00:00" for segundo in range(60))
    return lambda: next(contador)


def _decision(consulta: str, aceptado: bool, **componentes: float) -> Decision:
    return Decision(consulta_id=consulta, candidato_id="c", metodo="geometric", score_components=componentes, aceptado=aceptado, motivo=None, actor=None, registrada_en="t", actualizada_en="t")


def _entrada(**cambios: object) -> DecisionEntrada:
    base: dict[str, object] = {"consulta_id": "q1", "candidato_id": "c1", "metodo": "geometric", "score_components": {"dimensions": 0.9, "roles": 0.5, "dimensions_weight": 0.7}, "aceptado": True}
    return DecisionEntrada.model_validate({**base, **cambios})


def test_recomendar_pesos_separa_componentes() -> None:
    decisiones = (
        _decision("a", True, dimensions=0.9, roles=0.5, thickness=0.8, dimensions_weight=0.6),
        _decision("b", True, dimensions=0.8, roles=0.4, dimensions_weight=0.6),
        _decision("c", False, dimensions=0.3, roles=0.5, thickness=0.9, dimensions_weight=0.6),
        _decision("d", False, dimensions=0.2, roles=0.4, dimensions_weight=0.6),
    )
    resultado = recomendar_pesos(decisiones, ("roles", "dimensions", "thickness"), 4)
    assert resultado.estado == "recomendacion"
    assert resultado.aplicada_automaticamente is False
    assert (resultado.aceptadas, resultado.rechazadas) == (2, 2)
    assert resultado.pesos_recomendados == {"dimensions": 1.0, "roles": 0.0, "thickness": 0.0}  # thickness tiene datos (auc 0)
    assert sum(resultado.pesos_recomendados.values()) == pytest.approx(1.0)
    filas = {fila.componente: fila for fila in resultado.componentes}
    assert [fila.componente for fila in resultado.componentes] == ["dimensions", "roles", "thickness"]
    assert filas["dimensions"].auc == 1.0
    assert filas["roles"].auc == 0.5
    assert (filas["thickness"].aceptadas, filas["thickness"].rechazadas) == (1, 1)  # ausente no cuenta como 0
    assert "dimensions_weight" not in resultado.pesos_recomendados


def test_recomendar_pesos_reparte_entre_componentes() -> None:
    decisiones = (
        _decision("a", True, dimensions=0.9, roles=0.9),
        _decision("b", True, dimensions=0.4, roles=0.8),
        _decision("c", False, dimensions=0.5, roles=0.1),
        _decision("d", False, dimensions=0.1, roles=0.2),
    )
    resultado = recomendar_pesos(decisiones, ("dimensions", "roles"), 2)
    # AUC dimensions = 0.75 -> separación 0.25; roles = 1.0 -> 0.5; normalizado 1/3 y 2/3.
    assert resultado.pesos_recomendados == {"dimensions": pytest.approx(1 / 3, abs=1e-6), "roles": pytest.approx(2 / 3, abs=1e-6)}


@pytest.mark.parametrize(
    ("decisiones", "minimo", "prefijo"),
    [
        ((), 1, "decisiones_insuficientes"),
        ((_decision("a", True, dimensions=0.9), _decision("b", False, dimensions=0.1)), 3, "decisiones_insuficientes"),
        ((_decision("a", True, dimensions=0.9), _decision("b", True, dimensions=0.1)), 2, "falta_una_clase"),
        ((_decision("a", True, dimensions=0.1), _decision("b", False, dimensions=0.9)), 2, "sin_separacion"),
    ],
)
def test_recomendar_pesos_abstencion(decisiones: tuple[Decision, ...], minimo: int, prefijo: str) -> None:
    resultado = recomendar_pesos(decisiones, ("dimensions",), minimo)
    assert resultado.estado == "abstencion"
    assert resultado.motivo is not None and resultado.motivo.startswith(prefijo)
    assert resultado.pesos_recomendados is None
    assert resultado.aceptadas + resultado.rechazadas == len(decisiones)


def test_almacen_idempotente_y_actualiza(tmp_path: Path) -> None:
    almacen = AlmacenDecisiones(tmp_path / "d" / "precedentes_decisiones.sqlite3", ahora=_reloj())
    assert almacen.registrar(_entrada()).estado == "creada"
    repetida = almacen.registrar(_entrada())
    assert repetida.estado == "sin_cambios"
    assert repetida.decision.registrada_en == "2026-01-01T00:00:00+00:00"
    cambiada = almacen.registrar(_entrada(aceptado=False, motivo="otra familia"))
    assert cambiada.estado == "actualizada"
    assert cambiada.decision.registrada_en == "2026-01-01T00:00:00+00:00"
    assert cambiada.decision.actualizada_en != cambiada.decision.registrada_en
    assert len(almacen.listar()) == 1
    # Actor distinto = decisión distinta; actor None es una clave estable propia.
    almacen.registrar(_entrada(actor="ana"))
    almacen.registrar(_entrada(actor="ana"))
    listadas = almacen.listar("geometric")
    assert len(listadas) == 2
    assert listadas[0].score_components == {"dimensions": 0.9, "dimensions_weight": 0.7, "roles": 0.5}
    assert almacen.listar("semantic") == ()


def test_entrada_rechaza_no_finitos() -> None:
    with pytest.raises(ValidationError):
        _entrada(score_components={"dimensions": float("nan")})


def test_resumir_usa_componentes_del_metodo(tmp_path: Path) -> None:
    almacen = AlmacenDecisiones(tmp_path / "x.sqlite3", ahora=_reloj())
    almacen.registrar(_entrada(consulta_id="q1", aceptado=True, score_components={"dimensions": 0.9, "roles": 0.5}))
    almacen.registrar(_entrada(consulta_id="q2", aceptado=False, score_components={"dimensions": 0.2, "roles": 0.5}))
    resumen = resumir(almacen.listar(), "geometric", 2)
    assert (resumen.total, resumen.aceptadas, resumen.rechazadas) == (2, 1, 1)
    assert [fila.componente for fila in resumen.recomendacion.componentes] == ["dimensions", "roles", "thickness"]
    assert resumen.recomendacion.pesos_recomendados == {"dimensions": 1.0, "roles": 0.0}  # thickness sin datos: fuera
    otro = resumir(almacen.listar(), "hibrido", 2)
    assert otro.total == 0 and otro.recomendacion.estado == "abstencion"


def _cliente(tmp_path: Path, actor: str | None = None) -> TestClient:
    app = FastAPI()
    if actor is not None:
        @app.middleware("http")
        async def poner_actor(request: Request, call_next):
            request.state.actor = actor
            return await call_next(request)
    app.include_router(crear_router_decisiones(AlmacenDecisiones(tmp_path / "api.sqlite3", ahora=_reloj()), minimo_decisiones=2))
    return TestClient(app)


CUERPO = {"consulta_id": "q1", "candidato_id": "c1", "metodo": "geometric", "score_components": {"dimensions": 0.9, "roles": 0.4}, "aceptado": True, "actor": "suplantado"}
RUTA = "/api/v1/precedentes/decisiones"


def test_api_registrar_y_resumen(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    respuesta = cliente.post(RUTA, json=CUERPO)
    assert respuesta.status_code == 201
    assert respuesta.json()["data"]["estado"] == "creada"
    assert cliente.post(RUTA, json=CUERPO).status_code == 200
    cliente.post(RUTA, json={**CUERPO, "consulta_id": "q2", "aceptado": False, "score_components": {"dimensions": 0.1, "roles": 0.4}})
    resumen = cliente.get(RUTA + "/resumen", params={"metodo": "geometric"})
    assert resumen.status_code == 200
    datos = resumen.json()["data"]
    assert (datos["total"], datos["aceptadas"], datos["rechazadas"]) == (2, 1, 1)
    assert datos["recomendacion"]["estado"] == "recomendacion"
    assert datos["recomendacion"]["aplicada_automaticamente"] is False
    estricto = cliente.get(RUTA + "/resumen", params={"metodo": "geometric", "minimo": "10"}).json()["data"]
    assert estricto["recomendacion"]["estado"] == "abstencion"


def test_api_actor_autoritativo(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path, actor="ana")
    datos = cliente.post(RUTA, json=CUERPO).json()["data"]
    assert datos["decision"]["actor"] == "ana"


@pytest.mark.parametrize(
    "contenido",
    [
        b"no json",
        b"[1]",
        b'{"consulta_id": "q"}',
        b'{"consulta_id": "q", "candidato_id": "c", "metodo": "m", "score_components": {"x": NaN}, "aceptado": true}',
    ],
)
def test_api_errores_registro(tmp_path: Path, contenido: bytes) -> None:
    respuesta = _cliente(tmp_path).post(RUTA, content=contenido, headers={"Content-Type": "application/json"})
    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["code"] == "decision_invalida"
    assert respuesta.json()["data"] is None


def test_api_errores_resumen(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    assert cliente.get(RUTA + "/resumen").json()["error"]["code"] == "metodo_requerido"
    assert cliente.get(RUTA + "/resumen", params={"metodo": "geometric", "minimo": "0"}).json()["error"]["code"] == "minimo_invalido"


def test_api_sin_autenticacion_ignora_actor_del_cuerpo(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    primera = cliente.post(RUTA, json={**CUERPO, "actor": "jefe"}).json()["data"]
    assert primera["decision"]["actor"] is None
    # Variar el actor no crea decisiones nuevas: no se puede inflar la recomendación.
    segunda = cliente.post(RUTA, json={**CUERPO, "actor": "otro"})
    assert segunda.status_code == 200 and segunda.json()["data"]["estado"] == "sin_cambios"
    datos = cliente.get(RUTA + "/resumen", params={"metodo": "geometric"}).json()["data"]
    assert datos["total"] == 1


@pytest.mark.parametrize(
    "cambio",
    [
        {"consulta_id": "x" * 201},
        {"candidato_id": "x" * 201},
        {"metodo": "m" * 65},
        {"score_components": {f"c{indice}": 0.5 for indice in range(33)}},
        {"score_components": {"k" * 65: 0.5}},
    ],
)
def test_api_rechaza_campos_excesivos(tmp_path: Path, cambio: dict) -> None:
    respuesta = _cliente(tmp_path).post(RUTA, json={**CUERPO, **cambio})
    assert respuesta.status_code == 422
    assert respuesta.json()["error"]["code"] == "decision_invalida"


def test_api_rechaza_cuerpo_grande(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    respuesta = cliente.post(RUTA, json={**CUERPO, "motivo": "x" * (70 * 1024)})
    assert respuesta.status_code == 413
    assert respuesta.json()["error"]["code"] == "cuerpo_demasiado_grande"
    # Sin Content-Length (envío por trozos) también se corta.
    trozos = (bytes([b]) * 1024 for b in [32] * 70)
    sin_longitud = cliente.post(RUTA, content=trozos, headers={"Content-Type": "application/json"})
    assert sin_longitud.status_code == 413
    assert cliente.get(RUTA + "/resumen", params={"metodo": "geometric"}).json()["data"]["total"] == 0


def test_registro_concurrente_idempotente(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    almacen = AlmacenDecisiones(tmp_path / "decisiones.sqlite3")
    entrada = DecisionEntrada(
        consulta_id="c-1",
        candidato_id="cand-1",
        metodo="geometric",
        score_components={"dimensions": 0.9, "roles": 0.8},
        aceptado=True,
        actor="tester",
    )

    def tarea() -> str:
        res = almacen.registrar(entrada)
        return res.estado

    with ThreadPoolExecutor(max_workers=8) as ex:
        estados = list(ex.map(lambda _: tarea(), range(20)))

    # Exactamente una 'creada' y el resto 'sin_cambios', sin sqlite3.IntegrityError
    assert estados.count("creada") == 1
    assert estados.count("sin_cambios") == 19
    decisiones = almacen.listar()
    assert len(decisiones) == 1
