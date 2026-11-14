from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.contratos.modelos import (
    DescriptorDimensions,
    DescriptorPartFeature,
    FurnitureDescriptor,
    FurnitureDescriptorV2,
    LibraryItem,
    RoleQuantity,
)
from backend.app.precedentes.api_piezas import crear_router_piezas
from backend.app.precedentes.lotes import (
    ConfiguracionLotes,
    cabe_en_tablero,
    estimar_tableros,
    preparar_lotes,
)
from backend.app.precedentes.piezas import PiezaRef

RUTA = "/api/v1/precedentes/piezas/lotes"


def pieza(
    pedido: str,
    pid: str,
    largo: float | None = 1000,
    ancho: float | None = 500,
    espesor: float | None = 18,
    material: str | None = "Melamina",
    acabado: str | None = "mate",
    cantidad: int | None = 1,
) -> PiezaRef:
    return PiezaRef(
        origen_id=pedido,
        pieza_id=pid,
        largo_mm=largo,
        ancho_mm=ancho,
        espesor_mm=espesor,
        material=material,
        acabado=acabado,
        cantidad=cantidad,
        fuente="peticion",
    )


def item_v2(run_id: str) -> LibraryItem:
    return LibraryItem(
        id=f"lib-{run_id}",
        run_id=run_id,
        result_revision=1,
        label=run_id,
        descriptor=FurnitureDescriptorV2(
            family="rectangular_shelving",
            dimensions=DescriptorDimensions(),
            roles=(RoleQuantity(role="side", quantity=2),),
            structure="unknown",
            material="MELAMINA",
            finish="Mate",
            thicknesses_mm=(18.0,),
            classification_status="hypothesis",
            part_features=(
                DescriptorPartFeature(
                    length_mm=2000, width_mm=400, thickness_mm=18, quantity=2
                ),
            ),
            unknown_fields=(),
        ),
        descriptor_fingerprint="a" * 64,
        created_at="2026-01-01T00:00:00Z",
    )


def item_v1(run_id: str) -> LibraryItem:
    return LibraryItem(
        id=f"lib-{run_id}",
        run_id=run_id,
        result_revision=1,
        label=run_id,
        descriptor=FurnitureDescriptor(
            family="unknown",
            dimensions=DescriptorDimensions(),
            roles=(),
            structure="unknown",
            unknown_fields=(),
        ),
        descriptor_fingerprint="c" * 64,
        created_at="2026-01-01T00:00:00Z",
    )


class BibliotecaFalsa:
    def __init__(self, items: list[LibraryItem]) -> None:
        self.items = tuple(items)

    def get_library_items(self) -> tuple[LibraryItem, ...]:
        return self.items


def cliente(
    items: list[LibraryItem] | None = None, con_biblioteca: bool = True
) -> TestClient:
    app = FastAPI()
    fuente = BibliotecaFalsa(items or []) if con_biblioteca else None
    app.include_router(crear_router_piezas(fuente))
    return TestClient(app)


def test_agrupa_por_clave_exacta_entre_pedidos() -> None:
    piezas = [
        pieza("PED-1", "a", material="melamina", acabado=" MATE"),
        pieza("PED-2", "b"),
        pieza("PED-2", "c", espesor=19),
        pieza("PED-3", "d", acabado=None),
        pieza("PED-3", "e", acabado="brillo"),
    ]
    resultado = preparar_lotes(piezas, ConfiguracionLotes())
    claves = {
        (lote.clave.espesor_mm, lote.clave.material, lote.clave.acabado): lote
        for lote in resultado.lotes
    }
    assert set(claves) == {
        (18, "melamina", "mate"),
        (19, "melamina", "mate"),
        (18, "melamina", None),
        (18, "melamina", "brillo"),
    }
    assert claves[(18, "melamina", "mate")].pedidos == ("PED-1", "PED-2")


def test_sin_clasificar_nunca_se_mezcla() -> None:
    piezas = [
        pieza("P1", "ok"),
        pieza("P1", "sin-espesor", espesor=None),
        pieza("P2", "sin-material", material=None),
        pieza("P2", "sin-ancho", ancho=None),
    ]
    resultado = preparar_lotes(piezas, ConfiguracionLotes())
    assert len(resultado.lotes) == 1 and resultado.lotes[0].referencias == 1
    motivos = {s.pieza.pieza_id: s.motivo for s in resultado.sin_clasificar.piezas}
    assert motivos == {
        "sin-espesor": "espesor desconocido",
        "sin-material": "material desconocido",
        "sin-ancho": "ancho desconocido",
    }
    assert resultado.sin_clasificar.grupo == "sin_clasificar"


def test_cantidad_desconocida_no_entra_en_estimacion_de_tableros() -> None:
    piezas = [
        pieza("P1", "a", largo=2000, ancho=1000, cantidad=2),
        pieza("P2", "b", largo=1000, ancho=1000, cantidad=None),
    ]
    resultado = preparar_lotes(piezas, ConfiguracionLotes())
    lote = resultado.lotes[0]
    assert lote.superficie_m2 == 4.0
    assert lote.unidades == 2 and lote.unidades_con_cantidad_supuesta == 0
    assert lote.estimacion.es_estimacion is True and lote.estimacion.tableros == 2
    assert "nesting" in lote.estimacion.nota
    assert [(item.pieza.pieza_id, item.pieza.cantidad, item.motivo) for item in resultado.sin_clasificar.piezas] == [("b", None, "cantidad desconocida")]
    otra = ConfiguracionLotes(
        tablero_largo_mm=2500, tablero_ancho_mm=2000, aprovechamiento=1
    )
    assert preparar_lotes(piezas, otra).lotes[0].estimacion.tableros == 1


def test_estimacion_sin_ruido_flotante() -> None:
    config = ConfiguracionLotes(
        tablero_largo_mm=1000, tablero_ancho_mm=1000, aprovechamiento=0.7
    )
    assert estimar_tableros(0.7 * 1_000_000 * 3, config) == 3


def test_piezas_que_no_caben_con_giro() -> None:
    config = ConfiguracionLotes()
    assert cabe_en_tablero(1220, 2440, config)
    assert not cabe_en_tablero(2500, 600, config)
    assert not cabe_en_tablero(1300, 1300, config)
    piezas = [
        pieza("P1", "girable", largo=1000, ancho=2400),
        pieza("P1", "larga", largo=2600),
    ]
    lote = preparar_lotes(piezas, config).lotes[0]
    assert [p.pieza_id for p in lote.piezas_que_no_caben] == ["larga"]


def test_orden_determinista_por_superficie() -> None:
    piezas = [
        pieza("P1", "pequena", largo=100, ancho=100, material="B"),
        pieza("P2", "grande", largo=2000, ancho=1000, material="A"),
        pieza("P3", "media", largo=1000, ancho=500, material="C"),
    ]
    a = preparar_lotes(piezas, ConfiguracionLotes())
    b = preparar_lotes(list(reversed(piezas)), ConfiguracionLotes())
    assert a.model_dump() == b.model_dump()
    assert [lote.clave.material for lote in a.lotes] == ["a", "c", "b"]
    assert [lote.lote_id for lote in a.lotes] == ["lote-001", "lote-002", "lote-003"]


def test_endpoint_pedidos_y_runs() -> None:
    c = cliente([item_v2("run-1"), item_v1("run-v1")])
    respuesta = c.post(
        RUTA,
        json={
            "pedidos": [
                {
                    "pedido_id": "PED-1",
                    "piezas": [
                        {
                            "pieza_id": "a",
                            "largo_mm": 1000,
                            "ancho_mm": 500,
                            "espesor_mm": 18,
                            "material": "melamina",
                            "acabado": "mate",
                            "cantidad": 1,
                        }
                    ],
                }
            ],
            "run_ids": ["run-1", "run-v1"],
        },
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()["data"]
    assert len(datos["lotes"]) == 1
    lote = datos["lotes"][0]
    assert lote["pedidos"] == ["PED-1", "run-1"]
    assert lote["superficie_m2"] == 2.1
    assert datos["pedidos_sin_piezas"] == ["run-v1"]
    assert datos["origen_datos"] == {"peticion": 1, "biblioteca": 1, "historico": 0}


def test_endpoint_errores() -> None:
    c = cliente([item_v2("run-1")])
    assert c.post(RUTA, json={}).json()["error"]["code"] == "peticion_vacia"
    r = c.post(RUTA, json={"run_ids": ["no-existe"]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "run_no_encontrado"
    r = c.post(RUTA, json={"pedidos": [{"pedido_id": "run-1"}], "run_ids": ["run-1"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "pedido_duplicado"
    r = cliente(con_biblioteca=False).post(RUTA, json={"run_ids": ["run-1"]})
    assert r.status_code == 503
    assert c.post(RUTA, json={"pedidos": [], "aprovechamiento": 1.5}).status_code == 422


def test_endpoint_incluir_biblioteca_une_con_run_ids() -> None:
    c = cliente([item_v2("run-1"), item_v2("run-2"), item_v1("run-v1")])
    r = c.post(RUTA, json={"run_ids": ["run-1"], "incluir_biblioteca": True})
    assert r.status_code == 200
    datos = r.json()["data"]
    assert datos["pedidos"] == ["run-1", "run-2", "run-v1"]
    assert datos["lotes"][0]["unidades"] == 4
    assert datos["pedidos_sin_piezas"] == ["run-v1"]
    r = c.post(
        RUTA, json={"pedidos": [{"pedido_id": "run-2"}], "incluir_biblioteca": True}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "pedido_duplicado"


def test_total_de_piezas_limitado_antes_de_validar() -> None:
    pieza_cruda = {"pieza_id": "x"}
    pedidos = [{"pedido_id": f"P{i}", "piezas": [pieza_cruda] * 1500} for i in range(2)]
    r = cliente().post(RUTA, json={"pedidos": pedidos})
    assert r.status_code == 422
    demasiados = [{"pedido_id": f"P{i}"} for i in range(201)]
    assert cliente().post(RUTA, json={"pedidos": demasiados}).status_code == 422
