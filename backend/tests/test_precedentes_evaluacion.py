from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.precedentes.evaluacion import (
    ConjuntoJuicios,
    agregar,
    evaluar_consulta,
    ndcg_en_k,
    precision_en_k,
    rango_reciproco,
    recall_en_k,
)
from tools import evaluar_recuperacion

RAIZ = Path(__file__).resolve().parents[2]
JUICIOS_SINTETICOS = RAIZ / "evaluation" / "recuperacion" / "juicios_sinteticos.json"


def _item(item_id: str, run_id: str, ancho: float, alto: float, baldas: int, version: str = "furniture-v1") -> dict:
    descriptor = {
        "descriptor_version": "furniture-v1",
        "family": "rectangular_shelving",
        "dimensions": {"width_mm": ancho, "depth_mm": 300.0, "height_mm": alto},
        "roles": [{"role": "shelf", "quantity": baldas}, {"role": "side", "quantity": 2}],
        "structure": "top_base_between_sides",
        "unknown_fields": [],
    }
    if version == "furniture-v2":
        descriptor = {**descriptor, "descriptor_version": "furniture-v2", "thicknesses_mm": [18.0], "classification_status": "hypothesis"}
    return {"id": item_id, "run_id": run_id, "result_revision": 1, "label": item_id, "descriptor": descriptor, "descriptor_fingerprint": "0" * 64, "created_at": "2026-01-01T00:00:00+00:00"}


def _biblioteca() -> list[dict]:
    return [
        _item("sint-estanteria-1800", "run-a", 800, 1800, 4),
        _item("sint-estanteria-1850", "run-b", 800, 1850, 4),
        _item("sint-estanteria-2000", "run-c", 900, 2000, 5),
        _item("sint-mesa-750", "run-d", 1400, 750, 1),
    ]


def test_metricas_basicas() -> None:
    ranking = ("a", "b", "c", "d")
    rel = {"b": 2, "d": 1, "c": 0, "z": 1}
    assert precision_en_k(ranking, rel, 2) == 0.5
    assert precision_en_k(("b",), rel, 5) == pytest.approx(0.2)  # divide entre k
    assert recall_en_k(ranking, rel, 2) == pytest.approx(1 / 3)  # "z" juzgado pero ausente limita el recall
    assert rango_reciproco(ranking, rel) == 0.5
    assert rango_reciproco(("a", "c"), rel) == 0.0
    perfecto = ndcg_en_k(("b", "d", "z"), rel, 3)
    assert perfecto == pytest.approx(1.0)
    assert ndcg_en_k(ranking, rel, 3) < 1.0


def test_consulta_sin_relevantes_queda_indefinida_y_fuera_de_la_media() -> None:
    sin = evaluar_consulta("q1", ("a", "b"), {"a": 0}, 2)
    con = evaluar_consulta("q2", ("a", "b"), {"a": 2}, 2)
    assert sin.recall_k is None and sin.ndcg_k is None and sin.mrr is None
    assert sin.candidatos_sin_juicio == 1
    agregado = agregar((sin, con), 2)
    assert agregado.consultas_sin_relevantes == 1
    assert agregado.recall_k == 1.0 and agregado.ndcg_k == 1.0
    assert agregado.precision_k == pytest.approx(0.25)
    assert agregado.cobertura_juicios == pytest.approx(0.5)


def test_ranking_duplicado_y_k_invalido() -> None:
    with pytest.raises(ValueError):
        evaluar_consulta("q", ("a", "a"), {}, 1)
    with pytest.raises(ValueError):
        precision_en_k(("a",), {}, 0)


def test_formato_juicios_valida() -> None:
    base = {"version": "1", "origen": "synthetic", "descripcion": "x"}
    with pytest.raises(ValidationError):
        ConjuntoJuicios.model_validate({**base, "consultas": [{"consulta_id": "q", "relevancias": {"a": 3}}]})
    with pytest.raises(ValidationError):
        ConjuntoJuicios.model_validate({**base, "consultas": [{"consulta_id": "q", "relevancias": {}}, {"consulta_id": "q", "relevancias": {}}]})
    with pytest.raises(ValidationError):
        ConjuntoJuicios.model_validate({**base, "origen": "otro", "consultas": [{"consulta_id": "q", "relevancias": {}}]})
    with pytest.raises(ValidationError):
        ConjuntoJuicios.model_validate({**base, "consultas": [{"consulta_id": "q", "relevancias": {"q": 1}}]})


def test_juicios_sinteticos_publicados_son_validos() -> None:
    conjunto = ConjuntoJuicios.model_validate_json(JUICIOS_SINTETICOS.read_text(encoding="utf-8"))
    assert conjunto.origen == "synthetic"


def test_cli_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    items = _biblioteca() + [
        _item("sint-mismo-run", "run-a", 800, 1800, 4),
        _item("sint-v2", "run-e", 800, 1800, 4, version="furniture-v2"),
    ]
    biblioteca = tmp_path / "biblioteca.json"
    biblioteca.write_text(json.dumps({"items": items}), encoding="utf-8")
    codigo = evaluar_recuperacion.main(["--biblioteca", str(biblioteca), "--juicios", str(JUICIOS_SINTETICOS), "--k", "2"])
    assert codigo == 0
    informe = json.loads(capsys.readouterr().out)
    assert informe["origen_juicios"] == "synthetic" and informe["aviso"]
    por_consulta = {item["consulta_id"]: item for item in informe["por_consulta"]}
    assert por_consulta["sint-estanteria-1800"]["mrr"] == 1.0
    assert por_consulta["sint-mesa-750"]["recall_k"] is None
    exclusiones = {item["consulta_id"]: item for item in informe["exclusiones"]}
    assert exclusiones["sint-estanteria-1800"] == {"consulta_id": "sint-estanteria-1800", "misma_consulta": 1, "mismo_run": 1, "version_descriptor_distinta": 1}
    assert informe["agregadas"]["candidatos_sin_juicio"] > 0
    # Determinista: segunda ejecución idéntica.
    evaluar_recuperacion.main(["--biblioteca", str(biblioteca), "--juicios", str(JUICIOS_SINTETICOS), "--k", "2"])
    assert json.loads(capsys.readouterr().out) == informe


def test_cli_lista_y_advertencias(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    biblioteca = tmp_path / "b.json"
    biblioteca.write_text(json.dumps(_biblioteca()[:2] + [_item("sint-v2", "run-e", 800, 1800, 4, version="furniture-v2")]), encoding="utf-8")
    juicios = tmp_path / "j.json"
    juicios.write_text(json.dumps({"version": "1", "origen": "team_reviewed", "descripcion": "x", "consultas": [
        {"consulta_id": "sint-estanteria-1800", "relevancias": {"sint-estanteria-1850": 2, "fantasma": 1, "sint-v2": 1}},
        {"consulta_id": "no-existe", "relevancias": {}},
    ]}), encoding="utf-8")
    assert evaluar_recuperacion.main(["--biblioteca", str(biblioteca), "--juicios", str(juicios)]) == 0
    informe = json.loads(capsys.readouterr().out)
    assert informe["aviso"] is None
    assert len(informe["advertencias"]) == 3
    assert any("sint-v2" in item for item in informe["advertencias"])
    assert informe["por_consulta"][0]["recall_k"] == pytest.approx(1 / 3, abs=1e-6)


def test_cli_entrada_invalida(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    biblioteca = tmp_path / "b.json"
    biblioteca.write_text(json.dumps({"otra": 1}), encoding="utf-8")
    assert evaluar_recuperacion.main(["--biblioteca", str(biblioteca), "--juicios", str(JUICIOS_SINTETICOS)]) == 2
    assert "error" in capsys.readouterr().err


def test_ranking_empata_por_id() -> None:
    from backend.app.contratos.modelos import LibraryItem

    consulta = LibraryItem.model_validate(_item("q", "r0", 800, 1800, 4))
    gemelos = tuple(LibraryItem.model_validate(_item(nombre, f"r-{nombre}", 800, 1800, 4)) for nombre in ("zz", "aa", "mm"))
    ranking, _ = evaluar_recuperacion.ranking_consulta(consulta, gemelos, evaluar_recuperacion.METODOS["geometrico"])
    assert ranking == ("aa", "mm", "zz")
