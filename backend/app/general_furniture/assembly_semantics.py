from __future__ import annotations

from backend.app.contratos.modelos import (
    DrawingExtraction,
    GeneralAssemblyRelation,
    GeneralFurnitureProposal,
)


def validate_assembly_source_references(
    extraction: DrawingExtraction,
    proposal: GeneralFurnitureProposal,
    *,
    allowed_document_refs: tuple[str, ...] = (),
) -> None:
    ledger = {
        "view": {item.id for item in extraction.views},
        "observation": {item.id for item in extraction.observations},
        "contour": {item.id for item in extraction.contours},
        "evidence": {item.id for item in extraction.evidence},
        "dimension": {item.id for item in extraction.dimensions},
    }
    document_refs = set(allowed_document_refs)

    def validate(relation: GeneralAssemblyRelation) -> None:
        for reference in relation.source_refs:
            kind, separator, reference_id = reference.partition(":")
            if kind in ledger:
                if not separator or reference_id not in ledger[kind]:
                    raise ValueError("assembly_reference_outside_ledger")
            elif reference not in document_refs:
                raise ValueError("assembly_reference_outside_document_context")

    for relation in proposal.assembly_relations:
        if (
            proposal.proposal_origin == "native_tool"
            and relation.state == "hypothesis"
            and not relation.source_refs
        ):
            raise ValueError(
                "native_assembly_hypothesis_requires_source_reference"
            )
        validate(relation)
    for alternative in proposal.assembly_alternatives:
        for relation in alternative.relations:
            if not relation.source_refs:
                raise ValueError(
                    "assembly_alternative_relation_requires_source_reference"
                )
            validate(relation)
