import hashlib
import json
import zipfile
from pathlib import Path

import ezdxf
import pytest

from backend.app.precedentes.evaluacion import ConjuntoJuicios
from tools import evaluar_recuperacion, plankassembly_corpus
from tools.plankassembly_corpus import (
    ReglaRelevancia,
    generar_corpus,
    grado_relevancia,
)

CAMPO_CATEGORIA = "furniture_kind"


def _mueble(ancho, fondo, alto, baldas, *, grosor=18, trasera=True, escala=1.0, **extra):
    """Cuboides [xmin,ymin,zmin,xmax,ymax,zmax]; la primera fila es la envolvente."""
    t = grosor
    planks = [[0, 0, 0, ancho, fondo, alto]]
    normal = [[0, 0, 1]]
    planks += [[0, 0, 0, t, fondo, alto], [ancho - t, 0, 0, ancho, fondo, alto]]
    normal += [[1, 0, 0], [-1, 0, 0]]
    planks += [[t, 0, 0, ancho - t, fondo, t], [t, 0, alto - t, ancho - t, fondo, alto]]
    normal += [[0, 0, 1], [0, 0, -1]]
    for i in range(baldas):
        z = alto * (i + 1) / (baldas + 1)
        planks.append([t, 0, z, ancho - t, fondo, z + t])
        normal.append([0, 0, 1])
    if trasera:
        planks.append([t, fondo - 5, t, ancho - t, fondo, alto - t])
        normal.append([0, -1, 0])
    if escala != 1.0:
        planks = [[round(v * escala, 6) for v in row] for row in planks]
    attach = [[-1] * 6] + [[0, 1, 2, -1, 4, 5] for _ in planks[1:]]
    return {"planks": planks, "attach": attach, "normal": normal, **extra}


def _escribir(root: Path, modelos: dict[str, tuple[str | None, dict]], *, sin_normal=()):
    model_dir = root / "extracted" / "data" / "model"
    split_dir = root / "extracted" / "data" / "splits"
    model_dir.mkdir(parents=True)
    split_dir.mkdir(parents=True)
    listas = {"train": [], "valid": [], "test": []}
    for nombre, (particion, modelo) in modelos.items():
        modelo = dict(modelo)
        if nombre in sin_normal:
            modelo.pop("normal")
        (model_dir / nombre).write_text(json.dumps(modelo), encoding="utf-8")
        if particion:
            listas[particion].append(nombre)
    for particion, nombres in listas.items():
        (split_dir / f"{particion}.txt").write_text("".join(n + "\n" for n in nombres), encoding="utf-8")


def _universo(root: Path):
    marca = {"name": "revealing-source-name", "id": "SECRETO-ID", CAMPO_CATEGORIA: "bookcase-secreta"}
    m = {}
    # train: diseños distintos
    m["tr_a.json"] = ("train", _mueble(800, 300, 1800, 3, **marca))
    m["tr_b.json"] = ("train", _mueble(1200, 500, 900, 1, trasera=False))
    m["tr_c.json"] = ("train", _mueble(600, 400, 2000, 5))
    m["tr_d.json"] = ("train", _mueble(1000, 450, 1000, 2, grosor=22))
    m["tr_e.json"] = ("train", _mueble(900, 350, 1900, 4, trasera=False))
    # valid: uno único y uno duplicado exacto de un train
    m["va_unico.json"] = ("valid", _mueble(1500, 600, 800, 2))
    m["va_dup_train.json"] = ("valid", _mueble(1200, 500, 900, 1, trasera=False))
    # test: copia reescalada de tr_a (cruza), dos duplicados exactos entre sí, y únicos
    m["te_escalado_de_tr_a.json"] = ("test", _mueble(800, 300, 1800, 3, escala=1.5, **marca))
    m["te_dup_1.json"] = ("test", _mueble(700, 330, 1700, 3))
    m["te_dup_2.json"] = ("test", _mueble(700, 330, 1700, 3))
    m["te_unico_1.json"] = ("test", _mueble(1000, 460, 1020, 2, grosor=22))
    m["te_unico_2.json"] = ("test", _mueble(640, 400, 2050, 5))
    # no listado: no debe muestrearse ni contar como universo
    m["no_listado.json"] = (None, _mueble(777, 333, 1555, 3))
    _escribir(root, m, sin_normal=("tr_c.json", "te_unico_2.json"))


@pytest.fixture
def fuente(tmp_path: Path) -> Path:
    root = tmp_path / "src"
    _universo(root)
    return root


def _generar(fuente, tmp_path, nombre="a", **kw):
    kw.setdefault("sizes", {"train": 10, "valid": 10, "test": 10})
    kw.setdefault("seed", 7)
    pub, priv = tmp_path / f"pub-{nombre}", tmp_path / f"priv-{nombre}"
    manifiesto = generar_corpus(fuente, pub, priv, **kw)
    return pub, priv, manifiesto


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _arbol(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def test_particiones_oficiales_no_listados_y_duplicados(fuente, tmp_path):
    _, priv, manifiesto = _generar(fuente, tmp_path)
    audit = _json(priv / "audit.json")
    refs = {r["source_file"]: r for r in _json(priv / "references.json") if r["variant_of"] is None}
    # no listado: excluido y contado
    assert audit["unlisted_json_excluded"] == 1 and "no_listado.json" not in refs
    # cada caso conserva la partición oficial de su archivo
    oficial = {n: p for n, (p, _) in _json_modelos().items() if p}
    assert all(r["partition"] == oficial[n] for n, r in refs.items())
    # duplicado cruzado: el train se conserva, valid/test se descontaminan
    assert "tr_a.json" in refs and "te_escalado_de_tr_a.json" not in refs
    assert "tr_b.json" in refs and "va_dup_train.json" not in refs
    assert audit["dropped_cross_split"]["test"] == ["te_escalado_de_tr_a.json"]
    assert audit["dropped_cross_split"]["valid"] == ["va_dup_train.json"]
    # duplicado dentro de test: un único representante (menor nombre)
    assert "te_dup_1.json" in refs and "te_dup_2.json" not in refs
    assert audit["dropped_within_split_duplicate"]["test"] == ["te_dup_2.json"]
    # ningún grupo cruza particiones
    grupos: dict[str, set[str]] = {}
    for r in refs.values():
        grupos.setdefault(r["group_id"], set()).add(r["partition"])
    assert all(len(p) == 1 for p in grupos.values()) and len({r["group_id"] for r in refs.values()}) == len(refs)
    assert audit["duplicate_groups"]["groups_crossing_partitions"] == 2
    assert manifiesto["partitions"]["test"]["sampled"] == 3  # dup_1, unico_1, unico_2


def _json_modelos():
    # reconstruye el universo para conocer las particiones oficiales
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "s"
        _universo(root)
        out = {}
        for p in ("train", "valid", "test"):
            for n in (root / "extracted/data/splits" / f"{p}.txt").read_text().split():
                out[n] = (p, None)
        return out


def test_determinismo_semilla_y_tamano(fuente, tmp_path):
    a = _generar(fuente, tmp_path, "a", sizes={"train": 3, "valid": 1, "test": 2})
    b = _generar(fuente, tmp_path, "b", sizes={"train": 3, "valid": 1, "test": 2})
    assert _arbol(a[0]) == _arbol(b[0]) and _arbol(a[1]) == _arbol(b[1])
    otra = _generar(fuente, tmp_path, "c", sizes={"train": 3, "valid": 1, "test": 2}, seed=8)
    fuentes = lambda priv: [r["source_file"] for r in _json(priv / "references.json")]
    assert a[2]["partitions"]["train"]["sampled"] == 3 and a[2]["partitions"]["test"]["sampled"] == 2
    # el muestreo depende de la semilla (alguna de las semillas cambia el orden de train o test)
    muestras = [set(fuentes(_generar(fuente, tmp_path, f"s{s}", sizes={"train": 2, "valid": 1, "test": 1}, seed=s)[1])) for s in range(6)]
    assert len({frozenset(m) for m in muestras}) > 1
    assert _json(otra[1] / "manifest.json")["seed"] == "8"


def test_muestreo_estable_por_prefijo(fuente, tmp_path):
    pequeno = _json(_generar(fuente, tmp_path, "p", sizes={"train": 2, "valid": 1, "test": 1})[1] / "references.json")
    grande = _json(_generar(fuente, tmp_path, "g", sizes={"train": 4, "valid": 1, "test": 3})[1] / "references.json")
    assert {r["source_file"] for r in pequeno} <= {r["source_file"] for r in grande}
    assert {r["id"] for r in pequeno} <= {r["id"] for r in grande}  # ids estables por posición


def test_aislamiento_publico_privado_sin_fugas(fuente, tmp_path):
    pub, priv, _ = _generar(fuente, tmp_path, poor_variants=True, category_field=CAMPO_CATEGORIA)
    assert not (pub / "references.json").exists() and not (pub / "audit.json").exists()
    secretos = [b"revealing-source-name", b"SECRETO-ID", b"bookcase-secreta", b"planks", b"attach", b"normal",
                b"group_id", b"family_hash", b"familia", b"te_unico", b"tr_a", b".json\"", b"source_file"]
    for archivo in sorted(pub.rglob("*")):
        if not archivo.is_file():
            continue
        contenidos = [archivo.read_bytes(), archivo.name.encode()]
        if archivo.suffix == ".zip":
            with zipfile.ZipFile(archivo) as z:
                assert z.testzip() is None and set(z.namelist()) == {"input.dxf", "case.json"}
                contenidos += [z.read(n) for n in z.namelist()]
                meta = json.loads(z.read("case.json"))
                assert set(meta) == {"file", "format", "id", "instruction", "sha256", "unit", "view_kind"}
        for contenido in contenidos:
            for secreto in secretos:
                assert secreto not in contenido, (archivo.name, secreto)
    for dxf in (pub / "dxf").glob("*.dxf"):
        doc = ezdxf.readfile(dxf)
        assert not list(doc.modelspace().query("TEXT"))
        assert all(n.dxf.name.startswith("ORTHO_") or n.dxf.name in {"0", "Defpoints"} for n in doc.layers)
    # la referencia, los grupos y los juicios solo existen en la parte privada
    assert (priv / "references.json").exists() and (priv / "juicios" / "juicios_test.json").exists()
    assert set(_json(pub / "manifest.json")) <= {
        "generator_version", "source_dataset", "source_revision", "partitions", "complete_cases",
        "poor_variant_cases", "view_kind", "inference_evaluated", "redistribution_authorized", "license_notice",
        "cases_sha256", "poor_variants",
    }
    # hashes del manifiesto consistentes
    sumas = (pub / "SHA256SUMS").read_text().splitlines()
    assert all(hashlib.sha256((pub / linea.split("  ", 1)[1]).read_bytes()).hexdigest() == linea.split("  ")[0] for linea in sumas)
    assert _json(priv / "manifest.json")["public_manifest_sha256"] == hashlib.sha256((pub / "manifest.json").read_bytes()).hexdigest()


def test_envolvente_ignorada_y_normal_ausente_tolerado(fuente, tmp_path):
    _, priv, priv_manifest = _generar(fuente, tmp_path)
    refs = {r["source_file"]: r for r in _json(priv / "references.json") if r["variant_of"] is None}
    tr_a = refs["tr_a.json"]
    assert tr_a["envelope_source_index"] == 0
    assert all(c["source_index"] >= 1 for c in tr_a["components"])
    assert tr_a["features"]["n_piezas"] == len(tr_a["components"])
    assert [0, 0, 0, 800, 300, 1800] not in [c["bounds_mm"] for c in tr_a["components"]]
    assert all(c["normal"] is None for c in refs["tr_c.json"]["components"])
    assert refs["tr_a.json"]["components"][0]["normal"] == [1, 0, 0]
    assert _json(priv / "manifest.json")["sampled_without_normal"] == 2
    assert priv_manifest["inference_evaluated"] is False


def test_features_y_familia(fuente, tmp_path):
    _, priv, _ = _generar(fuente, tmp_path)
    refs = {r["source_file"]: r for r in _json(priv / "references.json") if r["variant_of"] is None}
    assert refs["tr_a.json"]["features"]["familia_estructural"] == "alto_con_trasera"
    assert refs["tr_b.json"]["features"]["familia_estructural"] == "medio_abierto"
    assert refs["tr_b.json"]["familia_origen"] == "estructural_inferida"
    assert refs["tr_a.json"]["features"]["n_horizontales"] == 2 + 3
    assert refs["tr_a.json"]["features"]["ancho_mm"] == 800
    # sin --category-field no se usa ningún campo de categoría
    assert refs["tr_a.json"]["categoria"] is None
    _, priv2, _ = _generar(fuente, tmp_path, "cat", category_field=CAMPO_CATEGORIA)
    refs2 = {r["source_file"]: r for r in _json(priv2 / "references.json") if r["variant_of"] is None}
    assert refs2["tr_a.json"]["familia"] == "bookcase-secreta" and refs2["tr_a.json"]["familia_origen"] == "categoria_declarada"


def test_regla_de_relevancia():
    def caso(familia, ancho, fondo, alto, n, h, v):
        return {"familia": familia, "features": {"ancho_mm": ancho, "fondo_mm": fondo, "alto_mm": alto, "n_piezas": n,
                                                 "n_horizontales": h, "n_verticales": v}}

    regla = ReglaRelevancia()
    q = caso("f", 1000, 400, 2000, 8, 4, 4)
    assert grado_relevancia(q, caso("f", 1050, 410, 1900, 9, 4, 5), regla) == 2
    assert grado_relevancia(q, caso("f", 1200, 400, 2000, 8, 4, 4), regla) == 1  # 16.7 % en un eje
    assert grado_relevancia(q, caso("g", 1050, 400, 2000, 8, 4, 4), regla) == 1  # otra familia, mismo histograma
    assert grado_relevancia(q, caso("g", 1050, 400, 2000, 8, 8, 0), regla) == 0
    assert grado_relevancia(q, caso("f", 2000, 400, 2000, 8, 4, 4), regla) == 0
    assert grado_relevancia(q, caso("f", 1000, 400, 2000, 14, 4, 10), regla) == 0
    c = caso("f", 1100, 420, 1800, 10, 5, 5)
    assert grado_relevancia(q, c, regla) == grado_relevancia(c, q, regla)  # simétrica


def test_juicios_bien_formados_y_sin_duplicado_propio(fuente, tmp_path):
    pub, priv, _ = _generar(fuente, tmp_path)
    juicios = ConjuntoJuicios.model_validate_json((priv / "juicios" / "juicios_test.json").read_text(encoding="utf-8"))
    refs = {r["id"]: r for r in _json(priv / "references.json")}
    publicos = {c["id"]: c for c in _json(pub / "cases.json")}
    assert juicios.origen == "derived_reference" and "regla" in juicios.descripcion.lower()
    consultas = {j.consulta_id: j for j in juicios.consultas}
    assert set(consultas) == {i for i, r in refs.items() if r["partition"] == "test"}
    todas = {i for i, r in refs.items() if r["variant_of"] is None}
    for consulta_id, j in consultas.items():
        # solo partición test como consulta, densos: todos los demás casos completos juzgados
        assert set(j.relevancias) == todas - {consulta_id}
        assert set(j.relevancias) <= set(publicos)
        grupo = refs[consulta_id]["group_id"]
        for candidato in j.relevancias:
            assert refs[candidato]["group_id"] != grupo  # nunca su duplicado/variante
        # ninguna clave fuente en los juicios
        assert not any(".json" in k for k in j.relevancias)
    mismos_grados = [g for j in juicios.consultas for g in j.relevancias.values()]
    assert set(mismos_grados) <= {0, 1, 2} and 2 in mismos_grados


def _refs_por_id(priv: Path) -> dict[str, dict]:
    return {r["id"]: r for r in _json(priv / "references.json")}


def test_variantes_empobrecidas_marcadas_y_con_juicios_propios(fuente, tmp_path):
    pub, priv, manifiesto = _generar(fuente, tmp_path, poor_variants=True)
    casos = {c["id"]: c for c in _json(pub / "cases.json")}
    refs = _refs_por_id(priv)
    variantes = [r for r in refs.values() if r["variant_of"]]
    assert variantes and all(r["partition"] == "test" and r["variant_of"] in casos for r in variantes)
    assert {r["poor_kind"] for r in variantes} == {"solo_frontal", "frontal_y_planta"}
    assert manifiesto["poor_variant_cases"] == len(variantes)
    una = next(r for r in variantes if r["poor_kind"] == "solo_frontal")
    publico = casos[una["id"]]
    doc = ezdxf.readfile(pub / publico["file"])
    assert {e.dxf.layer for e in doc.modelspace()} == {"ORTHO_FRONT"}
    completo = ezdxf.readfile(pub / casos[una["variant_of"]]["file"])
    assert {e.dxf.layer for e in completo.modelspace()} == {"ORTHO_FRONT", "ORTHO_TOP", "ORTHO_SIDE"}
    assert publico["view_kind"] == "assembled_orthographic_partial"
    assert publico["sha256"] != casos[una["variant_of"]]["sha256"]
    principal = ConjuntoJuicios.model_validate_json((priv / "juicios" / "juicios_test.json").read_text(encoding="utf-8"))
    ids_variantes = {r["id"] for r in variantes}
    assert not any(c.consulta_id in ids_variantes for c in principal.consultas)
    assert not any(k in ids_variantes for c in principal.consultas for k in c.relevancias)
    frontal = ConjuntoJuicios.model_validate_json((priv / "juicios" / "juicios_test_solo_frontal.json").read_text(encoding="utf-8"))
    por_base = {c.consulta_id: c for c in principal.consultas}
    de_base = {r["variant_of"]: r["id"] for r in variantes if r["poor_kind"] == "solo_frontal"}
    for c in frontal.consultas:
        origen = refs[c.consulta_id]["variant_of"]
        assert origen not in c.relevancias  # la completa propia nunca es candidata juzgada
        for candidato, grado in c.relevancias.items():
            if candidato in ids_variantes:
                # una variante candidata hereda el grado de su caso base
                assert refs[candidato]["poor_kind"] == "solo_frontal" and candidato != c.consulta_id
                assert grado == por_base[origen].relevancias[refs[candidato]["variant_of"]]
            else:
                assert grado == por_base[origen].relevancias[candidato]
        esperados = {de_base[b] for b in de_base if b != origen}
        assert esperados <= set(c.relevancias)


def test_ids_publicos_opacos_y_sin_relacion_variante_base(fuente, tmp_path):
    pub, priv, _ = _generar(fuente, tmp_path, poor_variants=True)
    ids = [c["id"] for c in _json(pub / "cases.json")]
    assert len(ids) == len(set(ids)) and len({len(i) for i in ids}) == 1  # longitud fija
    assert not any(a != b and b.startswith(a) for a in ids for b in ids)  # ningún id es prefijo de otro
    refs = _refs_por_id(priv)
    for r in refs.values():
        if r["variant_of"]:
            assert r["variant_of"] not in r["id"] and r["id"] not in r["variant_of"]
    # sin la semilla privada los ids no se reconstruyen: otra semilla da otros ids
    otros = {c["id"] for c in _json(_generar(fuente, tmp_path, "otra", poor_variants=True, seed=99)[0] / "cases.json")}
    assert not set(ids) & otros
    claves_publicas = set()
    for c in _json(pub / "cases.json"):
        claves_publicas |= set(c)
    assert claves_publicas == {"id", "file", "format", "unit", "view_kind", "instruction", "sha256", "partition"}
    assert "seed" not in _json(pub / "manifest.json") and _json(priv / "manifest.json")["seed"] == "7"
    for archivo in sorted(pub.rglob("*")):
        if not archivo.is_file():
            continue
        contenidos = [archivo.read_bytes()]
        if archivo.suffix == ".zip":
            with zipfile.ZipFile(archivo) as z:
                contenidos += [z.read(n) for n in z.namelist()]
        for contenido in contenidos:
            for prohibido in (b"variant_of", b"poor_kind", b"\"variant\"", b"solo_frontal", b"frontal_y_planta"):
                assert prohibido not in contenido, (archivo.name, prohibido)


def test_tope_de_pares_y_ceros_por_consulta(fuente, tmp_path):
    with pytest.raises(ValueError, match="max_pairs"):
        _generar(fuente, tmp_path, "tope", max_pairs=3)
    assert not (tmp_path / "pub-tope").exists() and not list(tmp_path.glob("pub-tope.partial-*"))
    _, priv, _ = _generar(fuente, tmp_path, "ceros", max_pairs=3, zeros_per_query=1)
    for c in _json(priv / "juicios" / "juicios_test.json")["consultas"]:
        assert sum(1 for g in c["relevancias"].values() if g == 0) <= 1


def test_destinos_inseguros(fuente, tmp_path):
    with pytest.raises(ValueError, match="separate"):
        generar_corpus(fuente, tmp_path / "x", tmp_path / "x" / "y")
    with pytest.raises(ValueError, match="inside the repository"):
        generar_corpus(fuente, plankassembly_corpus.REPO_ROOT / "tmp-no" / "p", tmp_path / "q")
    pub, _, _ = _generar(fuente, tmp_path)
    with pytest.raises(ValueError, match="exists"):
        generar_corpus(fuente, pub, tmp_path / "otro")
    with pytest.raises(ValueError, match="test partition"):
        generar_corpus(fuente, tmp_path / "p2", tmp_path / "q2", sizes={"test": 0})


def test_modelos_ausentes_o_compartidos_son_error(tmp_path):
    root = tmp_path / "s"
    _universo(root)
    (root / "extracted/data/model/tr_a.json").unlink()
    with pytest.raises(ValueError, match="missing"):
        generar_corpus(root, tmp_path / "p", tmp_path / "q")
    root2 = tmp_path / "s2"
    _universo(root2)
    with (root2 / "extracted/data/splits/test.txt").open("a", encoding="utf-8") as f:
        f.write("tr_a.json\n")
    with pytest.raises(ValueError, match="listed in both"):
        generar_corpus(root2, tmp_path / "p2", tmp_path / "q2")


def test_modelo_invalido_se_audita_sin_abortar(tmp_path):
    root = tmp_path / "s"
    _universo(root)
    (root / "extracted/data/model/tr_b.json").write_text(json.dumps({"planks": [[0, 0, 0, 1, 1, 1]], "attach": []}), encoding="utf-8")
    _, priv, _ = _generar(root, tmp_path)
    audit = _json(priv / "audit.json")
    assert [i["source_file"] for i in audit["invalid_models"]] == ["tr_b.json"]


def _biblioteca_para(priv: Path, nombre_juicios: str, destino: Path) -> Path:
    """Biblioteca según el contrato machine-readable `juicios/bibliotecas.json` del corpus."""
    contrato = _json(priv / "juicios" / "bibliotecas.json")[nombre_juicios]
    refs = _refs_por_id(priv)
    items = []
    for case_id in contrato["case_ids"]:
        r = refs[case_id]
        f = (refs[r["variant_of"]] if r["variant_of"] else r)["features"]
        items.append({
            "id": case_id, "run_id": contrato["run_id_overrides"].get(case_id, case_id), "result_revision": 1, "label": case_id,
            "descriptor": {
                "descriptor_version": "furniture-v1", "family": "unknown",
                "dimensions": {"width_mm": f["ancho_mm"], "depth_mm": f["fondo_mm"], "height_mm": f["alto_mm"]},
                "roles": [{"role": "shelf", "quantity": f["n_horizontales"]}],
                "structure": "unknown", "unknown_fields": [],
            },
            "descriptor_fingerprint": "0" * 64, "created_at": "2026-01-01T00:00:00+00:00",
        })
    ruta = destino / f"biblioteca-{nombre_juicios}"
    ruta.write_text(json.dumps({"items": items}), encoding="utf-8")
    return ruta


def _ejecutar_oraculo(priv, nombre, tmp_path, monkeypatch, capsys):
    ruta = priv / "juicios" / nombre
    objetivo = {c["consulta_id"]: c["relevancias"] for c in _json(ruta)["consultas"]}
    biblioteca = _biblioteca_para(priv, nombre, tmp_path)
    metodo = "oraculo-" + nombre
    monkeypatch.setitem(
        evaluar_recuperacion.METODOS, metodo,
        lambda q, cs: tuple((c.id, float(objetivo[q.id][c.id])) for c in cs),  # KeyError si falta un juicio
    )
    assert evaluar_recuperacion.main(["--biblioteca", str(biblioteca), "--juicios", str(ruta), "--k", "3", "--metodo", metodo]) == 0
    return json.loads(capsys.readouterr().out)


def test_extremo_a_extremo_con_todos_los_archivos_de_juicios(fuente, tmp_path, monkeypatch, capsys):
    _, priv, _ = _generar(fuente, tmp_path, poor_variants=True)
    nombres = sorted(p.name for p in (priv / "juicios").glob("juicios_*.json"))
    assert nombres == ["juicios_identidad_frontal_y_planta.json", "juicios_identidad_solo_frontal.json",
                       "juicios_test.json", "juicios_test_frontal_y_planta.json", "juicios_test_solo_frontal.json"]
    for nombre in nombres:
        informe = _ejecutar_oraculo(priv, nombre, tmp_path, monkeypatch, capsys)
        assert informe["origen_juicios"] == "derived_reference" and informe["aviso"]
        assert informe["advertencias"] == [], nombre
        agregadas = informe["agregadas"]
        assert agregadas["cobertura_juicios"] == 1.0, nombre  # ningún candidato queda sin juicio
        assert agregadas["candidatos_sin_juicio"] == 0
        assert agregadas["consultas"] == len(_json(priv / "juicios" / nombre)["consultas"])
        assert agregadas["ndcg_k"] in (1.0, None)
        if nombre.startswith("juicios_identidad"):
            assert agregadas["precision_k"] == pytest.approx(1 / 3) and agregadas["mrr"] == 1.0
        else:
            assert agregadas["consultas_sin_relevantes"] < agregadas["consultas"]
        assert all(e["misma_consulta"] == 1 for e in informe["exclusiones"])
    # el contrato excluye al mueble completo propio solo donde corresponde
    refs = _refs_por_id(priv)
    graduado = _ejecutar_oraculo(priv, "juicios_test_solo_frontal.json", tmp_path, monkeypatch, capsys)
    assert all(e["mismo_run"] == 1 for e in graduado["exclusiones"])
    identidad = _ejecutar_oraculo(priv, "juicios_identidad_solo_frontal.json", tmp_path, monkeypatch, capsys)
    assert all(e["mismo_run"] == 0 for e in identidad["exclusiones"])
    assert refs  # los ids usados existen en la referencia


def test_recuperador_trivial_es_determinista(fuente, tmp_path, monkeypatch, capsys):
    _, priv, _ = _generar(fuente, tmp_path)
    ruta = priv / "juicios" / "juicios_test.json"
    biblioteca = _biblioteca_para(priv, "juicios_test.json", tmp_path)

    def trivial(consulta, candidatos):
        return tuple((c.id, -abs(c.descriptor.roles[0].quantity - consulta.descriptor.roles[0].quantity)) for c in candidatos)

    monkeypatch.setitem(evaluar_recuperacion.METODOS, "trivial", trivial)
    argv = ["--biblioteca", str(biblioteca), "--juicios", str(ruta), "--k", "3", "--metodo", "trivial"]
    assert evaluar_recuperacion.main(argv) == 0
    primero = capsys.readouterr().out
    assert evaluar_recuperacion.main(argv) == 0
    assert capsys.readouterr().out == primero
    assert json.loads(primero)["agregadas"]["cobertura_juicios"] == 1.0


def test_identidad_respeta_max_pairs(fuente, tmp_path):
    _, priv, _ = _generar(fuente, tmp_path, poor_variants=True)
    refs = list(_refs_por_id(priv).values())
    with pytest.raises(ValueError, match="max_pairs"):
        plankassembly_corpus.juicios_identidad(refs, "solo_frontal", version="v", max_pares=5)
    recortado = plankassembly_corpus.juicios_identidad(refs, "solo_frontal", version="v", max_pares=5, ceros_por_consulta=2)
    assert all(len(c["relevancias"]) == 3 and 2 in c["relevancias"].values() for c in recortado["consultas"])
    with pytest.raises(ValueError, match="max_pairs"):
        _generar(fuente, tmp_path, "id", poor_variants=True, max_pairs=30)
    assert not (tmp_path / "pub-id").exists()


def test_cli_principal(fuente, tmp_path, capsys):
    pub, priv = tmp_path / "cp", tmp_path / "cq"
    codigo = plankassembly_corpus.main([
        "--source", str(fuente), "--public-output", str(pub), "--private-output", str(priv),
        "--seed", "3", "--train", "2", "--valid", "1", "--test", "2", "--source-revision", "d1d4308f0ee0aac2f9f407b3533ff83ecee22d34",
    ])
    assert codigo == 0
    manifiesto = json.loads(capsys.readouterr().out)
    assert manifiesto["source_revision"].startswith("d1d4308") and manifiesto["partitions"]["test"]["sampled"] == 2
    assert (priv / "juicios" / "juicios_test.json").exists()


def _fuente_con(tmp_path: Path, modelos: dict[str, tuple[str, dict]], nombre="src2") -> Path:
    root = tmp_path / nombre
    _escribir(root, modelos)
    return root


def test_familia_parametrica_no_colapsa_ni_se_encadena(tmp_path):
    # Anchos 600..640 cada 5 mm: la rejilla los propone, la verificación (tolerancia 2 mm) los separa.
    modelos = {}
    for i, ancho in enumerate(range(600, 645, 5)):
        particion = ("train", "train", "train", "valid", "test")[i % 5]
        modelos[f"fam_{ancho}.json"] = (particion, _mueble(ancho, 300, 1800, 3))
    # Casi duplicado real (1 mm) de un train (605), en test: sí debe descartarse.
    modelos["casi_dup.json"] = ("test", _mueble(601, 300, 1800, 3))
    root = _fuente_con(tmp_path, modelos)
    _, priv, _ = _generar(root, tmp_path, sizes={"train": 50, "valid": 50, "test": 50})
    audit = _json(priv / "audit.json")
    assert audit["dropped_cross_split"]["test"] == ["casi_dup.json"]
    assert audit["dropped_cross_split"]["valid"] == [] and audit["dropped_within_split_duplicate"]["train"] == []
    assert audit["partitions"]["train"]["available"] == 6 and audit["partitions"]["valid"]["available"] == 2
    assert audit["partitions"]["test"]["available"] == 1
    assert audit["duplicate_groups"]["size_distribution"] == {"1": 8, "2": 1}
    assert audit["duplicate_groups"]["largest_group"] == 2


def test_escalado_isotropo_verificado_y_anisotropo_rechazado(tmp_path):
    modelos = {
        "a.json": ("train", _mueble(800, 300, 1800, 3)),
        "a_x1_5.json": ("test", _mueble(800, 300, 1800, 3, escala=1.5)),  # copia reescalada: duplicado
        "b_ancho.json": ("test", _mueble(1000, 300, 1800, 3)),  # otro ancho con el mismo grosor: no lo es
    }
    _, priv, _ = _generar(_fuente_con(tmp_path, modelos), tmp_path, sizes={"train": 5, "valid": 5, "test": 5})
    assert _json(priv / "audit.json")["dropped_cross_split"]["test"] == ["a_x1_5.json"]


def test_grupos_grandes_avisan_o_fallan(tmp_path):
    modelos = {f"cad_{ancho}.json": ("train", _mueble(ancho, 300, 1800, 3)) for ancho in range(600, 615)}
    root = _fuente_con(tmp_path, modelos)
    modelos_test = {**modelos, "t.json": ("test", _mueble(700, 300, 1800, 3))}
    root = _fuente_con(tmp_path, modelos_test, "src3")
    _, priv, _ = _generar(root, tmp_path, "w", sizes={"train": 20, "valid": 1, "test": 1}, max_group_size=5)
    audit = _json(priv / "audit.json")
    assert audit["duplicate_groups"]["largest_group"] == 15
    assert any("15" in w for w in audit["warnings"])
    with pytest.raises(ValueError, match="group"):
        _generar(root, tmp_path, "estricto", sizes={"train": 20, "valid": 1, "test": 1}, max_group_size=5, strict_groups=True)
    assert not (tmp_path / "pub-estricto").exists()
