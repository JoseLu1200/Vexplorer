from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.contratos.modelos import (
    ReviewRequest,
    TableConfirmedValue,
    TableCostCatalog,
    TableCostTariff,
    TableObservedValueCorrection,
    TableSourceReviewDecision,
)


def test_human_corrections_have_stable_identity_and_explicit_supersession() -> None:
    first = TableConfirmedValue(
        confirmation_id="confirmation-top-t-v1",
        target_id="top-t",
        value_mm=30,
        reason="Medición inicial con calibre.",
    )
    replacement = TableConfirmedValue(
        confirmation_id="confirmation-top-t-v2",
        supersedes_confirmation_id=first.confirmation_id,
        target_id="top-t",
        value_mm=32,
        reason="Segunda medición humana documentada.",
    )
    correction = TableObservedValueCorrection(
        correction_id="correction-width-v1",
        measurement_id="measurement-width",
        value_mm=1199.8,
        reason="Comprobación humana sobre el plano fuente.",
        evidence_ids=("evidence-caliper-note",),
    )
    source_review = TableSourceReviewDecision(
        warning_id="source-warning-0123456789abcdef",
        warning_code="recovered_dxf:header_repaired",
        action="accept",
        reason="La técnica contrastó el DXF recuperado con el original.",
    )

    request = ReviewRequest(
        base_result_revision=2,
        reviewer_name="Técnica",
        table_program_id="program-side",
        table_confirmed_values=(replacement,),
        table_observed_value_corrections=(correction,),
        table_source_review_decisions=(source_review,),
        notes="Revisión trazable.",
    )

    assert request.table_confirmed_values[0].supersedes_confirmation_id == first.confirmation_id
    assert request.table_observed_value_corrections[0].source == "human"
    assert request.table_source_review_decisions[0].warning_code.startswith("recovered_dxf:")


def test_real_catalog_rejects_concept_unit_or_scope_mismatch() -> None:
    with pytest.raises(ValidationError, match="concept.*unit.*scope|combination"):
        TableCostTariff(
            id="bad-board",
            label="Tablero mal configurado",
            concept_type="material_area",
            scope="material",
            rate_eur_per_unit=50,
            rate_unit="EUR/h",
            synthetic=False,
        )


def test_catalog_provenance_and_synthetic_state_are_consistent() -> None:
    tariff = TableCostTariff(
        id="board-real",
        label="Tablero real",
        concept_type="material_area",
        scope="material",
        rate_eur_per_unit=50,
        rate_unit="EUR/m2",
        synthetic=False,
    )
    catalog = TableCostCatalog(
        catalog_version="erp-2026-11",
        source="Exportación ERP aprobada",
        effective_date="2026-11-01",
        synthetic=False,
        tariffs=(tariff,),
    )

    assert catalog.schema_version == "0.6.0"
    with pytest.raises(ValidationError, match="synthetic"):
        TableCostCatalog(
            catalog_version="mixed",
            source="Fuente inconsistente",
            effective_date="2026-11-01",
            synthetic=False,
            tariffs=(tariff.model_copy(update={"synthetic": True}),),
        )


@pytest.mark.parametrize("bad_date", ("2026-99-99", "2026-02-30"))
def test_real_catalog_effective_date_must_exist_on_calendar(bad_date: str) -> None:
    with pytest.raises(ValidationError, match="calendar date"):
        TableCostCatalog(
            catalog_version="erp-bad-date",
            source="ERP",
            effective_date=bad_date,
            synthetic=False,
            tariffs=(),
        )


def test_cost_exclusion_rejects_whitespace_reason_and_nonfinite_hours() -> None:
    from backend.app.contratos.modelos import TableCostExclusion, TableCostScope

    with pytest.raises(ValidationError, match="blank"):
        TableCostExclusion(scope="finishing", reason="   ")
    with pytest.raises(ValidationError, match="operation hours"):
        TableCostScope(
            operation_tariff_ids=("cut",),
            operation_hours_by_tariff={"cut": float("nan")},
        )


def test_operation_exclusion_rejects_selected_tariffs_or_hours() -> None:
    from backend.app.contratos.modelos import TableCostExclusion, TableCostScope

    with pytest.raises(ValidationError, match="excluded operation.*tariffs or hours"):
        TableCostScope(
            operation_tariff_ids=("cut",),
            operation_hours_by_tariff={"cut": 4},
            exclusions=(
                TableCostExclusion(
                    scope="operation",
                    reason="Operaciones fuera del encargo.",
                ),
            ),
        )
