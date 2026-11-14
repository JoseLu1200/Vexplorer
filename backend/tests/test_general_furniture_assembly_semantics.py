from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.contratos.modelos import (
    GeneralAssemblyAlternative,
    GeneralAssemblyRelation,
    GeneralFurnitureProposal,
    GeneralPremise,
)
from backend.app.general_furniture.proposal import materialize_general_proposal
from backend.app.general_furniture.repository import GeneralFurnitureRepository
from backend.app.general_furniture.router import (
    GeneralFurnitureContext,
    create_general_furniture_router,
)
from backend.tests.test_general_furniture_proposal import _extraction, _proposal


def _proposal_with_assembly(*, source_refs: tuple[str, ...]) -> GeneralFurnitureProposal:
    base = _proposal()
    support = base.components[0].model_copy(
        update={
            "id": "support",
            "label": "Support",
            "role": "support",
            "premise_ids": ("p-support",),
        }
    )
    top = base.components[0].model_copy(
        update={
            "id": "top",
            "label": "Top",
            "role": "top",
            "premise_ids": ("p-top",),
        }
    )
    supported = GeneralAssemblyRelation(
        subject_component_id="top",
        relation="supported_by",
        object_component_id="support",
        state="hypothesis",
        premise_ids=("p-supported",),
        source_refs=source_refs,
    )
    fixed = supported.model_copy(update={"relation": "fixed_to"})
    attached = supported.model_copy(update={"relation": "attached_to"})
    return GeneralFurnitureProposal(
        **(
            base.model_dump()
            | {
                "components": (top, support),
                "premises": (
                    GeneralPremise(id="p-top", description="The top is a component hypothesis."),
                    GeneralPremise(id="p-support", description="The support is a component hypothesis."),
                    GeneralPremise(id="p-supported", description="The drawing permits more than one assembly interpretation."),
                ),
                "assembly_relations": (supported,),
                "assembly_alternatives": (
                    GeneralAssemblyAlternative(
                        alternative_id="fixed",
                        relations=(fixed,),
                        premise_ids=("p-supported",),
                    ),
                    GeneralAssemblyAlternative(
                        alternative_id="attached",
                        relations=(attached,),
                        premise_ids=("p-supported",),
                    ),
                ),
            }
        )
    )


def test_materialize_preserves_incompatible_assembly_hypotheses_without_creating_components() -> None:
    proposal = _proposal_with_assembly(
        source_refs=("view:view-front", "evidence:evidence-width", "visual:page-1")
    )

    draft = materialize_general_proposal(
        _extraction(), proposal, allowed_document_refs=("visual:page-1",)
    )

    assert draft.assembly_relations == proposal.assembly_relations
    assert draft.assembly_alternatives == proposal.assembly_alternatives
    assert [item.id for item in draft.components] == ["top", "support"]


def test_materialize_rejects_assembly_source_reference_outside_ledger() -> None:
    proposal = _proposal_with_assembly(source_refs=("evidence:not-in-ledger",))

    with pytest.raises(ValueError, match="assembly_reference_outside_ledger"):
        materialize_general_proposal(_extraction(), proposal)


def test_materialize_accepts_unique_raw_ledger_ids_as_closed_aliases() -> None:
    proposal = _proposal_with_assembly(
        source_refs=("view-front", "observation-front", "evidence-width")
    )

    draft = materialize_general_proposal(_extraction(), proposal)

    assert draft.assembly_relations[0].source_refs == (
        "view-front",
        "observation-front",
        "evidence-width",
    )


def test_materialize_rejects_raw_reference_missing_from_ledger() -> None:
    proposal = _proposal_with_assembly(source_refs=("not-in-ledger",))

    with pytest.raises(ValueError, match="assembly_reference_outside_ledger"):
        materialize_general_proposal(_extraction(), proposal)


def test_materialize_rejects_raw_id_ambiguous_across_ledger_namespaces() -> None:
    extraction = _extraction()
    extraction = extraction.model_copy(
        update={
            "evidence": (
                *extraction.evidence,
                extraction.evidence[0].model_copy(update={"id": "view-front"}),
            )
        }
    )
    proposal = _proposal_with_assembly(source_refs=("view-front",))

    with pytest.raises(ValueError, match="assembly_reference_ambiguous"):
        materialize_general_proposal(extraction, proposal)


def test_materialize_rejects_unannounced_assembly_document_reference() -> None:
    proposal = _proposal_with_assembly(source_refs=("visual:private-oracle",))

    with pytest.raises(ValueError, match="assembly_reference_outside_document_context"):
        materialize_general_proposal(
            _extraction(), proposal, allowed_document_refs=("visual:page-1",)
        )


def test_materialize_rejects_alternative_relation_without_its_own_source_reference() -> None:
    proposal = _proposal_with_assembly(source_refs=("view:view-front",))
    alternative = proposal.assembly_alternatives[0]
    relation = alternative.relations[0].model_copy(update={"source_refs": ()})
    proposal = proposal.model_copy(
        update={
            "assembly_alternatives": (
                alternative.model_copy(update={"relations": (relation,)}),
                proposal.assembly_alternatives[1],
            )
        }
    )

    with pytest.raises(
        ValueError, match="assembly_alternative_relation_requires_source_reference"
    ):
        materialize_general_proposal(_extraction(), proposal)


def test_materialize_rejects_native_hypothesis_relation_without_source_reference() -> None:
    proposal = _proposal_with_assembly(source_refs=("view:view-front",))
    relation = proposal.assembly_relations[0].model_copy(update={"source_refs": ()})
    proposal = proposal.model_copy(update={"assembly_relations": (relation,)})

    with pytest.raises(
        ValueError, match="native_assembly_hypothesis_requires_source_reference"
    ):
        materialize_general_proposal(_extraction(), proposal)


def test_repository_and_http_snapshot_keep_alternatives_separate(tmp_path) -> None:
    repository = GeneralFurnitureRepository(tmp_path / "general.sqlite3")
    app = FastAPI()
    app.include_router(
        create_general_furniture_router(
            repository=repository,
            context_loader=lambda run_id: GeneralFurnitureContext(
                run_id=run_id,
                extraction=_extraction().model_copy(
                    update={"input_kind": "general_furniture"}
                ),
                ledger_revision="ledger-1",
            ),
        )
    )
    proposal = _proposal_with_assembly(source_refs=("view:view-front",)).model_copy(
        update={"proposal_origin": "human"}
    )

    response = TestClient(app).post(
        "/api/v1/runs/run-assembly/general/proposals",
        json={
            "mode": "manual",
            "base_proposal_revision": 0,
            "proposal": proposal.model_dump(mode="json"),
        },
    )

    assert response.status_code == 201
    payload = response.json()["data"]
    assert [
        item["alternative_id"]
        for item in payload["proposal"]["assembly_alternatives"]
    ] == ["fixed", "attached"]
    assert [
        item["relations"][0]["relation"]
        for item in payload["draft"]["assembly_alternatives"]
    ] == ["fixed_to", "attached_to"]
    stored = repository.get("run-assembly")
    assert stored is not None
    assert stored.proposal.assembly_alternatives == proposal.assembly_alternatives
    assert stored.draft.assembly_alternatives == proposal.assembly_alternatives


def test_legacy_proposal_materializes_with_empty_assembly_defaults() -> None:
    draft = materialize_general_proposal(_extraction(), _proposal())

    assert draft.assembly_relations == ()
    assert draft.assembly_alternatives == ()
