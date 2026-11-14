from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.contratos.modelos import (
    DescriptorDimensions,
    DescriptorPartFeature,
    FurnitureDescriptor,
    FurnitureDescriptorV2,
    FurnitureDescriptorV3,
    LibraryItem,
    RoleQuantity,
    TableDescriptorComponentFeature,
)
from backend.app.historico.models import HistoricalRecord
from backend.app.precedentes.api_piezas import crear_router_piezas
from backend.app.precedentes.gemelas import (
    ConfiguracionGemelas,
    GrupoGemelas,
    detectar_gemelas,
)
from backend.app.precedentes.piezas import (
    LIMITE_PIEZAS,
    PiezaRef,
    piezas_desde_biblioteca,
    piezas_desde_item_biblioteca,
    piezas_desde_registro_historico,
)

RUTA = "/api/v1/precedentes/piezas/gemelas"


def pieza(
    origen: str,
    pid: str,
    largo: float,
    ancho: float,
    espesor: float | None = 18,
    material: str | None = "Melamina blanca",
    cantidad: int | None = 1,
) -> PiezaRef:
    return PiezaRef(
        origen_id=origen,
        pieza_id=pid,
        largo_mm=largo,
        ancho_mm=ancho,
        espesor_mm=espesor,
        material=material,
        cantidad=cantidad,
        fuente="peticion",
    )


def item_v2(run_id: str, partes: list[tuple[float, float, float, int]]) -> LibraryItem:
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
            material="Melamina blanca",
            finish="mate",
            thicknesses_mm=(18.0,),
            classification_status="hypothesis",
            part_features=tuple(
                DescriptorPartFeature(
                    length_mm=lg, width_mm=an, thickness_mm=es, quantity=q
                )
                for lg, an, es, q in partes
            ),
            unknown_fields=(),
        ),
        descriptor_fingerprint="a" * 64,
        created_at="2026-01-01T00:00:00Z",
    )


def item_v3(run_id: str) -> LibraryItem:
    estados = {
        "quantity": "calculated",
        "length_mm": "calculated",
        "width_mm": "calculated",
        "thickness_mm": "calculated",
    }
    return LibraryItem(
        id=f"lib-{run_id}",
        run_id=run_id,
        result_revision=1,
        label=run_id,
        descriptor=FurnitureDescriptorV3(
            dimensions=DescriptorDimensions(),
            structure="side_support_table",
            components=(
                TableDescriptorComponentFeature(
                    role="tabletop",
                    quantity=1,
                    length_mm=1200,
                    width_mm=800,
                    thickness_mm=25,
                    field_states=estados,
                ),
            ),
            material_tariff_id="TAR-ROBLE",
        ),
        descriptor_fingerprint="b" * 64,
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


def ids_grupo(grupo: GrupoGemelas) -> set[str]:
    return {m.pieza.pieza_id for m in grupo.miembros}


def test_cadena_a_b_c_no_encadena() -> None:
    # A≈B y B≈C (±3), pero A y C están a 6 mm: nunca deben compartir grupo.
    piezas = [
        pieza("P1", "A", 800, 400),
        pieza("P2", "B", 803, 400),
        pieza("P3", "C", 806, 400),
    ]
    resultado = detectar_gemelas(piezas, ConfiguracionGemelas())
    assert resultado.grupos
    for grupo in resultado.grupos:
        assert not {"A", "C"} <= ids_grupo(grupo)
    assert ids_grupo(resultado.grupos[0]) == {"A", "B"}


def test_miembros_en_tolerancia_entre_si_y_del_estandar() -> None:
    piezas = [pieza(f"P{i}", f"x{i}", 800 + i, 400 + (i % 3)) for i in range(10)]
    resultado = detectar_gemelas(piezas, ConfiguracionGemelas())
    assert resultado.grupos
    for grupo in resultado.grupos:
        for a in grupo.miembros:
            assert abs(a.desviacion_largo_mm) <= 3 and abs(a.desviacion_ancho_mm) <= 3
            for b in grupo.miembros:
                assert abs(a.largo_orientado_mm - b.largo_orientado_mm) <= 3
                assert abs(a.ancho_orientado_mm - b.ancho_orientado_mm) <= 3


def test_estandar_mas_frecuente_ponderado_y_ahorro() -> None:
    piezas = [
        pieza("P1", "a", 800, 400, cantidad=1),
        pieza("P2", "b", 802, 400, cantidad=4),
        pieza("P3", "c", 801, 401, cantidad=2),
    ]
    grupo = detectar_gemelas(piezas, ConfiguracionGemelas()).grupos[0]
    assert (grupo.medida_estandar.largo_mm, grupo.medida_estandar.ancho_mm) == (
        802,
        400,
    )
    assert grupo.referencias_actuales == 3 and grupo.ahorro_referencias == 2
    assert grupo.unidades == 7
    desviaciones = {
        m.pieza.pieza_id: (m.desviacion_largo_mm, m.desviacion_ancho_mm)
        for m in grupo.miembros
    }
    assert desviaciones == {"a": (-2, 0), "b": (0, 0), "c": (-1, 1)}


def test_empate_de_frecuencia_elige_la_mayor() -> None:
    piezas = [pieza("P1", "a", 800, 400), pieza("P2", "b", 802, 400)]
    grupo = detectar_gemelas(piezas, ConfiguracionGemelas()).grupos[0]
    assert grupo.medida_estandar.largo_mm == 802


def test_exige_dos_origenes_distintos() -> None:
    piezas = [pieza("P1", "a", 800, 400), pieza("P1", "b", 802, 400)]
    assert detectar_gemelas(piezas, ConfiguracionGemelas()).grupos == ()


def test_medidas_identicas_no_proponen_nada() -> None:
    piezas = [pieza("P1", "a", 800, 400), pieza("P2", "b", 800, 400)]
    assert detectar_gemelas(piezas, ConfiguracionGemelas()).grupos == ()


def test_espesor_y_material_exactos_none_descartado() -> None:
    piezas = [
        pieza("P1", "a", 800, 400, material=" melamina  BLANCA "),
        pieza("P2", "b", 802, 400),
        pieza("P3", "c", 801, 400, espesor=19),
        pieza("P4", "d", 801, 400, material="Roble"),
        pieza("P5", "e", 801, 400, material=None),
        pieza("P6", "f", 801, 400, espesor=None),
    ]
    resultado = detectar_gemelas(piezas, ConfiguracionGemelas())
    assert len(resultado.grupos) == 1
    assert ids_grupo(resultado.grupos[0]) == {"a", "b"}
    assert {d.pieza_id for d in resultado.piezas_descartadas} == {"e", "f"}


def test_tolerancia_configurable() -> None:
    piezas = [pieza("P1", "a", 800, 400), pieza("P2", "b", 805, 400)]
    assert detectar_gemelas(piezas, ConfiguracionGemelas()).grupos == ()
    amplia = ConfiguracionGemelas(tolerancia_largo_mm=5)
    assert len(detectar_gemelas(piezas, amplia).grupos) == 1


def test_giro_desactivado_por_defecto() -> None:
    piezas = [pieza("P1", "a", 800, 400), pieza("P2", "b", 401, 801)]
    assert detectar_gemelas(piezas, ConfiguracionGemelas()).grupos == ()
    con_giro = detectar_gemelas(piezas, ConfiguracionGemelas(permitir_giro=True))
    assert len(con_giro.grupos) == 1
    giradas = {m.pieza.pieza_id: m.girada for m in con_giro.grupos[0].miembros}
    assert giradas == {"a": False, "b": True}


def test_determinista_independiente_del_orden() -> None:
    piezas = [
        pieza(f"P{i % 4}", f"x{i}", 800 + (i * 7) % 11, 400 + (i * 3) % 5)
        for i in range(20)
    ]
    a = detectar_gemelas(piezas, ConfiguracionGemelas())
    b = detectar_gemelas(list(reversed(piezas)), ConfiguracionGemelas())
    assert a.model_dump() == b.model_dump()
    assert a.grupos


def test_extraccion_desde_fuentes() -> None:
    assert piezas_desde_item_biblioteca(item_v1("r1")) == ()
    v2 = piezas_desde_item_biblioteca(item_v2("r2", [(800, 400, 18, 2)]))
    assert (v2[0].origen_id, v2[0].fuente, v2[0].acabado, v2[0].cantidad) == (
        "r2",
        "biblioteca",
        "mate",
        2,
    )
    v3 = piezas_desde_item_biblioteca(item_v3("r3"))
    assert v3[0].material == "tarifa:TAR-ROBLE" and v3[0].espesor_mm == 25
    registro = HistoricalRecord.model_validate(
        {
            "record_id": "rec1",
            "project_id": "proy1",
            "revision": "1",
            "origin": "synthetic",
            "manufacturing_hours": 2.0,
            "hours_scope": ["fabricacion"],
            "included_scope": ["fabricacion"],
            "provenance": {"source": "test", "source_date": "2026-01-01"},
            "components": [
                {
                    "component_id": "c1",
                    "length_mm": 500,
                    "width_mm": 300,
                    "thickness_mm": 16,
                    "material": "MDF",
                }
            ],
        }
    )
    historico = piezas_desde_registro_historico(registro)
    assert historico[0].origen_id == "proy1" and historico[0].pieza_id == "rec1:c1"
    assert historico[0].fuente == "historico"


def test_endpoint_con_biblioteca() -> None:
    c = cliente([item_v2("run-1", [(800, 400, 18, 1)]), item_v1("run-0")])
    respuesta = c.post(
        RUTA,
        json={
            "piezas": [
                {
                    "origen_id": "pedido-9",
                    "pieza_id": "p1",
                    "largo_mm": 802,
                    "ancho_mm": 400,
                    "espesor_mm": 18,
                    "material": "melamina blanca",
                    "cantidad": 3,
                }
            ],
            "incluir_biblioteca": True,
        },
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()["data"]
    assert datos["origen_datos"] == {"peticion": 1, "biblioteca": 1, "historico": 0}
    grupo = datos["grupos"][0]
    assert grupo["origenes"] == ["pedido-9", "run-1"]
    assert grupo["medida_estandar"]["largo_mm"] == 802
    assert grupo["grupo_id"] == "gemelas-001"


def test_endpoint_errores() -> None:
    c = cliente()
    r = c.post(RUTA, json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "sin_piezas"
    dup = {"origen_id": "o", "pieza_id": "p", "largo_mm": 1, "ancho_mm": 1}
    r = c.post(RUTA, json={"piezas": [dup, dup]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "pieza_duplicada"
    r = cliente(con_biblioteca=False).post(RUTA, json={"incluir_biblioteca": True})
    assert (
        r.status_code == 503 and r.json()["error"]["code"] == "biblioteca_no_disponible"
    )
    # La fuente no la declara el cliente.
    assert (
        c.post(RUTA, json={"piezas": [{**dup, "fuente": "biblioteca"}]}).status_code
        == 422
    )


def test_material_tarifa_v3_no_se_mezcla_con_nombre_v2() -> None:
    # Un nombre de material V2 igual al id de tarifa V3 no debe compartir clave.
    v2 = item_v2("r2", [(1201, 800, 25, 1)])
    v2 = v2.model_copy(
        update={
            "descriptor": v2.descriptor.model_copy(update={"material": "TAR-ROBLE"})
        }
    )
    piezas = piezas_desde_biblioteca([v2, item_v3("r3")])
    assert {p.material for p in piezas} == {"TAR-ROBLE", "tarifa:TAR-ROBLE"}
    assert detectar_gemelas(piezas, ConfiguracionGemelas()).grupos == ()


def test_tolerancia_maxima_validada() -> None:
    with pytest.raises(ValidationError):
        ConfiguracionGemelas(tolerancia_largo_mm=51)
    r = cliente().post(
        RUTA,
        json={
            "piezas": [
                {"origen_id": "o", "pieza_id": "p", "largo_mm": 1, "ancho_mm": 1}
            ],
            "tolerancia_largo_mm": 1000,
        },
    )
    assert r.status_code == 422


def _peor_caso_separado(n: int) -> list[PiezaRef]:
    # Pares de dos orígenes, anchos separados más que la tolerancia, largos
    # dentro de la tolerancia máxima y cantidad creciente con el largo.
    return [
        pieza(
            f"O{i % 2}",
            f"p{i:04d}",
            1000 + (i // 2) * 0.02 + (i % 2) * 0.01,
            200 + (i // 2) * 100,
            cantidad=1 + i // 2,
        )
        for i in range(n)
    ]


def _peor_caso_encadenado(n: int) -> list[PiezaRef]:
    # Anchos encadenados (paso < tolerancia): la partición por huecos no ayuda.
    return [
        pieza(
            f"O{i % 2}",
            f"p{i:04d}",
            1000 + (i // 2) * 0.02 + (i % 2) * 0.01,
            200 + (i // 2) * 30,
            cantidad=1 + i // 2,
        )
        for i in range(n)
    ]


@pytest.mark.parametrize("generador", [_peor_caso_separado, _peor_caso_encadenado])
def test_rendimiento_peor_caso_acotado(generador) -> None:
    piezas = generador(LIMITE_PIEZAS)
    config = ConfiguracionGemelas(tolerancia_largo_mm=50, tolerancia_ancho_mm=50)
    inicio = time.perf_counter()
    resultado = detectar_gemelas(piezas, config)
    assert time.perf_counter() - inicio < 10
    evaluadas = {m.pieza.pieza_id for g in resultado.grupos for m in g.miembros}
    no_evaluadas = {p.pieza_id for p in resultado.piezas_no_evaluadas}
    assert not evaluadas & no_evaluadas
    assert resultado.parcial == bool(no_evaluadas)
    for grupo in resultado.grupos:
        largos = [m.largo_orientado_mm for m in grupo.miembros]
        anchos = [m.ancho_orientado_mm for m in grupo.miembros]
        assert max(largos) - min(largos) <= 50 and max(anchos) - min(anchos) <= 50


def test_presupuesto_agotado_marca_parcial() -> None:
    piezas = _peor_caso_encadenado(60)
    config = ConfiguracionGemelas(tolerancia_largo_mm=50, tolerancia_ancho_mm=50)
    completo = detectar_gemelas(piezas, config)
    assert completo.parcial is False and completo.piezas_no_evaluadas == ()
    parcial = detectar_gemelas(piezas, config, presupuesto_trabajo=100)
    assert parcial.parcial is True and parcial.piezas_no_evaluadas
    assert {p.motivo for p in parcial.piezas_no_evaluadas} == {
        "presupuesto de cálculo agotado"
    }
