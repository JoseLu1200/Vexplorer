"""Nesting real por guillotina de los lotes de corte (idea 3.1)."""

from __future__ import annotations

import itertools
import random
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.contratos.modelos import (
    DescriptorDimensions,
    DescriptorPartFeature,
    FurnitureDescriptorV2,
    LibraryItem,
    RoleQuantity,
)
from backend.app.precedentes.api_piezas import crear_router_piezas
from backend.app.precedentes.lotes import (
    LIMITE_OCURRENCIAS_TOTAL,
    ConfiguracionLotes,
    preparar_lotes,
)
from backend.app.precedentes.nesting import (
    LIMITE_OCURRENCIAS,
    DemasiadasOcurrencias,
    ParametrosNesting,
    ResultadoNesting,
    nestear,
)
from backend.app.precedentes.piezas import PiezaRef

RUTA = "/api/v1/precedentes/piezas/lotes"
EPS = 1e-6


def pieza(
    pid: str,
    largo: float | None = 1000,
    ancho: float | None = 500,
    cantidad: int | None = 1,
    rotable: bool = True,
    pedido: str = "P1",
    espesor: float | None = 18,
    material: str | None = "melamina",
) -> PiezaRef:
    return PiezaRef(
        origen_id=pedido,
        pieza_id=pid,
        largo_mm=largo,
        ancho_mm=ancho,
        espesor_mm=espesor,
        cantidad=cantidad,
        material=material,
        acabado=None,
        rotable=rotable,
        fuente="peticion",
    )


def sin_kerf(**extra: object) -> ParametrosNesting:
    return ParametrosNesting(kerf_mm=0, margen_mm=0, **extra)  # type: ignore[arg-type]


def comprobar_geometria(
    resultado: ResultadoNesting,
    piezas: list[PiezaRef],
    parametros: ParametrosNesting,
) -> None:
    """Comprobación independiente del algoritmo: dentro del área útil, sin solapes, con kerf."""
    por_clave = {(p.origen_id, p.pieza_id): p for p in piezas}
    m, k = parametros.margen_mm, parametros.kerf_mm
    tl, ta = parametros.tablero_largo_mm, parametros.tablero_ancho_mm
    por_tablero: dict[int, list] = {}
    vistas: set[tuple[str, str, int]] = set()
    for c in resultado.colocaciones:
        original = por_clave[(c.origen_id, c.pieza_id)]
        largo, ancho = original.largo_mm, original.ancho_mm
        esperado = (ancho, largo) if c.rotada else (largo, ancho)
        assert (c.ancho_mm, c.alto_mm) == esperado
        if c.rotada:
            assert parametros.permitir_rotacion and original.rotable
        assert c.x_mm >= m - EPS and c.y_mm >= m - EPS
        assert c.x_mm + c.ancho_mm <= tl - m + EPS
        assert c.y_mm + c.alto_mm <= ta - m + EPS
        clave = (c.origen_id, c.pieza_id, c.ocurrencia)
        assert clave not in vistas
        vistas.add(clave)
        assert 1 <= c.tablero <= resultado.tableros
        por_tablero.setdefault(c.tablero, []).append(c)
    for colocaciones in por_tablero.values():
        for a, b in itertools.combinations(colocaciones, 2):
            hueco_x = max(
                a.x_mm - (b.x_mm + b.ancho_mm), b.x_mm - (a.x_mm + a.ancho_mm)
            )
            hueco_y = max(a.y_mm - (b.y_mm + b.alto_mm), b.y_mm - (a.y_mm + a.alto_mm))
            assert hueco_x >= k - EPS or hueco_y >= k - EPS, (a, b)
    assert len(resultado.tableros_detalle) == resultado.tableros
    area_tablero = tl * ta
    for detalle in resultado.tableros_detalle:
        area = sum(c.ancho_mm * c.alto_mm for c in por_tablero.get(detalle.tablero, []))
        assert detalle.aprovechamiento == pytest.approx(area / area_tablero, abs=1e-5)
        assert detalle.piezas == len(por_tablero.get(detalle.tablero, []))
    if resultado.tableros:
        total = sum(c.ancho_mm * c.alto_mm for c in resultado.colocaciones)
        assert resultado.aprovechamiento_total == pytest.approx(
            total / (resultado.tableros * area_tablero), abs=1e-5
        )


def test_pieza_del_tamano_exacto_del_tablero() -> None:
    parametros = sin_kerf()
    piezas = [pieza("a", largo=2440, ancho=1220)]
    r = nestear(piezas, parametros)
    assert r.tableros == 1 and len(r.colocaciones) == 1 and not r.no_colocadas
    c = r.colocaciones[0]
    assert (c.x_mm, c.y_mm, c.ancho_mm, c.alto_mm, c.rotada) == (
        0,
        0,
        2440,
        1220,
        False,
    )
    assert r.aprovechamiento_total == 1.0
    assert r.tableros_detalle[0].aprovechamiento == 1.0
    comprobar_geometria(r, piezas, parametros)


def test_kerf_obliga_a_un_segundo_tablero() -> None:
    piezas = [pieza("a", largo=1220, ancho=1220, cantidad=2)]
    sin = sin_kerf()
    assert nestear(piezas, sin).tableros == 1
    con = ParametrosNesting(kerf_mm=3, margen_mm=0)
    r = nestear(piezas, con)
    assert r.tableros == 2
    comprobar_geometria(r, piezas, con)


def test_kerf_se_respeta_entre_piezas_que_caben() -> None:
    # 1000 + 3 + 1000 cabe en 2440; con kerf 3 la separación debe verse en las coordenadas.
    parametros = ParametrosNesting(kerf_mm=3, margen_mm=0)
    piezas = [pieza("a", largo=1000, ancho=1220, cantidad=2)]
    r = nestear(piezas, parametros)
    assert r.tableros == 1
    xs = sorted(c.x_mm for c in r.colocaciones)
    assert xs[1] - xs[0] >= 1003 - EPS
    comprobar_geometria(r, piezas, parametros)


def test_margen_reduce_el_area_util() -> None:
    parametros = ParametrosNesting(kerf_mm=0, margen_mm=10)
    piezas = [pieza("a", largo=2440, ancho=1220)]
    r = nestear(piezas, parametros)
    assert r.tableros == 0 and r.colocaciones == ()
    assert [n.pieza_id for n in r.no_colocadas] == ["a"]
    assert r.no_colocadas[0].motivo == "mas_grande_que_el_area_util"
    justa = [pieza("b", largo=2420, ancho=1200)]
    r = nestear(justa, parametros)
    assert r.tableros == 1
    assert (r.colocaciones[0].x_mm, r.colocaciones[0].y_mm) == (10, 10)
    comprobar_geometria(r, justa, parametros)


def test_rotacion_necesaria() -> None:
    # 1200 x 2400: sin girar no cabe a lo largo (alto 2400 > 1220).
    parametros = sin_kerf()
    piezas = [pieza("a", largo=1200, ancho=2400)]
    r = nestear(piezas, parametros)
    assert r.tableros == 1 and r.colocaciones[0].rotada is True
    assert (r.colocaciones[0].ancho_mm, r.colocaciones[0].alto_mm) == (2400, 1200)
    comprobar_geometria(r, piezas, parametros)


def test_rotacion_prohibida_por_pieza() -> None:
    piezas = [
        pieza("a", largo=1200, ancho=2400, rotable=False),
        pieza("b", rotable=False),
    ]
    r = nestear(piezas, sin_kerf())
    assert [n.pieza_id for n in r.no_colocadas] == ["a"]
    assert r.no_colocadas[0].motivo == "no_cabe_sin_rotar"
    assert [c.pieza_id for c in r.colocaciones] == ["b"]
    assert all(not c.rotada for c in r.colocaciones)


def test_rotacion_prohibida_globalmente() -> None:
    parametros = sin_kerf(permitir_rotacion=False)
    piezas = [pieza("a", largo=1200, ancho=2400), pieza("b", largo=300, ancho=700)]
    r = nestear(piezas, parametros)
    assert [n.pieza_id for n in r.no_colocadas] == ["a"]
    assert all(not c.rotada for c in r.colocaciones)
    comprobar_geometria(r, [piezas[1]], parametros)


def test_rotacion_aprovecha_el_hueco() -> None:
    # Tablero 1000x500. Una pieza 700x500 y otra 500x300 (girada a 300x500 cabe al lado).
    parametros = ParametrosNesting(
        tablero_largo_mm=1000, tablero_ancho_mm=500, kerf_mm=0, margen_mm=0
    )
    piezas = [pieza("a", largo=700, ancho=500), pieza("b", largo=500, ancho=300)]
    r = nestear(piezas, parametros)
    assert r.tableros == 1
    giradas = {c.pieza_id: c.rotada for c in r.colocaciones}
    assert giradas == {"a": False, "b": True}
    comprobar_geometria(r, piezas, parametros)
    sin_giro = nestear(
        piezas,
        ParametrosNesting(**{**parametros.model_dump(), "permitir_rotacion": False}),
    )
    assert sin_giro.tableros == 2


def test_pieza_mayor_que_el_tablero_se_reporta_sin_descartar_el_resto() -> None:
    piezas = [
        pieza("enorme", largo=3000, ancho=2000, cantidad=2),
        pieza("normal", largo=600, ancho=400),
    ]
    r = nestear(piezas, sin_kerf())
    assert len(r.no_colocadas) == 1
    n = r.no_colocadas[0]
    assert (n.origen_id, n.pieza_id, n.ocurrencias) == ("P1", "enorme", 2)
    assert n.motivo == "mas_grande_que_el_area_util"
    assert (n.largo_mm, n.ancho_mm) == (3000, 2000)
    assert r.tableros == 1 and len(r.colocaciones) == 1


def test_medida_desconocida_queda_fuera_con_motivo() -> None:
    piezas = [pieza("a", largo=None), pieza("b", ancho=None), pieza("c")]
    r = nestear(piezas, sin_kerf())
    motivos = {n.pieza_id: n.motivo for n in r.no_colocadas}
    assert motivos == {"a": "medida_desconocida", "b": "medida_desconocida"}
    assert all(n.largo_mm is None or n.ancho_mm is None for n in r.no_colocadas)
    assert [c.pieza_id for c in r.colocaciones] == ["c"]


def test_cada_ocurrencia_se_coloca_por_separado() -> None:
    parametros = ParametrosNesting(kerf_mm=3, margen_mm=0)
    piezas = [pieza("a", largo=800, ancho=600, cantidad=7), pieza("b", cantidad=None)]
    r = nestear(piezas, parametros)
    ocurrencias = sorted(c.ocurrencia for c in r.colocaciones if c.pieza_id == "a")
    assert ocurrencias == [1, 2, 3, 4, 5, 6, 7]
    assert sum(1 for c in r.colocaciones if c.pieza_id == "b") == 1
    comprobar_geometria(r, piezas, parametros)


def test_determinista_con_independencia_del_orden_de_entrada() -> None:
    rng = random.Random(7)
    piezas = [
        pieza(
            f"p{i:02d}",
            largo=rng.randint(150, 1400),
            ancho=rng.randint(100, 900),
            cantidad=rng.randint(1, 4),
            rotable=rng.random() > 0.3,
            pedido=f"PED-{i % 3}",
        )
        for i in range(25)
    ]
    parametros = ParametrosNesting()
    a = nestear(piezas, parametros)
    b = nestear(list(reversed(piezas)), parametros)
    c = nestear(piezas, parametros)
    assert a.model_dump() == b.model_dump() == c.model_dump()
    comprobar_geometria(a, piezas, parametros)


@pytest.mark.parametrize("semilla", range(8))
def test_propiedad_sin_solapes_ni_salidas(semilla: int) -> None:
    rng = random.Random(semilla)
    parametros = ParametrosNesting(
        tablero_largo_mm=rng.choice([2440, 2800, 1830]),
        tablero_ancho_mm=rng.choice([1220, 2070, 915]),
        kerf_mm=rng.choice([0, 2.5, 4]),
        margen_mm=rng.choice([0, 5, 12.5]),
        permitir_rotacion=rng.random() > 0.3,
    )
    piezas = [
        pieza(
            f"p{i:03d}",
            largo=round(rng.uniform(40, 2600), 1),
            ancho=round(rng.uniform(30, 1300), 1),
            cantidad=rng.randint(1, 3),
            rotable=rng.random() > 0.2,
        )
        for i in range(40)
    ]
    r = nestear(piezas, parametros)
    comprobar_geometria(r, piezas, parametros)
    # Ninguna pieza que cabe sola en el área útil puede quedar sin colocar.
    no_colocadas_ids = {(n.origen_id, n.pieza_id) for n in r.no_colocadas}
    util_l = parametros.tablero_largo_mm - 2 * parametros.margen_mm
    util_a = parametros.tablero_ancho_mm - 2 * parametros.margen_mm
    for p in piezas:
        cabe = (p.largo_mm <= util_l and p.ancho_mm <= util_a) or (
            parametros.permitir_rotacion
            and p.rotable
            and p.ancho_mm <= util_l
            and p.largo_mm <= util_a
        )
        if cabe:
            assert (p.origen_id, p.pieza_id) not in no_colocadas_ids, p
    total = sum(p.cantidad or 1 for p in piezas)
    no_colocadas = sum(n.ocurrencias for n in r.no_colocadas)
    assert len(r.colocaciones) + no_colocadas == total


def test_limite_de_ocurrencias() -> None:
    piezas = [pieza("a", cantidad=LIMITE_OCURRENCIAS + 1)]
    with pytest.raises(DemasiadasOcurrencias):
        nestear(piezas, ParametrosNesting())


def test_rendimiento_con_el_maximo_de_ocurrencias() -> None:
    rng = random.Random(3)
    piezas = [
        pieza(
            f"p{i:03d}",
            largo=rng.randint(100, 900),
            ancho=rng.randint(80, 500),
            cantidad=LIMITE_OCURRENCIAS // 60,
        )
        for i in range(60)
    ]
    r = nestear(piezas, ParametrosNesting())
    assert len(r.colocaciones) == 60 * (LIMITE_OCURRENCIAS // 60)


def test_redondeo_del_lado_seguro() -> None:
    # Una pieza 0,4 µm más grande que el área útil no cabe (no se redondea a favor).
    r = nestear([pieza("a", largo=2440.0004, ancho=1220)], sin_kerf())
    assert r.tableros == 0 and r.no_colocadas[0].motivo == "mas_grande_que_el_area_util"
    # Un tablero 0,4 µm más pequeño que la pieza tampoco la admite.
    pequeno = ParametrosNesting(tablero_largo_mm=2439.9996, kerf_mm=0, margen_mm=0)
    assert nestear([pieza("a", largo=2440, ancho=1220)], pequeno).tableros == 0
    # El ruido de coma flotante no expulsa una pieza que mide exactamente lo mismo.
    exacto = ParametrosNesting(
        tablero_largo_mm=1220.3, tablero_ancho_mm=610.7, kerf_mm=0
    )
    assert nestear([pieza("a", largo=1220.3, ancho=610.7)], exacto).tableros == 1


def test_pares_duplicados_son_un_error() -> None:
    with pytest.raises(ValueError, match="duplicad"):
        nestear([pieza("a"), pieza("a", largo=300)], ParametrosNesting())
    # El mismo pieza_id en orígenes distintos es válido.
    r = nestear([pieza("a", pedido="P1"), pieza("a", pedido="P2")], ParametrosNesting())
    assert len(r.colocaciones) == 2


def test_peor_caso_una_pieza_por_tablero() -> None:
    # 1300x700 no admite una segunda pieza en 2440x1220 (ni girada): un tablero por pieza.
    piezas = [pieza("a", largo=1300, ancho=700, cantidad=LIMITE_OCURRENCIAS)]
    inicio = time.perf_counter()
    r = nestear(piezas, ParametrosNesting())
    assert time.perf_counter() - inicio < 10
    assert r.tableros == LIMITE_OCURRENCIAS
    # Formas todas distintas: el coste sigue acotado.
    distintas = [
        pieza(f"p{i:04d}", largo=1300 + i / 100, ancho=700)
        for i in range(LIMITE_OCURRENCIAS)
    ]
    inicio = time.perf_counter()
    r = nestear(distintas, ParametrosNesting())
    assert time.perf_counter() - inicio < 10
    assert r.tableros == LIMITE_OCURRENCIAS


# ---------- integración con lotes ----------


def test_lote_incluye_nesting_y_conserva_la_estimacion() -> None:
    piezas = [
        pieza("a", largo=2000, ancho=1000, cantidad=2),
        pieza("b", largo=1000, ancho=1000, cantidad=None, pedido="P2"),
    ]
    lote = preparar_lotes(piezas, ConfiguracionLotes()).lotes[0]
    assert lote.estimacion.es_estimacion is True
    assert lote.estimacion.metodo == "superficie_sobre_aprovechamiento"
    assert lote.estimacion.tableros == 3
    nesting = lote.nesting
    assert nesting.metodo == "guillotina_ffd_bssf"
    assert nesting.es_estimacion is False
    assert nesting.tableros >= 2
    assert len(nesting.colocaciones) == 3
    comprobar_geometria(nesting, piezas, ConfiguracionLotes())


def test_piezas_que_no_caben_coherente_con_rotacion_y_margen() -> None:
    piezas = [
        pieza("girable", largo=1200, ancho=2400),
        pieza("fija", largo=1200, ancho=2400, rotable=False),
        pieza("larga", largo=2600),
    ]
    lote = preparar_lotes(piezas, ConfiguracionLotes()).lotes[0]
    assert [p.pieza_id for p in lote.piezas_que_no_caben] == ["fija", "larga"]
    assert {n.pieza_id for n in lote.nesting.no_colocadas} == {"fija", "larga"}


def test_lotes_separan_grupos_y_numeran_tableros_por_grupo() -> None:
    piezas = [
        pieza("a", largo=2440, ancho=1220, material="x"),
        pieza("b", largo=2440, ancho=1220, material="y"),
    ]
    resultado = preparar_lotes(piezas, ConfiguracionLotes(margen_mm=0))
    assert [l.nesting.tableros for l in resultado.lotes] == [1, 1]
    assert resultado.configuracion.kerf_mm == 3


def test_limite_de_ocurrencias_es_por_lote() -> None:
    piezas = [
        pieza("grande", cantidad=LIMITE_OCURRENCIAS + 1, material="a"),
        pieza("larga", largo=3000, cantidad=LIMITE_OCURRENCIAS + 1, material="a"),
        pieza("pequena", cantidad=2, material="b"),
    ]
    resultado = preparar_lotes(piezas, ConfiguracionLotes())
    por_material = {lote.clave.material: lote for lote in resultado.lotes}
    excedido = por_material["a"]
    assert excedido.nesting is None
    assert excedido.nesting_omitido == "demasiadas_ocurrencias"
    assert excedido.estimacion.tableros >= 1
    assert [p.pieza_id for p in excedido.piezas_que_no_caben] == ["larga"]
    assert por_material["b"].nesting is not None
    assert por_material["b"].nesting_omitido is None
    assert por_material["b"].nesting.tableros == 1


def test_presupuesto_total_de_calculo() -> None:
    piezas = [
        pieza(f"p{i}", cantidad=LIMITE_OCURRENCIAS, material=f"m{i}")
        for i in range(LIMITE_OCURRENCIAS_TOTAL // LIMITE_OCURRENCIAS + 1)
    ]
    config = ConfiguracionLotes(tablero_largo_mm=10000, tablero_ancho_mm=10000)
    resultado = preparar_lotes(piezas, config)
    omitidos = [lote for lote in resultado.lotes if lote.nesting is None]
    assert len(omitidos) == 1
    assert omitidos[0].nesting_omitido == "limite_total_de_calculo"
    assert all(
        lote.nesting is not None for lote in resultado.lotes if lote is not omitidos[0]
    )


def test_parametros_invalidos() -> None:
    with pytest.raises(ValueError):
        ConfiguracionLotes(margen_mm=700)
    with pytest.raises(ValueError):
        ConfiguracionLotes(kerf_mm=-1)
    with pytest.raises(ValueError):
        ConfiguracionLotes(kerf_mm=float("nan"))


# ---------- endpoint ----------


def cliente() -> TestClient:
    app = FastAPI()
    app.include_router(crear_router_piezas(None))
    return TestClient(app)


def cuerpo(piezas: list[dict], **extra: object) -> dict:
    return {"pedidos": [{"pedido_id": "PED-1", "piezas": piezas}], **extra}


def pieza_json(pid: str, largo: float, ancho: float, **extra: object) -> dict:
    return {
        "pieza_id": pid,
        "largo_mm": largo,
        "ancho_mm": ancho,
        "espesor_mm": 18,
        "material": "melamina",
        "cantidad": 1,
        **extra,
    }


def test_endpoint_devuelve_nesting_con_parametros_de_la_peticion() -> None:
    r = cliente().post(
        RUTA,
        json=cuerpo(
            [pieza_json("a", 1220, 1220, cantidad=2)],
            kerf_mm=3,
            margen_mm=0,
            tablero_largo_mm=2440,
            tablero_ancho_mm=1220,
        ),
    )
    assert r.status_code == 200
    datos = r.json()["data"]
    assert datos["configuracion"]["kerf_mm"] == 3
    lote = datos["lotes"][0]
    assert lote["estimacion"]["metodo"] == "superficie_sobre_aprovechamiento"
    assert lote["nesting"]["tableros"] == 2
    assert len(lote["nesting"]["colocaciones"]) == 2
    primera = lote["nesting"]["colocaciones"][0]
    assert set(primera) == {
        "origen_id",
        "pieza_id",
        "ocurrencia",
        "tablero",
        "x_mm",
        "y_mm",
        "ancho_mm",
        "alto_mm",
        "rotada",
    }


def test_endpoint_rotable_false_y_permitir_rotacion() -> None:
    piezas = [pieza_json("a", 1200, 2400, rotable=False)]
    r = cliente().post(RUTA, json=cuerpo(piezas))
    nesting = r.json()["data"]["lotes"][0]["nesting"]
    assert nesting["tableros"] == 0
    assert nesting["no_colocadas"][0]["motivo"] == "no_cabe_sin_rotar"
    r = cliente().post(RUTA, json=cuerpo([pieza_json("a", 1200, 2400)]))
    assert r.json()["data"]["lotes"][0]["nesting"]["colocaciones"][0]["rotada"] is True
    r = cliente().post(
        RUTA, json=cuerpo([pieza_json("a", 1200, 2400)], permitir_rotacion=False)
    )
    assert r.json()["data"]["lotes"][0]["nesting"]["tableros"] == 0


def test_endpoint_limite_de_ocurrencias_por_lote() -> None:
    piezas = [pieza_json("a", 100, 100, cantidad=LIMITE_OCURRENCIAS + 1)]
    r = cliente().post(RUTA, json=cuerpo(piezas))
    assert r.status_code == 200
    lote = r.json()["data"]["lotes"][0]
    assert lote["nesting"] is None
    assert lote["nesting_omitido"] == "demasiadas_ocurrencias"
    assert lote["estimacion"]["tableros"] >= 1


def item_v2(run_id: str, material: str, cantidad: int) -> LibraryItem:
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
            material=material,
            finish="mate",
            thicknesses_mm=(18.0,),
            classification_status="hypothesis",
            part_features=(
                DescriptorPartFeature(
                    length_mm=500, width_mm=400, thickness_mm=18, quantity=cantidad
                ),
            ),
            unknown_fields=(),
        ),
        descriptor_fingerprint="a" * 64,
        created_at="2026-01-01T00:00:00Z",
    )


def test_endpoint_biblioteca_con_un_lote_excedido_sigue_dando_200() -> None:
    class Biblioteca:
        def get_library_items(self) -> tuple[LibraryItem, ...]:
            return (
                item_v2("run-grande", "melamina", LIMITE_OCURRENCIAS + 1),
                item_v2("run-pequeno", "roble", 3),
            )

    app = FastAPI()
    app.include_router(crear_router_piezas(Biblioteca()))
    r = TestClient(app).post(RUTA, json={"incluir_biblioteca": True})
    assert r.status_code == 200
    por_material = {
        lote["clave"]["material"]: lote for lote in r.json()["data"]["lotes"]
    }
    assert por_material["melamina"]["nesting"] is None
    assert por_material["melamina"]["nesting_omitido"] == "demasiadas_ocurrencias"
    assert por_material["roble"]["nesting"]["tableros"] == 1
    # Las piezas de biblioteca no traen información de veta: salen rotables.
    assert por_material["roble"]["piezas"][0]["rotable"] is True


def test_endpoint_configuracion_invalida_mismo_formato() -> None:
    piezas = [pieza_json("a", 100, 100)]
    casos = [
        {"margen_mm": 700},
        {"kerf_mm": -1},
        {"margen_mm": 400, "tablero_largo_mm": 600, "tablero_ancho_mm": 600},
    ]
    detalles = []
    for extra in casos:
        r = cliente().post(RUTA, json=cuerpo(piezas, **extra))
        assert r.status_code == 422
        detalles.append(r.json()["detail"])
    assert all(isinstance(d, list) and d for d in detalles)
    assert "margen" in detalles[2][0]["msg"].lower()
    assert "margen" not in detalles[1][0]["msg"].lower()


def test_endpoint_sin_campos_nuevos_sigue_funcionando() -> None:
    r = cliente().post(RUTA, json=cuerpo([pieza_json("a", 1000, 500)]))
    assert r.status_code == 200
    lote = r.json()["data"]["lotes"][0]
    assert lote["estimacion"]["tableros"] == 1
    assert lote["nesting"]["tableros"] == 1
