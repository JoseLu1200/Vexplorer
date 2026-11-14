import hashlib
import json
import shutil
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
    kw.setdefault("salt", "sal-fija-de-pruebas")
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
    assert audit["duplicate_groups"]["cross_partition_models_dropped"] == 2
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
    # sin la sal privada los ids no se reconstruyen: otra sal da otros ids
    otros = {c["id"] for c in _json(_generar(fuente, tmp_path, "otra", poor_variants=True, salt="otra-sal")[0] / "cases.json")}
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
    with pytest.raises(ValueError, match="inside a Git repository"):
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
    assert audit["duplicate_groups"]["size_distribution"] == {"1": 10}  # los grupos son por partición
    assert audit["duplicate_groups"]["largest_group"] == 1


def test_escalado_isotropo_verificado_y_anisotropo_rechazado(tmp_path):
    modelos = {
        "a.json": ("train", _mueble(800, 300, 1800, 3)),
        "a_x1_5.json": ("test", _mueble(800, 300, 1800, 3, escala=1.5)),  # copia reescalada: duplicado
        "b_ancho.json": ("test", _mueble(1000, 300, 1800, 3)),  # otro ancho con el mismo grosor: no lo es
    }
    _, priv, _ = _generar(_fuente_con(tmp_path, modelos), tmp_path, sizes={"train": 5, "valid": 5, "test": 5})
    assert _json(priv / "audit.json")["dropped_cross_split"]["test"] == ["a_x1_5.json"]


def test_grupos_grandes_avisan_o_fallan(tmp_path):
    modelos = {f"cad_{i:02d}.json": ("train", _mueble(700, 300, 1800, 3)) for i in range(15)}
    modelos["t.json"] = ("test", _mueble(1000, 450, 900, 2))
    root = _fuente_con(tmp_path, modelos, "src3")
    _, priv, _ = _generar(root, tmp_path, "w", sizes={"train": 20, "valid": 1, "test": 1}, max_group_size=5)
    audit = _json(priv / "audit.json")
    assert audit["duplicate_groups"]["largest_group"] == 15
    assert any("15" in w for w in audit["warnings"])
    with pytest.raises(ValueError, match="group"):
        _generar(root, tmp_path, "estricto", sizes={"train": 20, "valid": 1, "test": 1}, max_group_size=5, strict_groups=True)
    assert not (tmp_path / "pub-estricto").exists()


def test_destinos_dentro_de_cualquier_repositorio_git_se_rechazan(fuente, tmp_path):
    repo = tmp_path / "otro_repo"
    (repo / ".git").mkdir(parents=True)
    with pytest.raises(ValueError, match="inside a Git repository"):
        generar_corpus(fuente, repo / "out" / "pub", tmp_path / "priv-fuera")
    with pytest.raises(ValueError, match="inside a Git repository"):
        generar_corpus(fuente, tmp_path / "pub-fuera", repo / "sub" / "priv")
    assert not (repo / "out").exists() and not (tmp_path / "pub-fuera").exists()


def test_worktree_rechaza_el_repositorio_principal(fuente, tmp_path, monkeypatch):
    principal = tmp_path / "principal"
    gitdir = principal / ".git" / "worktrees" / "wt"
    gitdir.mkdir(parents=True)
    (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
    arbol = tmp_path / "fuera" / "wt"
    arbol.mkdir(parents=True)
    (arbol / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    assert principal.resolve() in plankassembly_corpus._raices_de_repositorio(arbol)
    assert arbol.resolve() in plankassembly_corpus._raices_de_repositorio(arbol / "carpeta")
    monkeypatch.setattr(plankassembly_corpus, "REPO_ROOT", arbol)
    # Un destino bajo el repositorio principal (carpeta no ignorada) se rechaza aunque no cuelgue del worktree.
    with pytest.raises(ValueError, match="inside a Git repository"):
        generar_corpus(fuente, principal / "datos" / "pub", tmp_path / "priv-x")
    with pytest.raises(ValueError, match="inside a Git repository"):
        generar_corpus(fuente, arbol / "pub", tmp_path / "priv-x")


def test_fallo_al_publicar_privado_limpia_el_publico(fuente, tmp_path, monkeypatch):
    original = Path.rename

    def rename(self, destino):
        if Path(destino).name == "priv-fallo":
            raise OSError("fallo simulado")
        return original(self, destino)

    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(OSError, match="simulado"):
        generar_corpus(fuente, tmp_path / "pub-fallo", tmp_path / "priv-fallo", sizes={"test": 1})
    assert not (tmp_path / "pub-fallo").exists() and not (tmp_path / "priv-fallo").exists()
    assert not list(tmp_path.glob("*.partial-*"))


# ------------------------------------------------------------ ronda 2: sal, clustering, traslación


def test_sal_secreta_los_ids_no_se_reconstruyen_con_la_semilla(fuente, tmp_path):
    pub, priv, _ = _generar(fuente, tmp_path, poor_variants=True, salt="sal-privada-aleatoria", seed=20261114)
    ids = {c["id"] for c in _json(pub / "cases.json")}
    # Esquema anterior (derivado de la semilla): ningún id coincide, para cualquier partición/posición/tipo.
    candidatos = set()
    for semilla in ("20261114", "7"):
        for particion in ("train", "valid", "test"):
            for posicion in range(1, 30):
                for tipo in ("completa", "solo_frontal", "frontal_y_planta"):
                    candidatos.add("pa-" + hashlib.sha256(f"{semilla}|case-id|{particion}|{posicion}|{tipo}".encode()).hexdigest()[:12])
    assert not ids & candidatos
    assert not ids & {plankassembly_corpus._id_opaco("otra-sal", p, n, t) for p in ("train", "valid", "test") for n in range(1, 30) for t in ("completa", "solo_frontal")}
    assert _json(priv / "manifest.json")["salt"] == "sal-privada-aleatoria"
    assert "sal-privada-aleatoria" not in "".join(p.read_text(errors="ignore") for p in pub.rglob("*.json"))
    # misma sal => mismos bytes; otra sal => otros ids y mismo muestreo
    otra = _generar(fuente, tmp_path, "otra", poor_variants=True, salt="otra-sal", seed=20261114)
    assert not ids & {c["id"] for c in _json(otra[0] / "cases.json")}
    fuentes = lambda p: sorted(r["source_file"] for r in _json(p / "references.json") if r["variant_of"] is None)
    assert fuentes(priv) == fuentes(otra[1])
    repetida = _generar(fuente, tmp_path, "rep", poor_variants=True, salt="sal-privada-aleatoria", seed=20261114)
    assert _arbol(repetida[0]) == _arbol(pub) and _arbol(repetida[1]) == _arbol(priv)


def test_sin_sal_se_genera_una_aleatoria_privada(fuente, tmp_path):
    a = _generar(fuente, tmp_path, "a", salt=None)
    b = _generar(fuente, tmp_path, "b", salt=None)
    sal_a, sal_b = (_json(x[1] / "manifest.json")["salt"] for x in (a, b))
    assert len(sal_a) >= 32 and sal_a != sal_b
    assert not {c["id"] for c in _json(a[0] / "cases.json")} & {c["id"] for c in _json(b[0] / "cases.json")}
    assert sal_a not in "".join(p.read_text(errors="ignore") for p in a[0].rglob("*.json"))


def test_cli_salt_file(fuente, tmp_path, capsys):
    sal = tmp_path / "sal.txt"
    sal.write_text("sal-desde-archivo\n", encoding="utf-8")
    argv = ["--source", str(fuente), "--seed", "3", "--train", "2", "--valid", "1", "--test", "2", "--salt-file", str(sal)]
    assert plankassembly_corpus.main([*argv, "--public-output", str(tmp_path / "p1"), "--private-output", str(tmp_path / "q1")]) == 0
    assert plankassembly_corpus.main([*argv, "--public-output", str(tmp_path / "p2"), "--private-output", str(tmp_path / "q2")]) == 0
    capsys.readouterr()
    assert _json(tmp_path / "q1" / "manifest.json")["salt"] == "sal-desde-archivo"
    assert _arbol(tmp_path / "p1") == _arbol(tmp_path / "p2")


def _distancia(a: float, b: float) -> float:
    return abs(a - b)


def _diametros(audit, anchos_por_archivo):
    """Máxima diferencia de ancho (única dimensión que varía en estas familias) dentro de cada clúster."""
    return [
        max(anchos_por_archivo[x] for x in miembros) - min(anchos_por_archivo[x] for x in miembros)
        for miembros in audit["duplicate_clusters"].values()
    ]


def test_paso_de_1_mm_no_colapsa_en_cadena(tmp_path):
    anchos = list(range(600, 801))
    modelos = {}
    anchos_por_archivo = {}
    for ancho in anchos:
        particion = "train" if ancho < 700 else ("valid" if ancho < 750 else "test")
        nombre = f"w_{ancho}.json"
        modelos[nombre] = (particion, _mueble(ancho, 300, 1800, 3))
        anchos_por_archivo[nombre] = ancho
    root = _fuente_con(tmp_path, modelos, "paso1")
    _, priv, _ = _generar(root, tmp_path, sizes={"train": 500, "valid": 500, "test": 500})
    audit = _json(priv / "audit.json")
    tolerancia = audit["duplicate_groups"]["tolerance_mm"]
    assert max(_diametros(audit, anchos_por_archivo)) <= tolerancia  # clique: sin cadenas
    disponibles = {p: v["available"] for p, v in audit["partitions"].items()}
    assert disponibles["valid"] > 5 and disponibles["test"] > 5 and disponibles["train"] > 20
    assert audit["duplicate_groups"]["largest_group"] <= tolerancia + 1
    # un superviviente de valid/test nunca está a <= tolerancia de un superviviente de una partición prioritaria
    refs = [r for r in _json(priv / "references.json")]
    por_particion = {}
    for r in refs:
        por_particion.setdefault(r["partition"], []).append(anchos_por_archivo[r["source_file"]])
    for menor, mayor in (("valid", "train"), ("test", "train"), ("test", "valid")):
        assert all(_distancia(a, b) > tolerancia for a in por_particion[menor] for b in por_particion[mayor])


def test_trescientos_anchos_aleatorios_no_colapsan(tmp_path):
    import random
    rnd = random.Random(2026)
    modelos = {}
    anchos_por_archivo = {}
    for i in range(300):
        ancho = 600 + rnd.random() * 200  # continuos
        particion = rnd.choices(("train", "valid", "test"), weights=(6, 2, 2))[0]
        nombre = f"r_{i:03d}.json"
        modelos[nombre] = (particion, _mueble(round(ancho, 3), 300, 1800, 3))
        anchos_por_archivo[nombre] = round(ancho, 3)
    root = _fuente_con(tmp_path, modelos, "aleatorios")
    _, priv, _ = _generar(root, tmp_path, sizes={"train": 500, "valid": 500, "test": 500})
    audit = _json(priv / "audit.json")
    tolerancia = audit["duplicate_groups"]["tolerance_mm"]
    assert max(_diametros(audit, anchos_por_archivo), default=0) <= tolerancia
    assert audit["duplicate_groups"]["largest_group"] <= 10
    disponibles = {p: v["available"] for p, v in audit["partitions"].items()}
    assert disponibles["valid"] >= 3 and disponibles["test"] >= 3, disponibles


def test_grupos_grandes_son_visibles_en_manifiesto_y_cli(tmp_path, capsys):
    # Cientos de copias idénticas: no son una cadena, pero el tamaño debe avisarse.
    modelos = {f"id_{i}.json": ("train", _mueble(700, 300, 1800, 3)) for i in range(8)}
    modelos["t.json"] = ("test", _mueble(1000, 450, 900, 2))
    root = _fuente_con(tmp_path, modelos, "ident")
    argv = ["--source", str(root), "--public-output", str(tmp_path / "pp"), "--private-output", str(tmp_path / "qq"),
            "--train", "5", "--valid", "1", "--test", "1", "--max-group-size", "3"]
    assert plankassembly_corpus.main(argv) == 0
    capturado = capsys.readouterr()
    assert "largest duplicate group" in capturado.err
    assert _json(tmp_path / "qq" / "manifest.json")["audit_warnings"]


def _puntos(dxf: Path, capa: str):
    doc = ezdxf.readfile(dxf)
    puntos = []
    for e in doc.modelspace().query("LINE"):
        if e.dxf.layer == capa:
            puntos += [(round(e.dxf.start.x, 6), round(e.dxf.start.y, 6)), (round(e.dxf.end.x, 6), round(e.dxf.end.y, 6))]
    return puntos


def test_variantes_con_traslacion_privada_que_no_cambia_medidas(fuente, tmp_path):
    pub, priv, _ = _generar(fuente, tmp_path, poor_variants=True)
    refs = _refs_por_id(priv)
    casos = {c["id"]: c for c in _json(pub / "cases.json")}
    variantes = [r for r in refs.values() if r["variant_of"]]
    desplazamientos = set()
    for r in variantes:
        capa = {"solo_frontal": "ORTHO_FRONT", "frontal_y_planta": "ORTHO_FRONT"}[r["poor_kind"]]
        base = _puntos(pub / casos[r["variant_of"]]["file"], capa)
        var = _puntos(pub / casos[r["id"]]["file"], capa)
        assert set(var) != set(base) and not set(var) & set(base)  # ya no hay coincidencia exacta de coordenadas
        dx, dy = r["view_translation_mm"]["front"]
        assert sorted((round(x + dx, 6), round(y + dy, 6)) for x, y in base) == sorted(var)  # solo traslación: mismas medidas
        assert set(r["view_translation_mm"]) == ({"front"} if r["poor_kind"] == "solo_frontal" else {"front", "top"})
        desplazamientos.add((r["poor_kind"], dx, dy))
    assert len(desplazamientos) == len(variantes)  # cada variante, su propio desplazamiento
    # determinista con la misma sal; distinto con otra sal
    otra = _generar(fuente, tmp_path, "otra-sal", poor_variants=True, salt="otra")
    otras = [r["view_translation_mm"] for r in _refs_por_id(otra[1]).values() if r["variant_of"]]
    assert otras != [r["view_translation_mm"] for r in variantes]
    assert "view_translation_mm" not in "".join(p.read_text(errors="ignore") for p in pub.rglob("*.json"))


def test_identidad_con_ceros_conserva_los_mas_cercanos(fuente, tmp_path):
    _, priv, _ = _generar(fuente, tmp_path, poor_variants=True, zeros_per_query=2)
    refs = _refs_por_id(priv)
    for c in _json(priv / "juicios" / "juicios_identidad_solo_frontal.json")["consultas"]:
        ceros = [k for k, g in c["relevancias"].items() if g == 0]
        assert len(ceros) == 2
        consulta = refs[refs[c["consulta_id"]]["variant_of"]]
        def distancia(cid, consulta=consulta):
            r = refs[cid]
            r = refs[r["variant_of"]] if r["variant_of"] else r
            return plankassembly_corpus._metricas_par(consulta, r)[1]
        excluidos = [k for k in refs if k not in c["relevancias"] and k != c["consulta_id"]
                     and not refs[k]["variant_of"] and k != refs[c["consulta_id"]]["variant_of"]]
        assert all(distancia(z) <= distancia(e) + 1e-12 for z in ceros for e in excluidos)


# ------------------------------------------------------------ comparativa A/B/C/D


def test_comparativa_lee_el_corpus_de_extremo_a_extremo(fuente, tmp_path):
    from evaluation.comparativa import (
        PlankAssemblyCorpusReader,
        ReferenceNotFrozen,
        build_methods,
        execute_run,
        score_run,
    )

    pub, priv, _ = _generar(fuente, tmp_path, poor_variants=True, poor_partitions=("train", "valid", "test"))
    public_rows = _json(pub / "cases.json")
    assert all({"family_hash", "group_id", "split"}.isdisjoint(row) for row in public_rows)

    class Espia(PlankAssemblyCorpusReader):
        lecturas_privadas = 0

        def _read_private(self):
            Espia.lecturas_privadas += 1
            return super()._read_private()

    reader = Espia(pub, priv, tmp_path / "staging")
    metas = reader.case_meta()
    assert {m.split for m in metas.values()} == {"train", "valid", "test"}
    assert {m.partition_id for m in metas.values()}.isdisjoint({"train", "valid", "test"})
    # Misma partición oficial, mismo partition_id; nunca un identificador de grupo privado.
    por_particion: dict[str, set[str]] = {}
    for meta in metas.values():
        por_particion.setdefault(meta.split, set()).add(meta.partition_id)
    assert all(len(ids) == 1 for ids in por_particion.values()) and len(por_particion) == 3
    privados = {str(r.get(k)) for r in _json(priv / "references.json") for k in ("group_id", "family_hash", "exact_hash")}
    assert not privados & {m.partition_id for m in metas.values()}

    with pytest.raises(ReferenceNotFrozen):
        score_run(reader, tmp_path / "run")
    run_dir = tmp_path / "run"
    execute_run(reader, build_methods(("A",)), run_dir)
    assert Espia.lecturas_privadas == 0  # ejecutar y congelar no abre lo privado
    report = score_run(reader, run_dir)
    assert Espia.lecturas_privadas == 1
    assert report["corpus"]["id"] == "plankassembly-corpus"
    assert "family_hash" not in json.dumps(report["corpus"])
    puntuados = [
        split for family in report["variants"]["A"]["families"].values() for split in family.values()
    ]
    assert {c for c in ("train", "valid", "test")} == {
        name for family in report["variants"]["A"]["families"].values() for name in family
    }
    assert sum(split["sample"]["cases"] for split in puntuados) == len(public_rows)
    # Todas las referencias (también las de variantes pobres, que heredan la de su caso base) se adaptan.
    referencias = reader._read_private()
    assert set(referencias) == {row["id"] for row in public_rows}
    assert all(ref is not None and ref.components for ref in referencias.values())
    base_de = {r["id"]: r["variant_of"] for r in _json(priv / "references.json") if r["variant_of"]}
    assert base_de
    for variante, base in base_de.items():
        assert referencias[variante].components == referencias[base].components


def test_comparativa_cli_con_corpus(fuente, tmp_path):
    from tools.comparativa_metodos import main as cli_main

    pub, priv, _ = _generar(fuente, tmp_path)
    run_dir = tmp_path / "run-cli"
    codigo = cli_main([
        "run", "--corpus", "plankassembly-corpus", "--public-dir", str(pub), "--private-dir", str(priv),
        "--run-dir", str(run_dir),
    ])
    assert codigo == 0
    assert (run_dir / "report.json").is_file()


# ------------------------------------------------------------ biblioteca para los juicios


def _descriptores_publicos(pub: Path, ids, version="furniture-v1") -> dict[str, dict]:
    """Descriptores de prueba derivados solo del id público (un extractor real leería los DXF públicos)."""
    publicos = {fila["id"] for fila in _json(pub / "cases.json")}
    assert set(ids) <= publicos
    salida = {}
    for case_id in ids:
        n = int(hashlib.sha256(case_id.encode()).hexdigest()[:6], 16)
        salida[case_id] = {
            "descriptor_version": version, "family": "unknown",
            "dimensions": {"width_mm": 500 + n % 700, "depth_mm": 300 + n % 200, "height_mm": 800 + n % 1100},
            "roles": [], "structure": "unknown", "unknown_fields": [],
        }
    return salida


def test_biblioteca_de_juicios_para_cada_archivo_del_corpus(fuente, tmp_path, capsys):
    from tools import biblioteca_juicios

    pub, priv, _ = _generar(fuente, tmp_path, poor_variants=True)
    bibliotecas = _json(priv / "juicios" / "bibliotecas.json")
    assert len(bibliotecas) > 1 and any(c["run_id_overrides"] for c in bibliotecas.values())
    for archivo, contrato in bibliotecas.items():
        descriptores = tmp_path / f"desc-{archivo}"
        descriptores.write_text(json.dumps(_descriptores_publicos(pub, contrato["case_ids"])), encoding="utf-8")
        salida = tmp_path / f"bib-{archivo}"
        assert biblioteca_juicios.main([
            "--privado", str(priv), "--publico", str(pub), "--juicios", archivo,
            "--descriptores", str(descriptores), "--salida", str(salida),
        ]) == 0
        items = evaluar_recuperacion.cargar_biblioteca(salida)
        assert sorted(i.id for i in items) == sorted(contrato["case_ids"])
        assert all(i.run_id == contrato["run_id_overrides"].get(i.id, i.id) for i in items)
        assert len({i.descriptor.descriptor_version for i in items}) == 1
        capsys.readouterr()
        rc = evaluar_recuperacion.main(["--biblioteca", str(salida), "--juicios", str(priv / "juicios" / archivo), "--k", "3"])
        informe = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert informe["advertencias"] == []  # biblioteca densa respecto a sus juicios


def test_biblioteca_de_juicios_rechaza_entradas_incoherentes(fuente, tmp_path, capsys):
    from tools import biblioteca_juicios

    pub, priv, _ = _generar(fuente, tmp_path, poor_variants=True)
    contrato = _json(priv / "juicios" / "bibliotecas.json")["juicios_test.json"]
    ids = contrato["case_ids"]
    base = ["--privado", str(priv), "--publico", str(pub), "--juicios", "juicios_test.json", "--salida", str(tmp_path / "s.json")]

    def ejecutar(descriptores: dict, donde: Path) -> int:
        donde.write_text(json.dumps(descriptores), encoding="utf-8")
        return biblioteca_juicios.main([*base, "--descriptores", str(donde)])

    completos = _descriptores_publicos(pub, ids)
    assert ejecutar({k: v for k, v in list(completos.items())[1:]}, tmp_path / "falta.json") == 2
    assert ejecutar({**completos, "pa-inexistente": next(iter(completos.values()))}, tmp_path / "sobra.json") == 2
    mixtos = dict(completos)
    mixtos[ids[0]] = {**mixtos[ids[0]], "descriptor_version": "furniture-v2", "thicknesses_mm": [], "classification_status": "hypothesis"}
    assert ejecutar(mixtos, tmp_path / "mixtos.json") == 2
    assert ejecutar(completos, priv / "descriptores.json") == 2  # dentro del directorio privado
    assert ejecutar(completos, tmp_path / "bien.json") == 0
    assert capsys.readouterr().err.count('"error"') == 4
    # Un archivo de juicios desconocido falla.
    assert biblioteca_juicios.main([*base[:2], *base[2:4], "--juicios", "otro.json", "--descriptores", str(tmp_path / "bien.json"), "--salida", base[-1]]) == 2


def test_escala_cercana_es_simetrica():
    from tools.plankassembly_corpus import ModeloAnalizado, _cercanos, _escala_cercana

    def make_model(name: str, dims: tuple[tuple[float, ...], ...], mayor: float) -> ModeloAnalizado:
        return ModeloAnalizado(
            filename=name,
            partition="train",
            sha256="abc",
            fisicas=(),
            has_normal=False,
            exact_hash="ex",
            family_hash="fam",
            claves=(),
            dims=dims,
            mayor=mayor,
            features={},
            categoria=None,
            model={},
        )

    # a has mayor 1000 and plank dim 100.
    # b has mayor 2000 and plank dim 203.
    # Forward check: factor = 2000 / 1000 = 2.0. 100 * 2.0 = 200. abs(200 - 203) = 3.0.
    # Backward check: factor = 1000 / 2000 = 0.5. 203 * 0.5 = 101.5. abs(101.5 - 100) = 1.5.
    # With tolerance_mm = 2.0: forward residual is 3.0 > 2.0 (False), backward residual is 1.5 <= 2.0 (True).
    # Symmetric check requires both, so both must evaluate to False.
    a = make_model("a.json", ((100.0, 500.0, 1000.0),), 1000.0)
    b = make_model("b.json", ((203.0, 1000.0, 2000.0),), 2000.0)

    assert _escala_cercana(a, b, 2.0) == _escala_cercana(b, a, 2.0)
    assert _escala_cercana(a, b, 2.0) is False
    assert _cercanos(a, b, 2.0) == _cercanos(b, a, 2.0)
    assert _cercanos(a, b, 2.0) is False

    c = make_model("c.json", ((200.0, 1000.0, 2000.0),), 2000.0)
    assert _escala_cercana(a, c, 2.0) is True
    assert _escala_cercana(c, a, 2.0) is True
    assert _cercanos(a, c, 2.0) is True
    assert _cercanos(c, a, 2.0) is True


def test_auditar_universo_deduplica_en_misma_particion(tmp_path: Path):
    root = tmp_path / "src_same_part"
    model_dir = root / "extracted" / "data" / "model"
    split_dir = root / "extracted" / "data" / "splits"
    model_dir.mkdir(parents=True)
    split_dir.mkdir(parents=True)

    def write_model(nombre: str, thickness: float):
        planks = [
            [0, 0, 0, 1000, 500, 700],  # envelope
            [0, 0, 0, thickness, 500, 700],
            [980, 0, 0, 1000, 500, 700],
        ]
        attach = [[-1] * 6, [0, 1, 2, -1, 4, 5], [-1, -1, 2, -1, 4, 5]]
        (model_dir / nombre).write_text(json.dumps({"planks": planks, "attach": attach}), encoding="utf-8")

    # A: 10.0, X: 11.8 (|A-X|=1.8<=2.0), B: 8.2 (|B-A|=1.8<=2.0, |B-X|=3.6>2.0).
    # Clique clustering groups [A, X] in cluster 0 (rep A).
    # B cannot join [A, X] so it forms cluster 1 (rep B).
    # Same-partition audit checks B against accepted finales (A), finds it close, and drops B into dentro["train"].
    write_model("m_a.json", 10.0)
    write_model("m_x.json", 11.8)
    write_model("m_b.json", 8.2)

    (split_dir / "train.txt").write_text("m_a.json\nm_x.json\nm_b.json\n", encoding="utf-8")
    (split_dir / "valid.txt").write_text("", encoding="utf-8")
    (split_dir / "test.txt").write_text("", encoding="utf-8")

    supervivientes, audit = plankassembly_corpus.auditar_universo(root, tolerancia_mm=2.0)
    assert [m.filename for m in supervivientes] == ["m_a.json"]
    assert "m_b.json" in audit["dropped_within_split_duplicate"]["train"]
    assert "m_x.json" in audit["dropped_within_split_duplicate"]["train"]


def test_leer_particiones_rechaza_symlink(tmp_path: Path, monkeypatch):
    root = tmp_path / "src_symlink"
    model_dir = root / "extracted" / "data" / "model"
    split_dir = root / "extracted" / "data" / "splits"
    model_dir.mkdir(parents=True)
    split_dir.mkdir(parents=True)

    target = model_dir / "real.json"
    target.write_text(json.dumps({"planks": [[0, 0, 0, 10, 10, 10], [0, 0, 0, 1, 1, 1]], "attach": [[-1]*6, [-1]*6]}), encoding="utf-8")
    link = model_dir / "symlink.json"
    try:
        link.symlink_to(target)
        (split_dir / "train.txt").write_text("symlink.json\n", encoding="utf-8")
        (split_dir / "valid.txt").write_text("", encoding="utf-8")
        (split_dir / "test.txt").write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="symlink rejected"):
            plankassembly_corpus._leer_particiones(root)
    except OSError:
        pass

    (split_dir / "train.txt").write_text("real.json\n", encoding="utf-8")
    (split_dir / "valid.txt").write_text("", encoding="utf-8")
    (split_dir / "test.txt").write_text("", encoding="utf-8")

    monkeypatch.setattr(Path, "is_symlink", lambda self: True)
    with pytest.raises(ValueError, match="symlink rejected"):
        plankassembly_corpus._leer_particiones(root)


def test_biblioteca_juicios_validaciones_adicionales(fuente, tmp_path, capsys):
    from tools import biblioteca_juicios

    pub, priv, _ = _generar(fuente, tmp_path, poor_variants=True)
    contrato = _json(priv / "juicios" / "bibliotecas.json")["juicios_test.json"]
    ids = contrato["case_ids"]
    descriptores = _descriptores_publicos(pub, ids)

    # 1. privado.resolve() == publico.resolve()
    with pytest.raises(ValueError, match="distintos"):
        biblioteca_juicios.construir_biblioteca(pub, pub, "juicios_test.json", descriptores)

    # 2. bool(case_ids) == False
    priv_vacio = tmp_path / "priv_vacio"
    shutil.copytree(priv, priv_vacio)
    bj = _json(priv_vacio / "juicios" / "bibliotecas.json")
    bj["juicios_test.json"]["case_ids"] = []
    (priv_vacio / "juicios" / "bibliotecas.json").write_text(json.dumps(bj), encoding="utf-8")
    with pytest.raises(ValueError, match="vacío"):
        biblioteca_juicios.construir_biblioteca(priv_vacio, pub, "juicios_test.json", descriptores)

    # 3. isinstance(overrides, dict)
    priv_bad_overrides = tmp_path / "priv_bad_ov"
    shutil.copytree(priv, priv_bad_overrides)
    bj_bad = _json(priv_bad_overrides / "juicios" / "bibliotecas.json")
    bj_bad["juicios_test.json"]["run_id_overrides"] = "not-a-dict"
    (priv_bad_overrides / "juicios" / "bibliotecas.json").write_text(json.dumps(bj_bad), encoding="utf-8")
    with pytest.raises(TypeError, match="diccionario"):
        biblioteca_juicios.construir_biblioteca(priv_bad_overrides, pub, "juicios_test.json", descriptores)

    # 4. set(overrides.values()) <= set(case_ids)
    priv_bad_values = tmp_path / "priv_bad_vals"
    shutil.copytree(priv, priv_bad_values)
    bj_vals = _json(priv_bad_values / "juicios" / "bibliotecas.json")
    bj_vals["juicios_test.json"]["run_id_overrides"] = {ids[0]: "id-fantasma-fuera-de-case-ids"}
    (priv_bad_values / "juicios" / "bibliotecas.json").write_text(json.dumps(bj_vals), encoding="utf-8")
    with pytest.raises(ValueError, match="valores de run_id_overrides"):
        biblioteca_juicios.construir_biblioteca(priv_bad_values, pub, "juicios_test.json", descriptores)

    # 5. unit == "mm" en cases.json
    pub_bad_unit = tmp_path / "pub_bad_unit"
    shutil.copytree(pub, pub_bad_unit)
    cases = _json(pub_bad_unit / "cases.json")
    cases[0]["unit"] = "meters"
    (pub_bad_unit / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    with pytest.raises(ValueError, match="unit == 'mm'"):
        biblioteca_juicios.construir_biblioteca(priv, pub_bad_unit, "juicios_test.json", descriptores)

    # 6. main() validación de --salida (dentro de publico, dentro de privado, o en repo git)
    desc_path = tmp_path / "desc.json"
    desc_path.write_text(json.dumps(descriptores), encoding="utf-8")

    # Salida dentro de publico
    rc = biblioteca_juicios.main([
        "--privado", str(priv), "--publico", str(pub), "--juicios", "juicios_test.json",
        "--descriptores", str(desc_path), "--salida", str(pub / "out.json")
    ])
    assert rc == 2
    # Salida dentro de privado
    rc = biblioteca_juicios.main([
        "--privado", str(priv), "--publico", str(pub), "--juicios", "juicios_test.json",
        "--descriptores", str(desc_path), "--salida", str(priv / "out.json")
    ])
    assert rc == 2
    # Salida en repositorio Git
    rc = biblioteca_juicios.main([
        "--privado", str(priv), "--publico", str(pub), "--juicios", "juicios_test.json",
        "--descriptores", str(desc_path), "--salida", str(plankassembly_corpus.REPO_ROOT / "out.json")
    ])
    assert rc == 2


def test_evaluar_recuperacion_validaciones(fuente, tmp_path):
    from tools import evaluar_recuperacion
    from backend.app.precedentes.evaluacion import ConjuntoJuicios

    pub, priv, _ = _generar(fuente, tmp_path)
    juicios = ConjuntoJuicios.model_validate_json((priv / "juicios" / "juicios_test.json").read_text(encoding="utf-8"))

    # 1. _validar_k
    with pytest.raises(ValueError, match="k debe ser un entero >= 1"):
        evaluar_recuperacion.evaluar((), juicios, 0, "geometrico")
    with pytest.raises(ValueError, match="k debe ser un entero >= 1"):
        evaluar_recuperacion.evaluar((), juicios, -5, "geometrico")

    # 2. metodo in METODOS
    with pytest.raises(ValueError, match="método desconocido"):
        evaluar_recuperacion.evaluar((), juicios, 5, "metodo_fantasma")

    # 3. not metricas (biblioteca vacía: ninguna consulta encontrada)
    with pytest.raises(ValueError, match="no se ha evaluado ninguna consulta"):
        evaluar_recuperacion.evaluar((), juicios, 5, "geometrico")

    # 4. ranking_consulta con score no finito
    from backend.app.contratos.modelos import LibraryItem
    from backend.tests.test_precedentes_evaluacion import _item

    consulta = LibraryItem.model_validate(_item("q", "r0", 800, 1800, 4))
    candidatos = (LibraryItem.model_validate(_item("c1", "r1", 800, 1800, 4)),)

    def ranqueador_nan(c, cands):
        return ((cands[0].id, float("nan")),)

    with pytest.raises(ValueError, match="score no finito"):
        evaluar_recuperacion.ranking_consulta(consulta, candidatos, ranqueador_nan)

    def ranqueador_inf(c, cands):
        return ((cands[0].id, float("inf")),)

    with pytest.raises(ValueError, match="score no finito"):
        evaluar_recuperacion.ranking_consulta(consulta, candidatos, ranqueador_inf)

