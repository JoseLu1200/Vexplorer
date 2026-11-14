from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.agente.runner import AgentLimits, run_agent, run_parts_agent, run_table_agent
from backend.app.agente.tools import parts_tool_schemas, table_tool_schemas, tool_schemas
from backend.app.geometria import extract_drawing
from backend.app.geometria.mounted_table import analyze_mounted_table, catalog_table_programs
from backend.app.geometria.parts import derive_assembly_candidates, extract_separated_parts
from backend.app.servicios.decomposition import derive_decomposition_scenarios


ROOT = Path(__file__).resolve().parents[2]


class _Script:
    def __init__(self, responses: list[ProviderResponse]) -> None:
        self.responses = responses
        self.inputs: list[list[dict]] = []

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.inputs.append(input_items)
        return self.responses.pop(0)


def _response(response_id: str, call_id: str, name: str, arguments: dict) -> ProviderResponse:
    return ProviderResponse(
        id=response_id, model="model-test",
        tool_calls=(ToolCall(call_id=call_id, name=name, arguments=arguments),),
    )


def test_compare_schema_is_strict_common_and_contains_no_free_numbers_or_paths() -> None:
    for registry in (tool_schemas(), parts_tool_schemas(), table_tool_schemas()):
        schema = next(item for item in registry if item["name"] == "comparar_candidatas")
        parameters = schema["parameters"]
        assert parameters["additionalProperties"] is False
        assert set(parameters["required"]) == {"candidate_revision", "candidate_ids"}
        ids = parameters["properties"]["candidate_ids"]
        assert ids["minItems"] == ids["maxItems"] == 2
        encoded = json.dumps(schema).lower()
        assert "path" not in encoded and "file" not in encoded
        assert "number" not in encoded and "integer" not in encoded


def test_legacy_compare_recalculates_current_revision_and_rejects_cross_revision() -> None:
    extraction = extract_drawing(ROOT / "data/planos_demo/estanteria_montada.dxf")
    scenarios = derive_decomposition_scenarios(extraction)
    first, second = scenarios[0].components[0].id, scenarios[1].components[0].id
    provider = _Script([
        _response("r1", "c1", "comparar_candidatas", {
            "candidate_revision": "wrong", "candidate_ids": [first, second],
        }),
        _response("r2", "c2", "comparar_candidatas", {
            "candidate_revision": extraction.drawing_id, "candidate_ids": [first, second],
        }),
        _response("r3", "c3", "entregar_despiece", {"scenario_id": scenarios[0].id}),
    ])
    run_agent(extraction, scenarios, provider, AgentLimits(max_model_calls=3, max_tool_calls=3, timeout_s=5))
    rejected = json.loads(provider.inputs[1][0]["output"])
    compared = json.loads(provider.inputs[2][0]["output"])
    assert rejected["error"] == "candidate_revision_mismatch"
    assert compared["ok"] is True
    assert compared["comparison"]["candidate_ids"] == [first, second]
    assert {item["kind"] for item in compared["comparison"]["relations"]} == {
        "same_physical_part", "same_dimensions", "mirrored_variant", "alternative_hypothesis",
    }
    assert all(item["status"] in {"pass", "fail", "unknown", "not_applicable"} for item in compared["comparison"]["relations"])


def test_parts_compare_uses_only_current_assembly_candidates() -> None:
    extraction = extract_drawing(ROOT / "data/planos_demo/piezas_completo.dxf", input_kind="separated_part_views")
    parts = extract_separated_parts(extraction)
    candidates = derive_assembly_candidates(parts)
    provider = _Script([
        _response("r1", "c1", "comparar_candidatas", {
            "candidate_revision": parts.candidate_revision,
            "candidate_ids": [candidates[0].id, candidates[1].id],
        }),
        _response("r2", "c2", "entregar_candidato_montaje", {
            "candidate_revision": parts.candidate_revision,
            "assembly_candidate_id": candidates[0].id,
        }),
    ])
    run_parts_agent(extraction, parts, candidates, provider, AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5))
    compared = json.loads(provider.inputs[1][0]["output"])["comparison"]
    assert compared["candidate_kind"] == "assembly"
    assert compared["candidate_ids"] == [candidates[0].id, candidates[1].id]
    assert "value_mm" not in json.dumps(compared)


def test_table_compare_uses_only_programs_announced_in_current_context() -> None:
    extraction = extract_drawing(ROOT / "data/planos_demo/mesa_demo_001.dxf", input_kind="mounted_orthographic_views")
    analysis = analyze_mounted_table(extraction)
    candidates = catalog_table_programs(analysis)
    baseline = candidates[0]
    proposal = {
        "bindings": [item.model_dump(mode="json") for item in baseline.bindings],
        "components": [item.model_dump(mode="json") for item in baseline.components],
        "premises": [item.model_dump(mode="json") for item in baseline.premises],
        "assumptions": list(baseline.assumptions),
        "evidence_ids": list(baseline.evidence_ids),
    }
    provider = _Script([
        _response("r1", "c1", "comparar_candidatas", {
            "candidate_revision": analysis.ledger_revision,
            "candidate_ids": [candidates[0].id, candidates[1].id],
        }),
        _response("r2", "c2", "proponer_descomposicion", proposal),
    ])
    run_table_agent(
        extraction, analysis, provider,
        AgentLimits(max_model_calls=2, max_tool_calls=2, timeout_s=5),
        comparison_candidates=candidates,
    )
    context = json.loads(provider.inputs[0][0]["content"])
    assert {item["id"] for item in context["program_candidates"]} == {item.id for item in candidates}
    compared = json.loads(provider.inputs[1][0]["output"])["comparison"]
    assert compared["candidate_kind"] == "table_program"
    assert compared["candidate_ids"] == [candidates[0].id, candidates[1].id]
    assert "value_mm" not in json.dumps(compared)
