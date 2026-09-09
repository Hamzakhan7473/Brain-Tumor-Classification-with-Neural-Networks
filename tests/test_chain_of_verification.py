"""Chain-of-verification: atomic claims vs grounding payload (stubbed LLM)."""

from __future__ import annotations

import json

import pytest

from src.llm.chain_of_verification import (
    decompose_into_claims,
    run_chain_of_verification,
    verify_claim,
)
from src.llm.validation import enforce_clinical_gate, grounding_from_prediction


GLIOMA_PAYLOAD = grounding_from_prediction(
    "glioma",
    0.91,
    {"glioma": 0.91, "meningioma": 0.05, "pituitary": 0.03, "notumor": 0.01},
)

CLEAN_GLIOMA = (
    "Prediction summary: the classifier favors glioma with confidence 0.91 "
    "(91%). Additional insights: appearance is consistent with glioma. "
    "No other findings are stated."
)

MULTI_SENTENCE = (
    "The classifier favors glioma. Appearance is consistent with glioma. "
    "No other findings are stated."
)


def test_decompose_into_claims_splits_multi_sentence():
    claims = decompose_into_claims(MULTI_SENTENCE, complete_fn=lambda *a, **k: "")
    assert 2 <= len(claims) <= 5
    blob = " ".join(claims).lower()
    assert "glioma" in blob


def test_decompose_into_claims_parses_llm_json():
    payload = json.dumps({"claims": ["Claim one.", "Claim two.", "Claim three."]})
    claims = decompose_into_claims("ignored source text. Another sentence.", complete_fn=lambda *a, **k: payload)
    assert claims == ["Claim one.", "Claim two.", "Claim three."]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("SUPPORTED", "SUPPORTED"),
        ('{"status":"CONTRADICTED","rationale":"severity mismatch"}', "CONTRADICTED"),
        ("NOT_ADDRESSED_BY_PAYLOAD", "NOT_ADDRESSED_BY_PAYLOAD"),
        ('{"status": "supported"}', "SUPPORTED"),
    ],
)
def test_verify_claim_classifies_mocked_statuses(raw, expected):
    result = verify_claim(
        "WMH burden is severe.",
        {"wmh": {"volume_cc": 2.0, "severity_grade": "Mild"}},
        complete_fn=lambda *a, **k: raw,
    )
    assert result.status == expected
    assert result.claim == "WMH burden is severe."
    if expected == "CONTRADICTED":
        assert "severity" in (result.rationale or "").lower() or result.rationale == ""


def test_contradicted_claim_is_tier_0_fallback(monkeypatch):
    monkeypatch.setenv("ENABLE_CHAIN_OF_VERIFICATION", "true")
    calls = {"n": 0}

    def _complete(prompt, max_tokens=256, **_k):
        if "independent factual claims" in prompt or "Split the clinical" in prompt:
            return json.dumps({"claims": ["This finding is a surgical emergency."]})
        return json.dumps({"status": "CONTRADICTED", "rationale": "payload does not support emergency"})

    monkeypatch.setattr("src.llm.chain_of_verification.complete_text", _complete)

    def retry(_corrective: str) -> str:
        calls["n"] += 1
        return CLEAN_GLIOMA

    fallback = "Prediction: glioma (91.00%). Template only."
    text, result = enforce_clinical_gate(
        CLEAN_GLIOMA,
        GLIOMA_PAYLOAD,
        fallback_text=fallback,
        retry_fn=retry,
    )
    assert calls["n"] == 1
    assert text == fallback
    assert result.passed is False
    assert result.used_fallback is True
    assert result.contradicted_claims
    assert any(v["type"] == "contradicted_claim" and v.get("tier") == "0" for v in result.violations)


def test_not_addressed_is_warning_not_hard_fail(monkeypatch):
    monkeypatch.setenv("ENABLE_CHAIN_OF_VERIFICATION", "true")
    logged: list[dict] = []

    def _capture(*, event_type, user_id, payload):
        logged.append({"event_type": event_type, "payload": payload})
        return "audit"

    monkeypatch.setattr("src.llm.chain_of_verification.log_report_draft_event", _capture)

    def _complete(prompt, max_tokens=256, **_k):
        if "Split the clinical" in prompt:
            return json.dumps({"claims": ["Routine follow-up at clinical discretion."]})
        return json.dumps({"status": "NOT_ADDRESSED_BY_PAYLOAD", "rationale": "advice not in payload"})

    monkeypatch.setattr("src.llm.chain_of_verification.complete_text", _complete)

    text, result = enforce_clinical_gate(
        CLEAN_GLIOMA,
        GLIOMA_PAYLOAD,
        fallback_text="TEMPLATE",
    )
    assert text == CLEAN_GLIOMA
    assert result.passed is True
    assert result.used_fallback is False
    assert result.unaddressed_claims
    assert not result.contradicted_claims
    assert any(e["event_type"] == "llm_chain_of_verification_review" for e in logged)
    assert logged[0]["payload"]["human_review_required"] is True
    assert logged[0]["payload"]["tier_0_failure"] is False


def test_feature_flag_off_makes_zero_llm_calls(monkeypatch):
    monkeypatch.delenv("ENABLE_CHAIN_OF_VERIFICATION", raising=False)
    monkeypatch.setenv("ENABLE_CHAIN_OF_VERIFICATION", "false")
    calls: list[int] = []

    def _boom(*_a, **_k):
        calls.append(1)
        raise AssertionError("chain-of-verification LLM must not run when the flag is off")

    monkeypatch.setattr("src.llm.chain_of_verification.complete_text", _boom)

    text, result = enforce_clinical_gate(
        CLEAN_GLIOMA,
        GLIOMA_PAYLOAD,
        fallback_text="TEMPLATE",
    )
    assert calls == []
    assert text == CLEAN_GLIOMA
    assert result.passed is True
    assert result.chain_of_verification is None


def test_full_claim_trail_logged_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_CHAIN_OF_VERIFICATION", "true")
    logged: list[dict] = []

    def _capture(*, event_type, user_id, payload):
        logged.append({"event_type": event_type, "payload": payload})
        return "audit"

    monkeypatch.setattr("src.llm.chain_of_verification.log_report_draft_event", _capture)

    def _complete(prompt, max_tokens=256, **_k):
        if "Split the clinical" in prompt:
            return json.dumps({"claims": ["The classifier favors glioma."]})
        return json.dumps({"status": "SUPPORTED", "rationale": "label matches"})

    monkeypatch.setattr("src.llm.chain_of_verification.complete_text", _complete)

    result = run_chain_of_verification(CLEAN_GLIOMA, GLIOMA_PAYLOAD)
    assert result.passed is True
    assert result.claims[0].status == "SUPPORTED"
    assert logged[0]["event_type"] == "llm_chain_of_verification"
    assert logged[0]["payload"]["claims"][0]["status"] == "SUPPORTED"
