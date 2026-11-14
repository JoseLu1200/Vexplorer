import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from tools.audit_production import AcceptanceConfig, run_production_acceptance


ROOT = Path(__file__).resolve().parents[1]


def _catalog_payload() -> dict:
    rows = (
        ("board-real", "Tablero", "material_area", "material", "50.005", "EUR/m2"),
        ("solid-real", "Macizo", "material_volume", "material", "1000", "EUR/m3"),
        ("edge-real", "Canto", "edge", "edge", "3", "EUR/m"),
        ("cut-real", "Mecanizado", "operation", "operation", "40", "EUR/h"),
        ("labor-real", "Mano de obra", "labor", "labor", "30", "EUR/h"),
        ("finish-real", "Acabado", "finish", "finishing", "10", "EUR/m2"),
        ("setup-real", "Preparación", "fixed", "preparation", "20", "EUR/unit"),
    )
    return {
        "schema_version": "0.6.0",
        "catalog_version": "acceptance-erp-2026-11",
        "source": "Fixture de aceptación que simula exportación ERP aprobada",
        "effective_date": "2026-11-01",
        "synthetic": False,
        "tariffs": [
            {
                "id": tariff_id,
                "label": label,
                "concept_type": concept_type,
                "scope": scope,
                "rate_eur_per_unit": rate,
                "rate_unit": unit,
                "synthetic": False,
            }
            for tariff_id, label, concept_type, scope, rate, unit in rows
        ],
    }


def _config(tmp_path: Path) -> AcceptanceConfig:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(_catalog_payload()), encoding="utf-8")
    return AcceptanceConfig(
        data_dir=tmp_path / "runtime",
        report_path=tmp_path / "acceptance-report.md",
        catalog_path=catalog,
        fixture_path=ROOT / "data" / "planos_demo" / "mesa_demo_001.dxf",
        conflict_fixture_path=ROOT / "data" / "planos_demo" / "mesa_demo_004.dxf",
        username="acceptance-auditor",
        password="fixture password never written in plaintext",
        poll_timeout_s=10,
    )


def test_offline_authenticated_workflow_survives_restart_and_blocks_negatives(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VEXPLORER_API_KEY", raising=False)

    result = run_production_acceptance(_config(tmp_path))

    checks = {item["id"]: item for item in result["checks"]}
    assert all(checks[name]["status"] == "PASS" for name in (
        "offline_geometry_only",
        "authentication_required",
        "named_reviewer_authority",
        "durable_job_restart",
        "review_drawings_cost_export",
        "dimension_conflict_blocks_completion",
    ))
    assert result["job"]["state"] == "succeeded"
    assert result["review"]["state"] == "completed"
    assert result["estimate"]["synthetic"] is False
    assert result["estimate"]["catalog_version"] == "acceptance-erp-2026-11"
    assert result["export"]["estimate"] == result["estimate"]
    assert result["restart"]["run_id"] == result["job"]["run_id"]
    assert result["conflict"]["state"] == "needs_review"
    assert _config(tmp_path).report_path.is_file()
    report = _config(tmp_path).report_path.read_text(encoding="utf-8")
    assert "fixture password" not in report
    assert result["provider_calls"] == []


def test_real_tariff_arithmetic_is_checked_independently_of_product_helpers(tmp_path: Path) -> None:
    result = run_production_acceptance(_config(tmp_path))
    estimate = result["estimate"]
    assert {
        concept["tariff_id"]
        for concept in estimate["concepts"]
        if concept["concept_type"] in {"material_area", "material_volume"}
    } == {"board-real", "solid-real"}
    rates = {
        "board-real": Decimal("50.005"),
        "solid-real": Decimal("1000"),
        "edge-real": Decimal("3"),
        "cut-real": Decimal("40"),
        "labor-real": Decimal("30"),
        "finish-real": Decimal("10"),
        "setup-real": Decimal("20"),
    }
    known_amounts = []
    for concept in estimate["concepts"]:
        if concept["state"] != "resolved":
            continue
        expected = (
            Decimal(str(concept["quantity"])) * rates[concept["tariff_id"]]
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert Decimal(str(concept["amount_eur"])) == expected
        known_amounts.append(expected)
    expected_subtotal = sum(known_amounts, Decimal("0.00"))
    assert Decimal(str(estimate["known_subtotal_eur"])) == expected_subtotal
    expected_sale = (expected_subtotal / Decimal("0.80")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    assert Decimal(str(estimate["provisional_sale_price_eur"])) == expected_sale


def test_acceptance_harness_can_repeat_against_the_same_runtime(tmp_path: Path) -> None:
    config = _config(tmp_path)

    first = run_production_acceptance(config)
    second = run_production_acceptance(config)

    assert first["job"]["id"] != second["job"]["id"]
    assert all(item["status"] == "PASS" for item in second["checks"])
