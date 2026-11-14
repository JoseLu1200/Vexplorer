from __future__ import annotations

import json

import httpx
import pytest

from backend.app.agente.config import ProviderSettings
from backend.app.agente.provider import OpenAIResponsesProvider, ProviderError
from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.agente.runner import AgentLimits
from backend.app.contratos.modelos import Bounds2D, DrawingExtraction, DrawingObservation, DrawingView, Evidence, ObservedDimension, InspectGeneralContextArgs
from backend.app.general_furniture.live import GENERAL_FURNITURE_SYSTEM_PROMPT, run_general_furniture_agent
from backend.app.general_furniture.live import GeneralVisualPage
from backend.app.general_furniture import live as general_live
from backend.app.agente.vision import VisionMark


def _extraction() -> DrawingExtraction:
    bounds = Bounds2D(min_x=0, min_y=0, max_x=800, max_y=720)
    return DrawingExtraction(
        drawing_id="drawing-1", status="ready", source_unit="mm", unit_scale_to_mm=1,
        coordinate_unit="mm", entities=(),
        views=(DrawingView(id="front", label="FRONT", entity_ids=(), bounds_source=bounds, bounds_mm=bounds),),
        contours=(),
        dimensions=(ObservedDimension(id="overall-width", kind="overall", value_mm=800, source_entity_ids=(), evidence_ids=("ev-width",), origin="observed", view_id="front"),),
        evidence=(Evidence(id="ev-width", kind="annotation", source_entity_ids=(), description="Ancho exterior 800 mm"),),
        observations=(DrawingObservation(id="obs-front", view_id="front", contour_ids=(), dimension_ids=("overall-width",)),),
    )


class _Provider:
    def __init__(self) -> None:
        self.tools = None
        self.input_items = None

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.tools = tools
        self.input_items = input_items
        arguments = {
            "bindings": [{"id": "panel-length", "operation": "copy", "operand_refs": ["dimension:overall-width"]}],
            "components": [{
                "id": "panel", "label": "Panel propuesto", "kind": "panel", "role": "unknown",
                "length_binding_id": "panel-length", "width_binding_id": None, "thickness_binding_id": None,
                "quantity": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
                "premise_ids": ["premise-panel"], "source_view_ids": ["front"],
                "source_observation_ids": ["obs-front"], "source_evidence_ids": ["ev-width"],
                "source_contour_ids": [],
                "source_dimension_ids": ["overall-width"], "assumptions": ["El rol no está confirmado."],
                "source_document_refs": [],
                "unknown_fields": ["width", "thickness", "quantity", "placement"],
            }],
            "premises": [{"id": "premise-panel", "description": "Puede ser un panel rectangular.", "required": True, "blocking": True}],
            "assumptions": ["Propuesta revisable, no apta para fabricación directa."],
        }
        return ProviderResponse(id="response-1", tool_calls=(ToolCall(call_id="call-1", name="proponer_mueble_general", arguments_json=json.dumps(arguments)),), model="fake")


def test_live_agent_uses_strict_native_tool_and_returns_new_evidence_grounded_proposal() -> None:
    provider = _Provider()

    outcome = run_general_furniture_agent(_extraction(), ledger_revision="ledger-1", provider=provider)

    assert outcome.proposal.proposal_origin == "native_tool"
    assert outcome.draft.components[0].length.value_mm == 800
    schema = next(item for item in provider.tools if item["name"] == "proponer_mueble_general")
    assert schema["strict"] is True
    assert schema["parameters"]["additionalProperties"] is False


def test_openai_provider_accepts_generic_instructions_without_changing_default_contract() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"id": "response-1", "status": "completed", "output": [], "usage": {}})

    provider = OpenAIResponsesProvider(
        ProviderSettings(api_key="test", model="gpt-test"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        instructions="GENERIC_FURNITURE_INSTRUCTIONS",
    )
    provider.create_response(input_items=[], tools=[], previous_response_id=None, timeout_s=1)

    assert captured["instructions"] == "GENERIC_FURNITURE_INSTRUCTIONS"


def test_live_tool_exposes_bounded_assembly_relations_and_ambiguity_rule() -> None:
    provider = _Provider()

    run_general_furniture_agent(
        _extraction(), ledger_revision="ledger-1", provider=provider,
    )

    schema = next(item for item in provider.tools if item["name"] == "proponer_mueble_general")
    assert {"assembly_relations", "assembly_alternatives"} <= set(
        schema["parameters"]["properties"]
    )
    assert "supported_by" in schema["description"]
    assert "fixed_to" in schema["description"]
    assert "unknown/conflict" in schema["description"]
    assert "side_panel, top_panel, bottom_panel" in schema["description"]
    assert "assembly_not_identifiable" in schema["description"]
    assert "view:<id> | observation:<id> | contour:<id> | evidence:<id> | dimension:<id>" in schema["description"]
    assert "alias raw" in schema["description"]
    assert "una sola colección" in schema["description"]
    assert "No declares uniones como observadas" in GENERAL_FURNITURE_SYSTEM_PROMPT
    assert "hidden joinery" in GENERAL_FURNITURE_SYSTEM_PROMPT
    payload = json.loads(provider.input_items[0]["content"][0]["text"])
    assert "roles canónicos" in payload["instruction"]
    assert "assembly_not_identifiable" in payload["instruction"]
    assert "Prefiere source_refs canónicos" in payload["instruction"]
    assert "dimension:<id>" in payload["instruction"]


def test_live_agent_preserves_visual_mark_mapping_and_projection_context() -> None:
    provider = _Provider()
    page = GeneralVisualPage(
        reference="cad:region-001", media_type="image/png", sha256="a" * 64,
        content=b"png", source_view_ids=("front",), source_contour_ids=("contour-1",),
        source_document_refs=("document:cad",), crop_bounds_source=(0, 0, 10, 20),
        marks=(VisionMark(mark_id="M001", source_kind="contour", source_id="contour-1"),),
        warnings=("spatial_region_not_semantic_view",),
    )

    run_general_furniture_agent(
        _extraction(), ledger_revision="ledger-1", provider=provider,
        visual_pages=(page,),
    )

    payload = json.loads(provider.input_items[0]["content"][0]["text"])
    visual = payload["visual_pages"][0]
    assert visual["marks"] == [{"mark_id": "M001", "source_kind": "contour", "source_id": "contour-1"}]
    assert visual["source_contour_ids"] == ["contour-1"]
    assert visual["crop_bounds_source"] == [0, 0, 10, 20]
    assert payload["compact_geometry"]["metadata"]["initial_measurement_scope"] == "contour_spans_only"
    assert payload["compact_geometry"]["metadata"]["projection_authority"] == "heuristic_not_probability_or_physical_identity"


def test_live_agent_returns_bounded_validation_reason_then_accepts_repaired_quantity() -> None:
    class RepairingProvider(_Provider):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0
            self.repair_input = None

        def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
            self.calls += 1
            response = super().create_response(
                input_items=input_items, tools=tools,
                previous_response_id=previous_response_id, timeout_s=timeout_s,
            )
            call = response.tool_calls[0]
            arguments = json.loads(call.arguments_json)
            if self.calls == 1:
                arguments["components"][0]["quantity"] = {
                    "value": 999, "state": "hypothesis", "dependency_refs": [], "evidence_ids": [],
                }
            else:
                self.repair_input = input_items
                arguments["components"][0]["quantity"] = {
                    "value": 4, "state": "hypothesis",
                    "dependency_refs": ["premise:premise-panel"], "evidence_ids": [],
                }
            return ProviderResponse(
                id=f"response-{self.calls}",
                tool_calls=(ToolCall(call_id=f"call-{self.calls}", name=call.name, arguments_json=json.dumps(arguments)),),
                model="fake",
            )

    provider = RepairingProvider()
    outcome = run_general_furniture_agent(_extraction(), ledger_revision="ledger-1", provider=provider)

    repair_payload = json.loads(provider.repair_input[0]["output"])
    assert repair_payload["error"] == "invalid_arguments"
    assert any("hypothesis quantity requires premise references" in item["msg"] for item in repair_payload["details"])
    assert outcome.proposal.components[0].quantity.value == 4


def test_measurement_inspector_allows_explicit_first_segment_page() -> None:
    request = InspectGeneralContextArgs(
        evidence_ids=(), view_ids=(), measurement_ids=(),
        query_measurements=True, measurement_offset=0, measurement_limit=64,
    )

    assert request.query_measurements is True


def _raster_extraction() -> DrawingExtraction:
    return DrawingExtraction(
        drawing_id="raster-drawing", status="needs_review",
        source_unit="unknown", unit_scale_to_mm=None, coordinate_unit="source",
        entities=(), views=(), contours=(), dimensions=(), evidence=(), observations=(),
    )


class _RasterProvider:
    def __init__(self, *, source_view_ids=()) -> None:
        self.source_view_ids = list(source_view_ids)
        self.tools = None
        self.input_items = None

    def create_response(self, *, input_items, tools, previous_response_id, timeout_s):
        self.tools = tools
        self.input_items = input_items
        arguments = {
            "bindings": [],
            "components": [{
                "id": "visual-panel", "label": "Panel visual provisional",
                "kind": "panel", "role": "unknown",
                "length_binding_id": None, "width_binding_id": None,
                "thickness_binding_id": None,
                "quantity": {"value": None, "state": "unknown", "dependency_refs": [], "evidence_ids": []},
                "premise_ids": ["visual-premise"],
                "source_view_ids": list(self.source_view_ids),
                "source_observation_ids": [], "source_contour_ids": [],
                "source_evidence_ids": [], "source_dimension_ids": [],
                "source_document_refs": ["document:pdf-child"],
                "assumptions": ["Interpretación visual sin escala métrica."],
                "unknown_fields": ["length", "width", "thickness", "quantity"],
            }],
            "premises": [{"id": "visual-premise", "description": "La silueta puede corresponder a un panel.", "required": True, "blocking": True}],
            "assumptions": ["No se infieren milímetros desde píxeles."],
        }
        return ProviderResponse(
            id="raster-response", model="fake",
            tool_calls=(ToolCall(call_id="raster-call", name="proponer_mueble_general", arguments_json=json.dumps(arguments)),),
        )


def test_raster_live_accepts_announced_document_reference_without_fake_view() -> None:
    provider = _RasterProvider()
    page = GeneralVisualPage(
        reference="pdf-sha:pdf-page:0001", media_type="image/png",
        sha256="b" * 64, content=b"png",
        source_document_refs=("document:pdf-child",),
    )

    outcome = run_general_furniture_agent(
        _raster_extraction(), ledger_revision="ledger-raster", provider=provider,
        visual_pages=(page,),
    )

    component = outcome.draft.components[0]
    assert component.source_view_ids == ()
    assert component.source_document_refs == ("document:pdf-child",)
    assert component.length.value_mm is None
    assert component.width.value_mm is None
    assert component.thickness.value_mm is None
    payload = json.loads(provider.input_items[0]["content"][0]["text"])
    assert payload["raster_authority"] == {
        "allowed_source_view_ids": [],
        "allowed_source_document_refs": [
            "pdf-sha:pdf-page:0001", "document:pdf-child",
        ],
        "allowed_numeric_binding_refs": [],
        "instruction": payload["raster_authority"]["instruction"],
    }
    proposal_schema = next(item for item in provider.tools if item["name"] == "proponer_mueble_general")
    assert "source_view_ids=[]" in proposal_schema["description"]
    assert "no midas píxeles" in proposal_schema["description"]


def test_raster_fake_view_failure_preserves_validation_reason_in_typed_error() -> None:
    page = GeneralVisualPage(
        reference="pdf-sha:pdf-page:0001", media_type="image/png",
        sha256="b" * 64, content=b"png",
        source_document_refs=("document:pdf-child",),
    )

    with pytest.raises(general_live.GeneralLiveError) as caught:
        run_general_furniture_agent(
            _raster_extraction(), ledger_revision="ledger-raster",
            provider=_RasterProvider(source_view_ids=("pdf-page-0001",)),
            visual_pages=(page,), limits=AgentLimits(max_validation_repairs=0),
        )

    assert caught.value.code == "validation_repair_budget_exhausted"
    assert caught.value.trace[-1]["details"] == [{
        "loc": [], "msg": "proposal_reference_outside_ledger", "type": "value_error",
    }]


def test_live_error_preserves_only_allowlisted_provider_diagnostic() -> None:
    class FailingProvider:
        def create_response(self, **kwargs):
            raise ProviderError(
                "provider_response_incomplete", status_code=200,
                request_id="req-safe", response_id="resp-safe",
                incomplete_reason="max_output_tokens",
            )

    with pytest.raises(general_live.GeneralLiveError) as caught:
        run_general_furniture_agent(
            _raster_extraction(), ledger_revision="ledger-raster",
            provider=FailingProvider(),
        )

    error = caught.value
    assert error.code == "provider_response_incomplete"
    assert error.provider_status_code == 200
    assert error.provider_request_id == "req-safe"
    assert error.provider_response_id == "resp-safe"
    assert error.provider_incomplete_reason == "max_output_tokens"
    assert error.trace == ()
