import httpx
import pytest

from backend.app.semantic_explorer.review import ReviewAssistant
from backend.app.semantic_explorer.store import ExplorerStore
from backend.tests.test_semantic_explorer import bundle, png


def test_review_budget_survives_restart_and_cache_avoids_second_call(tmp_path):
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "model": "jev-1.14.0",
                "answers": {
                    "category": {
                        "type": "choice",
                        "choice": "UNKNOWN",
                        "confidence": 0.6,
                        "probabilities": {
                            "a": 0.1,
                            "b": 0.1,
                            "OTHER": 0.2,
                            "UNKNOWN": 0.6,
                        },
                    }
                },
                "usage": {"input_tokens": 5, "output_tokens": 1},
                "secret_extra": "discard",
            },
        )

    store = ExplorerStore(tmp_path / "store.sqlite3")
    reviewer = ReviewAssistant(
        store, "test-key", 1, transport=httpx.MockTransport(provider)
    )
    entry = bundle().entries[0].model_copy(update={"text": "geometric observation"})
    first = reviewer.review(entry, png(), ("a", "b"), "snapshot")
    assert first["state"] == "needs_review" and first["label"] == "UNKNOWN"
    assert "secret_extra" not in str(first)
    restarted = ReviewAssistant(
        store, "test-key", 1, transport=httpx.MockTransport(provider)
    )
    assert restarted.review(entry, png(), ("a", "b"), "snapshot")["cache_hit"]
    assert len(calls) == 1
    with pytest.raises(ValueError, match="budget"):
        restarted.review(entry, png(), ("a", "b"), "new-snapshot")


def test_provider_failure_is_not_unknown_and_consumes_budget(tmp_path):
    store = ExplorerStore(tmp_path / "store.sqlite3")
    reviewer = ReviewAssistant(
        store, "test", 1, transport=httpx.MockTransport(lambda r: httpx.Response(503))
    )
    entry = bundle().entries[0].model_copy(update={"text": "geometry"})
    assert reviewer.review(entry, png(), ("a", "b"), "v1")["state"] == "provider_error"
    with pytest.raises(ValueError, match="budget"):
        reviewer.review(entry, png(), ("a", "b"), "v2")
