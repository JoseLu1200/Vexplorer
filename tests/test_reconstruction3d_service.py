import io
from types import SimpleNamespace

from PIL import Image
import pytest

from backend.app.reconstruction3d.service import reconstruct, ReconstructionError


def png():
    b = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(b, format="PNG")
    return b.getvalue()


def payload(unit="mm"):
    return {
        "status": "proposed",
        "intended_use": "panel",
        "unit": unit,
        "components": [
            {
                "id": "p1",
                "label": "panel",
                "size_mm": [100, 20, 200],
                "origin_mm": [0, 0, 0],
                "source_refs": ["input"],
                "assumptions": ["hypothetical thickness"],
            }
        ],
        "assumptions": ["hypothesis"],
        "missing_information": ["function"],
        "functional_notes": ["not certified"],
    }


class Provider:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def create_response(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="resp",
            model="fake",
            input_tokens=1,
            output_tokens=1,
            duration_ms=1,
            tool_calls=[
                SimpleNamespace(
                    name="proponer_construccion",
                    arguments=self.data,
                    arguments_json=None,
                )
            ],
        )


def test_uses_only_public_images_and_keeps_first_pass_and_review():
    provider = Provider(payload())
    r = reconstruct(png(), provider=provider, known_unit="mm")
    assert len(provider.calls) == 2
    assert r["proposal"]["status"] == "proposed" and r["baseline"] == r["proposal"]
    assert "evaluator_only" not in str(provider.calls)
    assert all(c["previous_response_id"] is None for c in provider.calls)
    from backend.app.reconstruction3d.service import SYSTEM_PROMPT

    assert all(
        c["input_items"][0]["role"] == "developer"
        and c["input_items"][0]["content"] == SYSTEM_PROMPT
        for c in provider.calls
    )


def test_unscaled_input_cannot_claim_millimetres():
    with pytest.raises(ReconstructionError, match="invalid_proposal"):
        reconstruct(png(), provider=Provider(payload()), known_unit="relative")


def test_private_or_unknown_reference_is_rejected():
    p = payload()
    p["components"][0]["source_refs"] = ["private:answer"]
    with pytest.raises(ReconstructionError, match="invalid_proposal"):
        reconstruct(png(), provider=Provider(p), known_unit="mm")


def test_provider_error_does_not_become_abstention():
    class Bad:
        def create_response(self, **kwargs):
            raise RuntimeError("sensitive detail")

    with pytest.raises(ReconstructionError, match="provider_failed") as e:
        reconstruct(png(), provider=Bad(), known_unit="relative")
    assert "sensitive" not in str(e.value)
