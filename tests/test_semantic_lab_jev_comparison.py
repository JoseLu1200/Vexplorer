import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
import urllib.error

import pytest

from tools.semantic_lab.jev_comparison import (
    JevClient,
    AttemptBudget,
    ProviderError,
    build_payload,
    build_questions,
    classification_summary,
    _operational_summary,
    load_api_key,
    open_choice_summary,
    ood_summary,
    validate_response,
)


CORE_CRITERIA = {
    "beds": "Beds and bed groups.",
    "buffets": "Commercial serving and kitchen-line equipment.",
    "simple-tables": "Tables, desks, chairs, and office arrangements.",
    "sofas": "Sofas, armchairs, chaise longues, and ottomans.",
}


def _sample() -> dict:
    return {
        "id": "case-1",
        "label": "secret-sample-label",
        "source_path": "private/revealing-name.dxf",
        "image_path": "private/render.png",
        "text": "geometric observation; normalized width 1.0000",
    }


def _response(choice: str = "beds") -> dict:
    return {
        "model": "jev-1.14.0",
        "answers": {
            "closed_category": {
                "type": "choice",
                "choice": choice,
                "confidence": 0.8,
                "probabilities": {
                    "beds": 0.7,
                    "buffets": 0.1,
                    "simple-tables": 0.1,
                    "sofas": 0.1,
                },
            },
            "open_category": {
                "type": "choice",
                "choice": choice,
                "confidence": 0.7,
                "probabilities": {
                    "beds": 0.6,
                    "buffets": 0.1,
                    "simple-tables": 0.1,
                    "sofas": 0.1,
                    "OTHER": 0.05,
                    "UNKNOWN": 0.05,
                },
            },
            "sufficient_evidence": {"type": "noul", "noul": 0.75},
        },
        "usage": {"input_tokens": 500, "output_tokens": 50},
    }


class _HTTPResponse:
    status = 200

    def __init__(self, body: dict):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.body).encode("utf-8")


def test_payload_uses_only_neutral_observation_and_optional_image() -> None:
    questions = build_questions(CORE_CRITERIA)
    text_payload = build_payload(_sample(), "text", questions=questions)
    mixed_payload = build_payload(
        _sample(), "mixed", questions=questions, image_bytes=b"png-bytes"
    )

    assert text_payload["state"] == {
        "geometric_observation": "geometric observation; normalized width 1.0000"
    }
    assert "assets" not in text_payload
    assert set(mixed_payload["state"]) == {"geometric_observation", "drawing"}
    assert list(mixed_payload["assets"].values()) == [
        {"type": "image", "format": "png", "data_base64": "cG5nLWJ5dGVz"}
    ]
    serialized = json.dumps(mixed_payload)
    assert "secret-sample-label" not in serialized
    assert "revealing-name" not in serialized


def test_questions_have_closed_open_and_independent_evidence_contract() -> None:
    questions = build_questions(CORE_CRITERIA)

    assert set(questions) == {"closed_category", "open_category", "sufficient_evidence"}
    assert set(questions["closed_category"]["criteria"]) == set(CORE_CRITERIA)
    assert set(questions["open_category"]["criteria"]) == {
        *CORE_CRITERIA,
        "OTHER",
        "UNKNOWN",
    }
    assert questions["sufficient_evidence"]["type"] == "noul"


def test_cache_identity_excludes_authorization_and_replays_without_network(
    tmp_path: Path,
) -> None:
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        return _HTTPResponse(_response())

    payload = build_payload(_sample(), "text", questions=build_questions(CORE_CRITERIA))
    first = JevClient("first-secret", tmp_path, opener=opener).evaluate(payload)
    second = JevClient("different-secret", tmp_path, opener=opener).evaluate(payload)

    assert calls == 1
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    cached = next(tmp_path.glob("*.json")).read_text(encoding="utf-8")
    assert "first-secret" not in cached
    assert "different-secret" not in cached
    assert "geometric observation" not in cached


def test_transport_ambiguity_is_not_retried(tmp_path: Path) -> None:
    calls = 0
    budget = AttemptBudget(1)

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise TimeoutError("ambiguous delivery")

    client = JevClient("secret", tmp_path, opener=opener, budget=budget)
    with pytest.raises(ProviderError, match="transport_failure"):
        client.evaluate(
            build_payload(_sample(), "text", questions=build_questions(CORE_CRITERIA))
        )
    assert calls == 1
    assert budget.used == 1


def test_503_is_not_retried_because_delivery_may_be_ambiguous(tmp_path: Path) -> None:
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, None)

    with pytest.raises(ProviderError, match="http_503"):
        JevClient("secret", tmp_path, opener=opener, sleep=lambda _: None).evaluate(
            build_payload(_sample(), "text", questions=build_questions(CORE_CRITERIA))
        )
    assert calls == 1


@pytest.mark.parametrize("status", [429, 529])
def test_explicit_rate_limit_retries_once_and_budget_ignores_later_cache_hit(
    tmp_path: Path, status: int
) -> None:
    calls = 0
    budget = AttemptBudget(2)

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError(
                request.full_url, status, "limited", {"Retry-After": "0"}, None
            )
        return _HTTPResponse(_response())

    payload = build_payload(_sample(), "text", questions=build_questions(CORE_CRITERIA))
    client = JevClient(
        "secret", tmp_path, opener=opener, sleep=lambda _: None, budget=budget
    )
    assert client.evaluate(payload)["network_attempts"] == 2
    assert client.evaluate(payload)["cache_hit"] is True
    assert calls == 2
    assert budget.used == 2


def test_retry_after_over_bound_stops_without_second_attempt(tmp_path: Path) -> None:
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(
            request.full_url, 429, "limited", {"Retry-After": "31"}, None
        )

    with pytest.raises(ProviderError, match="retry_after_exceeds_bound"):
        JevClient("secret", tmp_path, opener=opener, sleep=lambda _: None).evaluate(
            build_payload(_sample(), "text", questions=build_questions(CORE_CRITERIA))
        )
    assert calls == 1


def test_attempt_cap_is_shared_across_clients_and_counts_retry(tmp_path: Path) -> None:
    calls = 0
    budget = AttemptBudget(2)

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError(
                request.full_url, 429, "limited", {"Retry-After": "0"}, None
            )
        return _HTTPResponse(_response())

    questions = build_questions(CORE_CRITERIA)
    first_payload = build_payload(_sample(), "text", questions=questions)
    second_payload = build_payload(
        {**_sample(), "text": "geometric observation; normalized width 0.5000"},
        "text",
        questions=questions,
    )
    first = JevClient(
        "secret", tmp_path, opener=opener, sleep=lambda _: None, budget=budget
    )
    second = JevClient(
        "secret", tmp_path, opener=opener, sleep=lambda _: None, budget=budget
    )

    assert first.evaluate(first_payload)["network_attempts"] == 2
    with pytest.raises(ProviderError, match="request_cap_exhausted"):
        second.evaluate(second_payload)
    assert calls == 2
    assert budget.used == 2


def test_non_retryable_http_error_does_not_expose_body_or_retry(tmp_path: Path) -> None:
    calls = 0
    budget = AttemptBudget(1)

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError(request.full_url, 400, "secret body", {}, None)

    with pytest.raises(ProviderError) as exc:
        JevClient("secret", tmp_path, opener=opener, budget=budget).evaluate(
            build_payload(_sample(), "text", questions=build_questions(CORE_CRITERIA))
        )
    assert str(exc.value) == "http_400"
    assert calls == 1
    assert budget.used == 1


def test_operational_summary_separates_replayed_usage_and_uses_attempt_override() -> (
    None
):
    response = _response()
    records = [
        {
            "status": "ok",
            "cache_hit": False,
            "elapsed_s": 0.2,
            "network_attempts": 1,
            "response": response,
        },
        {
            "status": "ok",
            "cache_hit": True,
            "elapsed_s": 0.0,
            "network_attempts": 0,
            "response": response,
        },
        {"status": "api_error", "error": "transport_failure_delivery_unknown"},
    ]

    result = _operational_summary(records, network_attempts_total=3)

    assert result["network_requests"] == 3
    assert result["total_reported_input_tokens"] == 1000
    assert result["total_reported_output_tokens"] == 100
    assert result["new_successful_uncached_input_tokens"] == 500
    assert result["new_successful_uncached_output_tokens"] == 50
    assert result["estimated_new_input_cost_usd"] == pytest.approx(500 / 1e6 * 0.042)
    assert result["ambiguous_delivery_errors"] == 1


def test_response_is_rebuilt_from_whitelisted_fields() -> None:
    questions = build_questions(CORE_CRITERIA)
    response = _response()
    response["provider_state"] = {"asset": "must-not-persist"}
    response["answers"]["closed_category"]["trace"] = "must-not-persist"
    response["answers"]["open_category"]["extra"] = ["must-not-persist"]
    response["answers"]["sufficient_evidence"]["explanation"] = "must-not-persist"
    response["usage"]["billing_reference"] = "must-not-persist"

    sanitized = validate_response(response, questions)

    assert set(sanitized) == {"model", "answers", "usage"}
    assert set(sanitized["answers"]["closed_category"]) == {
        "type",
        "choice",
        "confidence",
        "probabilities",
    }
    assert set(sanitized["answers"]["open_category"]) == {
        "type",
        "choice",
        "confidence",
        "probabilities",
    }
    assert sanitized["answers"]["sufficient_evidence"] == {"type": "noul", "noul": 0.75}
    assert sanitized["usage"] == {"input_tokens": 500, "output_tokens": 50}


def test_same_inflight_payload_is_deduplicated_across_threads(tmp_path: Path) -> None:
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        time.sleep(0.05)
        return _HTTPResponse(_response())

    payload = build_payload(_sample(), "text", questions=build_questions(CORE_CRITERIA))
    first = JevClient("secret", tmp_path, opener=opener)
    second = JevClient("secret", tmp_path, opener=opener)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda client: client.evaluate(payload), (first, second))
        )

    assert calls == 1
    assert sorted(result["cache_hit"] for result in results) == [False, True]


def test_metrics_keep_api_errors_in_all_denominators() -> None:
    records = [
        {"expected": "a", "status": "ok", "closed": "a", "open": "a"},
        {"expected": "a", "status": "ok", "closed": "b", "open": "UNKNOWN"},
        {"expected": "b", "status": "api_error"},
        {"expected": "b", "status": "ok", "closed": "b", "open": "b"},
    ]

    closed = classification_summary(records, labels=["a", "b"])
    opened = open_choice_summary(records)

    assert closed["total"] == 4
    assert closed["api_errors"] == 1
    assert closed["balanced_accuracy"] == pytest.approx(0.5)
    assert closed["macro_f1"] == pytest.approx((2 / 3 + 1 / 2 + 0) / 3)
    assert opened == {
        "total": 4,
        "api_errors": 1,
        "covered": 2,
        "correct": 2,
        "coverage": 0.5,
        "exact_correct_all": 0.5,
        "conditional_accuracy": 1.0,
    }


def test_zero_support_taxonomy_class_is_reported_but_not_in_macro_average() -> None:
    records = [
        {"expected": "a", "status": "ok", "closed": "a"},
        {"expected": "a", "status": "ok", "closed": "a"},
    ]
    result = classification_summary(records, labels=["a", "b"])

    assert result["macro_f1"] == 1.0
    assert result["balanced_accuracy"] == 1.0
    assert result["per_class"]["b"] == {
        "support": 0,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }


def test_ood_abstention_does_not_count_provider_errors_as_unknown() -> None:
    records = [
        {"status": "ok", "open": "OTHER"},
        {"status": "ok", "open": "UNKNOWN"},
        {"status": "ok", "open": "beds"},
        {"status": "api_error"},
    ]
    assert ood_summary(records) == {
        "total": 4,
        "api_errors": 1,
        "abstentions": 2,
        "abstention_rate_all": 0.5,
        "abstention_rate_successful": pytest.approx(2 / 3),
    }


def test_credential_file_reads_only_requested_key(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "OTHER_SECRET=do-not-use\nTYPESAFE_API_KEY=chosen\n", encoding="utf-8"
    )
    assert load_api_key(None, path) == "chosen"
    with pytest.raises(ValueError, match="missing TYPESAFE_API_KEY"):
        load_api_key(None, tmp_path / "missing.env")
