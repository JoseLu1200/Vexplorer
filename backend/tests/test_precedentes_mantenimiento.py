from __future__ import annotations

import hashlib
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.precedentes import mantenimiento
from backend.app.precedentes.api_embeddings import crear_router_embeddings
from backend.app.precedentes.comun import PREFIJO_API
from backend.app.precedentes.espacio import AlmacenEspacio
from backend.app.precedentes.mantenimiento import (
    VARIABLE_REGENERACION_AUTO,
    CandadoPerdido,
    CandadoPersistente,
    IntervaloNoCumplido,
    OperacionEnCurso,
    RegistroEspacio,
)
from backend.app.precedentes.regeneracion import estado_vector
from backend.app.semantic.embeddings import EmbeddingResult

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "planos_demo" / "estanteria_montada.dxf"
REGENERAR = f"{PREFIJO_API}/embeddings/regenerar"
VERIFICAR = f"{PREFIJO_API}/embeddings/espacio/verificar"
ROTAR = f"{PREFIJO_API}/embeddings/espacio/rotar"
MANTENIMIENTO = f"{PREFIJO_API}/embeddings/mantenimiento"
RELOJ = "2026-11-14T00:00:00+00:00"


class RelojFalso:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


# ---------------------------------------------------------------- candado persistente


def test_solo_un_hilo_adquiere_el_candado(tmp_path: Path) -> None:
    ruta = tmp_path / "espacio.sqlite3"
    hilos = 8
    barrera = threading.Barrier(hilos)
    resultados: list[str] = []
    mutex = threading.Lock()
    todos_intentaron = threading.Event()
    intentos = [0]

    def trabajo() -> None:
        candado = CandadoPersistente(ruta)  # conexión propia por hilo, como un proceso distinto
        barrera.wait(5)
        try:
            with candado.ocupar("regeneracion", 30):
                with mutex:
                    resultados.append("adquirido")
                    intentos[0] += 1
                # el titular espera a que los demás hayan intentado
                todos_intentaron.wait(5)
        except OperacionEnCurso:
            with mutex:
                resultados.append("ocupado")
                intentos[0] += 1
                if intentos[0] == hilos:
                    todos_intentaron.set()

    pool = [threading.Thread(target=trabajo) for _ in range(hilos)]
    for hilo in pool:
        hilo.start()
    for hilo in pool:
        hilo.join(10)
    assert resultados.count("adquirido") == 1
    assert resultados.count("ocupado") == hilos - 1


SCRIPT_PROCESO = """
import sys, time
from pathlib import Path
from backend.app.precedentes.mantenimiento import CandadoPersistente, OperacionEnCurso
ruta, inicio = Path(sys.argv[1]), float(sys.argv[2])
candado = CandadoPersistente(ruta)
while time.time() < inicio:
    time.sleep(0.005)
try:
    with candado.ocupar('regeneracion', 60):
        print('ADQUIRIDO', flush=True)
        time.sleep(3.0)
except OperacionEnCurso:
    print('OCUPADO', flush=True)
"""


def test_solo_un_proceso_adquiere_el_candado(tmp_path: Path) -> None:
    ruta = tmp_path / "espacio.sqlite3"
    CandadoPersistente(ruta)  # crea el esquema antes de lanzar procesos
    inicio = time.time() + 4.0
    procesos = [
        subprocess.Popen([sys.executable, "-c", SCRIPT_PROCESO, str(ruta), str(inicio)], cwd=ROOT, stdout=subprocess.PIPE, text=True)
        for _ in range(3)
    ]
    salidas = [proceso.communicate(timeout=60)[0].strip() for proceso in procesos]
    assert sorted(salidas) == ["ADQUIRIDO", "OCUPADO", "OCUPADO"]


def test_lease_expirado_se_readquiere_y_el_titular_viejo_no_lo_pisa(tmp_path: Path) -> None:
    reloj = RelojFalso()
    ruta = tmp_path / "espacio.sqlite3"
    a, b = CandadoPersistente(ruta, reloj), CandadoPersistente(ruta, reloj)
    caido = a.ocupar("regeneracion", 60)
    lease_a = caido.__enter__()  # un proceso que se cae y nunca libera
    with pytest.raises(OperacionEnCurso), b.ocupar("regeneracion", 60):
        pass
    reloj.t += 61
    with b.ocupar("regeneracion", 60) as lease_b:
        # el titular antiguo ya no puede renovar ni liberar el lease del nuevo
        with pytest.raises(CandadoPerdido):
            lease_a.renovar()
        caido.__exit__(None, None, None)
        assert a.estado("regeneracion").ocupado is True
        lease_b.renovar()
    assert a.estado("regeneracion").ocupado is False


def test_renovar_extiende_la_expiracion(tmp_path: Path) -> None:
    reloj = RelojFalso()
    ruta = tmp_path / "espacio.sqlite3"
    a, b = CandadoPersistente(ruta, reloj), CandadoPersistente(ruta, reloj)
    with a.ocupar("regeneracion", 60) as lease:
        reloj.t += 50
        lease.renovar()
        reloj.t += 50  # pasada la expiración original, pero renovado
        with pytest.raises(OperacionEnCurso), b.ocupar("regeneracion", 60):
            pass


def test_intervalo_minimo_persiste_entre_instancias(tmp_path: Path) -> None:
    reloj = RelojFalso()
    ruta = tmp_path / "espacio.sqlite3"
    with CandadoPersistente(ruta, reloj).ocupar("espacio", 60, intervalo_minimo_s=60):
        pass
    reloj.t += 10
    otra = CandadoPersistente(ruta, reloj)  # otro proceso
    with pytest.raises(IntervaloNoCumplido) as info, otra.ocupar("espacio", 60, intervalo_minimo_s=60):
        pass
    assert info.value.espera_s == pytest.approx(50)
    # Una operación sin intervalo (regeneración) no se ve afectada, y las de otro nombre tampoco.
    with otra.ocupar("regeneracion", 60):
        pass
    reloj.t += 51
    with otra.ocupar("espacio", 60, intervalo_minimo_s=60):
        pass


def test_dos_routers_sobre_la_misma_bd_comparten_candado_e_intervalo(tmp_path: Path) -> None:
    dentro, soltar = threading.Event(), threading.Event()

    class Lento(ProveedorFalso):
        def embed(self, text: str) -> EmbeddingResult:
            dentro.set()
            soltar.wait(5)
            return super().embed(text)

    def cliente(proveedor, **kwargs) -> TestClient:
        app = FastAPI()
        app.include_router(crear_router_embeddings(SinBiblioteca(), proveedor, AlmacenEspacio(tmp_path / "precedentes_espacio.sqlite3"), ahora=lambda: RELOJ, **kwargs))
        return TestClient(app)

    uno, dos = cliente(Lento()), cliente(ProveedorFalso())  # dos "workers"
    respuestas = []
    hilo = threading.Thread(target=lambda: respuestas.append(uno.post(VERIFICAR)))
    hilo.start()
    assert dentro.wait(5)
    ocupada = dos.post(VERIFICAR)
    soltar.set()
    hilo.join(5)
    assert ocupada.status_code == 409 and ocupada.json()["error"]["code"] == "operacion_en_curso"
    assert respuestas[0].status_code == 200
    reciente = dos.post(VERIFICAR)  # el intervalo mínimo también se comparte entre procesos
    assert reciente.status_code == 429 and reciente.json()["error"]["code"] == "verificacion_reciente"


# ---------------------------------------------------------------- huella ligada al espacio


class ProveedorFalso:
    model = "modelo-falso"
    dimensions = 4

    def __init__(self) -> None:
        self.llamadas = 0
        self.deriva = 0.0

    def embed(self, text: str) -> EmbeddingResult:
        self.llamadas += 1
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = [1.0 + digest[index] / 255 for index in range(4)]
        vector[0] += self.deriva
        return EmbeddingResult(vector=tuple(vector), model=self.model, dimensions=4)


class SinBiblioteca:
    def get_library_items(self):
        return ()


def _entorno(tmp_path: Path, monkeypatch, proveedor: ProveedorFalso | None = None):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv(VARIABLE_REGENERACION_AUTO, raising=False)
    proveedor = proveedor or ProveedorFalso()
    aplicacion = create_app(data_dir=tmp_path, embedding_provider=proveedor)
    router = FastAPI()
    router.include_router(crear_router_embeddings(aplicacion.state.repository, proveedor, AlmacenEspacio(tmp_path / "precedentes_espacio.sqlite3"), ahora=lambda: RELOJ, intervalo_minimo_verificacion_s=0))
    return TestClient(aplicacion), TestClient(router), aplicacion.state.repository, proveedor


def _run_revisado(cliente: TestClient, etiqueta: str) -> str:
    with FIXTURE.open("rb") as stream:
        document_id = cliente.post("/api/v1/documents", files={"file": (f"{etiqueta}.dxf", stream, "application/dxf")}).json()["data"]["document_id"]
    creado = cliente.post("/api/v1/runs", json={"document_id": document_id, "mode": "geometry_only"}).json()["data"]
    run_id = creado["run"]["id"]
    escenario = creado["result"]["scenarios"][0]["id"]
    assert cliente.post(f"/api/v1/runs/{run_id}/reviews", json={"base_result_revision": 1, "reviewer_name": "Técnica", "scenario_id": escenario, "confirmed_thickness_mm": 18, "material": "tablero", "finish": "melamina", "notes": "ok"}).status_code == 201
    return run_id


def _guardar(principal: TestClient, run_id: str, revision: int = 2, modo: str = "openai"):
    respuesta = principal.post(f"/api/v1/runs/{run_id}/library", json={"result_revision": revision, "label": f"et-{run_id}", "embedding_mode": modo})
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["data"]


def _obsoletos(router: TestClient, **extra) -> list[dict]:
    return router.post(REGENERAR, json=extra).json()["data"]["elementos"]


def test_deriva_rotacion_marca_obsoleto_y_la_regeneracion_no_reutiliza_la_cache(tmp_path: Path, monkeypatch) -> None:
    principal, router, repositorio, proveedor = _entorno(tmp_path, monkeypatch)
    assert router.post(VERIFICAR).json()["data"]["estado"] == "referencia_creada"
    run_id = _run_revisado(principal, "a")
    guardado = _guardar(principal, run_id)
    assert guardado["embedding"]["status"] == "generated"
    assert _obsoletos(router) == []  # sellado con la referencia vigente al guardar

    metadatos = repositorio.get_library_item(run_id).embedding
    antes = repositorio.get_embedding(metadatos.cache_key, metadatos.model, metadatos.dimensions, metadatos.descriptor_version)
    proveedor.deriva = 0.5
    assert router.post(ROTAR).status_code == 200
    [elemento] = _obsoletos(router)
    assert elemento["motivos"] == ["huella_retirada"] and elemento["estado"] == "pendiente"

    llamadas = proveedor.llamadas
    [regenerado] = _obsoletos(router, simular=False)
    assert regenerado["estado"] == "regenerado"  # no "de_cache": la cache tiene el vector del espacio retirado
    assert proveedor.llamadas == llamadas + 1
    despues = repositorio.get_embedding(metadatos.cache_key, metadatos.model, metadatos.dimensions, metadatos.descriptor_version)
    assert despues != antes
    assert _obsoletos(router) == []
    assert _obsoletos(router, simular=False) == []


def test_embedding_sin_huella_no_se_marca_salvo_peticion_explicita(tmp_path: Path, monkeypatch) -> None:
    principal, router, repositorio, _ = _entorno(tmp_path, monkeypatch)
    run_id = _run_revisado(principal, "a")
    _guardar(principal, run_id)  # aún no hay referencia: no se puede sellar
    assert RegistroEspacio(AlmacenEspacio(tmp_path / "precedentes_espacio.sqlite3")).sello(repositorio.get_library_item(run_id).embedding.cache_key) is None
    router.post(VERIFICAR)  # ahora existe referencia
    assert _obsoletos(router) == []
    [elemento] = _obsoletos(router, incluir_sin_huella=True)
    assert elemento["motivos"] == ["huella_desconocida"]
    [regenerado] = _obsoletos(router, simular=False, incluir_sin_huella=True)
    assert regenerado["estado"] == "regenerado"
    assert _obsoletos(router, incluir_sin_huella=True) == []


def test_identidad_del_espacio_incluye_descriptor_version(tmp_path: Path, monkeypatch) -> None:
    principal, _, repositorio, _ = _entorno(tmp_path, monkeypatch)
    run_id = _run_revisado(principal, "a")
    _guardar(principal, run_id)
    elemento = repositorio.get_library_item(run_id)
    assert estado_vector(repositorio, elemento) == "ok"
    ajeno = elemento.model_copy(update={"embedding": elemento.embedding.model_copy(update={"descriptor_version": "furniture-v3"})})
    assert estado_vector(repositorio, ajeno) == "espacio_distinto"


# ---------------------------------------------------------------- enganche tras guardar


def _contar(proveedor: ProveedorFalso, accion):
    antes = proveedor.llamadas
    resultado = accion()
    return resultado, proveedor.llamadas - antes


def test_reemplazo_de_revision_marca_el_embedding_anterior(tmp_path: Path, monkeypatch) -> None:
    principal, router, _, _ = _entorno(tmp_path, monkeypatch)
    run_id = _run_revisado(principal, "a")
    primero = _guardar(principal, run_id, revision=1)["embedding"]["cache_key"]
    segundo = _guardar(principal, run_id, revision=2)["embedding"]["cache_key"]
    reemplazados = router.get(MANTENIMIENTO).json()["data"]["reemplazados"]
    if primero != segundo:
        assert [(r["cache_key"], r["library_item_id"], r["motivo"]) for r in reemplazados] == [(primero, f"library-{run_id}", "revision_reemplazada")]
    else:
        assert reemplazados == []
    _guardar(principal, run_id, revision=2)  # misma clave: no se marca nada nuevo
    assert len(router.get(MANTENIMIENTO).json()["data"]["reemplazados"]) == len(reemplazados)


def _preparar_cache_retirada(principal, router, proveedor, monkeypatch):
    """Referencia H1, run A guardado y sellado con H1, rotación a H2: la cache de A queda en el espacio retirado."""
    router.post(VERIFICAR)
    run_a = _run_revisado(principal, "a")
    _guardar(principal, run_a)
    proveedor.deriva = 0.5
    assert router.post(ROTAR).status_code == 200
    assert [item["motivos"] for item in _obsoletos(router)] == [["huella_retirada"]]
    return run_a, _run_revisado(principal, "b")


def test_regeneracion_tras_guardar_desactivada_por_defecto_no_llama_al_proveedor(tmp_path: Path, monkeypatch) -> None:
    principal, router, _, proveedor = _entorno(tmp_path, monkeypatch)
    _, run_b = _preparar_cache_retirada(principal, router, proveedor, monkeypatch)
    monkeypatch.setattr(mantenimiento, "_encolar", lambda tarea: tarea())
    guardado, llamadas = _contar(proveedor, lambda: _guardar(principal, run_b))
    assert guardado["embedding"]["status"] == "cache" and llamadas == 0
    assert len(_obsoletos(router)) == 2  # A y B siguen apuntando a la cache retirada


def test_regeneracion_tras_guardar_activada_regenera_solo_ese_elemento(tmp_path: Path, monkeypatch) -> None:
    principal, router, repositorio, proveedor = _entorno(tmp_path, monkeypatch)
    _, run_b = _preparar_cache_retirada(principal, router, proveedor, monkeypatch)
    monkeypatch.setenv(VARIABLE_REGENERACION_AUTO, "1")
    monkeypatch.setattr(mantenimiento, "_encolar", lambda tarea: tarea())
    guardado, llamadas = _contar(proveedor, lambda: _guardar(principal, run_b))
    assert guardado["embedding"]["status"] == "cache"
    assert llamadas == 1
    # A y B comparten cache_key: al sobrescribirla con el espacio vigente ambos quedan al día.
    assert _obsoletos(router) == []
    assert repositorio.get_library_item(run_b).embedding is not None


def test_regeneracion_tras_guardar_se_salta_si_el_candado_esta_ocupado(tmp_path: Path, monkeypatch) -> None:
    principal, router, _, proveedor = _entorno(tmp_path, monkeypatch)
    _, run_b = _preparar_cache_retirada(principal, router, proveedor, monkeypatch)
    monkeypatch.setenv(VARIABLE_REGENERACION_AUTO, "1")
    monkeypatch.setattr(mantenimiento, "_encolar", lambda tarea: tarea())
    with CandadoPersistente(tmp_path / "precedentes_espacio.sqlite3").ocupar("regeneracion", 60):
        guardado, llamadas = _contar(proveedor, lambda: _guardar(principal, run_b))
    assert guardado["embedding"] is not None and llamadas == 0


def test_regeneracion_tras_guardar_no_bloquea_la_respuesta(tmp_path: Path, monkeypatch) -> None:
    principal, router, _, proveedor = _entorno(tmp_path, monkeypatch)
    _, run_b = _preparar_cache_retirada(principal, router, proveedor, monkeypatch)
    monkeypatch.setenv(VARIABLE_REGENERACION_AUTO, "1")
    dentro, soltar = threading.Event(), threading.Event()
    embed = proveedor.embed

    def lento(texto: str) -> EmbeddingResult:
        dentro.set()
        soltar.wait(10)
        return embed(texto)

    monkeypatch.setattr(proveedor, "embed", lento)
    _guardar(principal, run_b)  # vuelve aunque la regeneración siga en curso
    assert dentro.wait(10)
    assert router.get(MANTENIMIENTO).json()["data"]["candados"]["regeneracion"]["ocupado"] is True
    soltar.set()
    mantenimiento.esperar_pendientes(10)
    assert router.get(MANTENIMIENTO).json()["data"]["candados"]["regeneracion"]["ocupado"] is False
    assert _obsoletos(router) == []


def test_guardado_en_modo_offline_no_toca_el_proveedor(tmp_path: Path, monkeypatch) -> None:
    principal, router, _, proveedor = _entorno(tmp_path, monkeypatch)
    _, run_b = _preparar_cache_retirada(principal, router, proveedor, monkeypatch)
    monkeypatch.setenv(VARIABLE_REGENERACION_AUTO, "1")
    monkeypatch.setattr(mantenimiento, "_encolar", lambda tarea: tarea())
    guardado, llamadas = _contar(proveedor, lambda: _guardar(principal, run_b, modo="offline"))
    assert guardado["embedding"] is None and llamadas == 0


def test_un_fallo_del_enganche_no_cambia_la_respuesta_201(tmp_path: Path, monkeypatch) -> None:
    principal, _, _, _ = _entorno(tmp_path, monkeypatch)
    run_id = _run_revisado(principal, "a")

    def roto(self, *args, **kwargs):
        raise RuntimeError("bd corrupta")

    monkeypatch.setattr(RegistroEspacio, "registrar_guardado", roto)
    assert _guardar(principal, run_id)["run_id"] == run_id
