from __future__ import annotations

from pathlib import Path
import sys

import pytest

from tools import audit_autonomous as module


def _config(tmp_path: Path, *, public: bool) -> module.AuditConfig:
    fixture = tmp_path / "case.dxf"
    fixture.write_bytes(b"public-dxf")
    return module.AuditConfig(
        base_url="http://127.0.0.1:8774",
        fixture=fixture,
        output=tmp_path / "report.json",
        username=None if public else "qa",
        password=None if public else "secret",
        origin=None,
        public=public,
    )


def test_public_cli_never_prompts_or_adds_basic_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _config(tmp_path, public=True)
    captured: list[module.AuditConfig] = []

    def no_credentials() -> tuple[str, str]:
        raise AssertionError("public mode must not prompt for credentials")

    def fake_run(value: module.AuditConfig) -> dict:
        captured.append(value)
        return {"status": "passed", "checks": []}

    monkeypatch.setattr(module, "_credentials", no_credentials)
    monkeypatch.setattr(module, "run_autonomous_acceptance", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_autonomous.py",
            "--public",
            "--base-url",
            config.base_url,
            "--fixture",
            str(config.fixture),
            "--output",
            str(config.output),
        ],
    )

    module.main()

    assert len(captured) == 1
    assert captured[0].public is True
    assert captured[0].username is None and captured[0].password is None
    audit = module.AutonomousAudit(captured[0])
    try:
        request = audit.client.build_request("GET", "api/v1/session")
        assert "authorization" not in request.headers
    finally:
        audit.close()
    assert '"status": "passed"' in capsys.readouterr().out


def test_public_mode_explicitly_skips_private_history_without_request(
    tmp_path: Path,
) -> None:
    class NoPrivateClient:
        def post(self, *args, **kwargs):
            raise AssertionError("public audit called a private endpoint")

    class FakeAudit:
        client = NoPrivateClient()
        report = {}
        skipped: list[tuple[str, str, dict]] = []

        def skip(self, check_id: str, detail: str, **evidence) -> None:
            self.skipped.append((check_id, detail, evidence))

    audit = FakeAudit()
    module._audit_history_scenarios(
        audit, _config(tmp_path, public=True),
        run_id="run-1", proposal_revision=1, review_revision=1,
    )

    assert audit.skipped == [
        (
            "historical_scenarios_exact_snapshot",
            "Public acceptance intentionally omits private history/catalog endpoints.",
            {"omitted_endpoint": "/api/v1/history/scenarios"},
        )
    ]


def test_numeric_primary_pieces_require_downloaded_svg_and_dxf() -> None:
    piece = {
        "piece_id": "p1",
        "component_id": "p1",
        "geometry": {"shape_kind": "rectangle"},
        "quantity": {"value": 2},
        "length": {"value_mm": 800.0},
        "width": {"value_mm": 300.0},
        "thickness": {"value_mm": 18.0},
        "sheet_ids": ["sheet-p1"],
    }
    package = {"construction": {"pieces": [piece]}}
    svg = {
        "kind": "piece_sheet_svg", "status": "ready", "sheet_id": "sheet-p1"
    }
    dxf = {
        "kind": "piece_sheet_dxf", "status": "ready", "sheet_id": "sheet-p1"
    }

    evidence = module._validate_construction_outputs(
        package, [(svg, b"<svg/>"), (dxf, b"0\nEOF")]
    )

    assert evidence["piece_count"] == 1
    assert evidence["manufactured_piece_count"] == 1
    assert evidence["hardware_count"] == 0
    assert evidence["numeric_dimension_count"] == 3
    with pytest.raises(module.AcceptanceFailure, match="construction_piece_formats_missing"):
        module._validate_construction_outputs(package, [(svg, b"<svg/>")])


def test_commercial_hardware_requires_bom_and_explicit_pending_fields() -> None:
    pending = {
        "value_mm": None,
        "state": "unknown",
        "review_status": "abstained",
        "explanation": "Commercial catalogue dimension remains to be selected.",
    }
    hardware = {
        "piece_id": "slides",
        "component_id": "slides",
        "geometry": {"shape_kind": "hardware"},
        "quantity": {
            "value": 3,
            "state": "estimated",
            "review_status": "accepted",
            "explanation": "Three reviewed commercial slide pairs.",
        },
        "length": {
            "value_mm": 400.0,
            "state": "estimated",
            "review_status": "accepted",
            "explanation": "Reviewed nominal catalogue length.",
        },
        "width": dict(pending),
        "thickness": dict(pending),
        "sheet_ids": [],
    }
    panel = {
        "piece_id": "side",
        "component_id": "side",
        "geometry": {"shape_kind": "rectangle"},
        "quantity": {"value": 2},
        "length": {"value_mm": 800.0},
        "width": {"value_mm": 450.0},
        "thickness": {"value_mm": 18.0},
        "sheet_ids": ["sheet-side"],
    }
    package = {
        "construction": {"pieces": [panel, hardware]},
        "bom_rows": [{"component_id": "slides"}],
    }
    downloads = [
        (
            {"kind": kind, "status": "ready", "sheet_id": "sheet-side"},
            b"content",
        )
        for kind in ("piece_sheet_svg", "piece_sheet_dxf")
    ]
    review = {
        "components": [{"id": "slides", "kind": "hardware"}],
        "machine_checks": [
            {
                "id": "visual-hardware",
                "method": "model_visual",
                "outcome": "pass",
                "target_refs": ["component:slides.geometry"],
            }
        ],
        "machine_field_reviews": [
            {
                "target_ref": "component:slides.geometry",
                "status": "accepted",
                "check_ids": ["visual-hardware"],
            }
        ],
    }

    evidence = module._validate_construction_outputs(package, downloads, review)

    assert evidence["manufactured_piece_count"] == 1
    assert evidence["hardware_count"] == 1
    assert evidence["hardware_pending_field_count"] == 2
    with pytest.raises(module.AcceptanceFailure, match="construction_hardware_bom_missing"):
        module._validate_construction_outputs(
            {"construction": {"pieces": [panel, hardware]}, "bom_rows": []},
            downloads,
            review,
        )
    with pytest.raises(
        module.AcceptanceFailure,
        match="construction_hardware_classification_unreviewed",
    ):
        module._validate_construction_outputs(
            package, downloads, {"components": review["components"]}
        )
    with pytest.raises(
        module.AcceptanceFailure, match="construction_manufactured_pieces_missing"
    ):
        module._validate_construction_outputs(
            {
                "construction": {"pieces": [hardware]},
                "bom_rows": [{"component_id": "slides"}],
            },
            [],
            review,
        )
    leaked = {**hardware, "length": {**hardware["length"], "review_status": "unreviewed"}}
    with pytest.raises(
        module.AcceptanceFailure, match="construction_hardware_numeric_unreviewed"
    ):
        module._validate_construction_outputs(
            {
                "construction": {"pieces": [panel, leaked]},
                "bom_rows": [{"component_id": "slides"}],
            },
            downloads,
            review,
        )


def test_estimated_quantity_keeps_occurrences_provisional() -> None:
    review = {
        "components": [
            {"id": "piece-1", "quantity": {"value": 2, "state": "estimated"}}
        ],
        "occurrences": [],
        "scenario_occurrences": [
            {"component_id": "piece-1", "state": "provisional"},
            {"component_id": "piece-1", "state": "provisional"},
        ],
    }

    assert module._assert_occurrence_authority(review) == {
        "physical": 0,
        "provisional": 2,
    }


def test_spanish_provisional_svg_keeps_non_manufacturing_authority() -> None:
    csv_payload = (
        "quantity_state,occurrence_status,physical_occurrence_ids,scenario_occurrence_ids\n"
        "estimated,provisional,,provisional:case:piece:1\n"
    ).encode()
    svg_payload = (
        '<svg data-authority="esquema_sin_colocacion_no_fabricacion">'
        "<text>ESQUEMA PROVISIONAL · NO APTO PARA FABRICACIÓN</text>"
        "<text>Escenario provisional</text></svg>"
    ).encode()

    evidence = module._validate_provisional_exports(csv_payload, svg_payload)

    assert evidence["svg_label"] == "provisional scenario"
