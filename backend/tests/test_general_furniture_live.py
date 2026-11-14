from __future__ import annotations

import json

import httpx

from backend.app.agente.config import ProviderSettings
from backend.app.agente.provider import OpenAIResponsesProvider
from backend.app.agente.provider import ProviderResponse, ToolCall
from backend.app.contratos.modelos import Bounds2D, DrawingExtraction, DrawingObservation, DrawingView, Evidence, ObservedDimension, InspectGeneralContextArgs
from backend.app.general_furniture.live import run_general_furniture_agent
from backend.app.general_furniture.live import GeneralVisualPage
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
