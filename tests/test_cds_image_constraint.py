"""FDA Non-Device CDS Criterion 1 — no raw-scan interpretation by the LLM."""

from __future__ import annotations

import sys
import types

import pytest

from src.llm.cds_constraint import MODEL_OVERLAY_CAPTION
from src.llm.validation import (
    validate_clinical_output,
    validate_no_independent_image_interpretation,
)


GLIOMA_PAYLOAD = {
    "label": "glioma",
    "prediction": "glioma",
    "confidence": 0.91,
    "probabilities": {"glioma": 0.91},
}

WMH_PAYLOAD = {
    "measurements": [{"id": "wmh_volume_cc", "value": 10.9, "label": "WMH volume", "unit": "cc"}],
    "wmh": {"volume_cc": 10.9},
}


class _FakeBedrockRuntime:
    def __init__(self):
        self.calls: list[dict] = []
        self.response = {
            "output": {"message": {"content": [{"text": "The classifier predicted glioma (0.91)."}]}},
            "usage": {"totalTokens": 12},
        }

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


@pytest.fixture()
def fake_boto3(monkeypatch):
    runtime = _FakeBedrockRuntime()
    module = types.ModuleType("boto3")
    module.client = lambda service, **kw: runtime  # noqa: ARG005
    monkeypatch.setitem(sys.modules, "boto3", module)
    return runtime


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("LLM_PROVIDER", "BEDROCK_MODEL_ID", "BEDROCK_GUARDRAIL_ID", "BEDROCK_GUARDRAIL_VERSION"):
        monkeypatch.delenv(var, raising=False)


def test_flags_independent_visual_language():
    bad = "I can see a hyperintense lesion. The image shows midline shift."
    result = validate_no_independent_image_interpretation(bad, GLIOMA_PAYLOAD)
    assert result.passed is False
    assert result.independent_visual_claims
    assert any("i can see" in c.lower() or "image shows" in c.lower() for c in result.independent_visual_claims)


def test_does_not_flag_model_measurement_narration():
    ok = "The model measured 10.9 cc of white-matter hyperintensity volume."
    result = validate_no_independent_image_interpretation(ok, WMH_PAYLOAD)
    assert result.passed is True
    assert result.independent_visual_claims == []


def test_does_not_flag_saliency_overlay_narration():
    ok = (
        "The highlighted region corresponds to elevated signal per the saliency map "
        "produced by the classifier."
    )
    result = validate_no_independent_image_interpretation(ok, GLIOMA_PAYLOAD)
    assert result.passed is True
    assert result.independent_visual_claims == []


def test_visual_check_is_in_clinical_gate():
    text = "Upon inspection of the scan I can see hemorrhage in the left temporal lobe."
    combined = validate_clinical_output(text, GLIOMA_PAYLOAD)
    assert combined.passed is False
    assert any(v["type"] == "independent_visual_interpretation" for v in combined.violations)


def test_explain_image_does_not_pass_raw_scan(monkeypatch):
    captured: list[dict] = []

    def _fake_prose(prompt, **kwargs):
        captured.append({"prompt": prompt, **kwargs})
        return "The classifier predicted glioma with confidence 0.91.", {}

    monkeypatch.setattr("src.llm.explanations.generate_clinical_prose", _fake_prose)
    from src.llm.explanations import explain_image

    text, _gate, _prov = explain_image(
        "glioma",
        confidence=0.91,
        probabilities={"glioma": 0.91},
        visual_overlay=None,
    )
    assert captured
    assert captured[0].get("visual_overlay") is None
    assert "image" not in captured[0]
    assert "narrating results" in captured[0]["prompt"].lower()
    assert "glioma" in text.lower() or "classifier" in text.lower()


def test_clinical_prose_without_overlay_has_no_image_block(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    from src.llm.client import generate_clinical_prose

    generate_clinical_prose(
        "Narrate the classifier output.",
        query="explain findings",
        grounding_payload=GLIOMA_PAYLOAD,
        visual_overlay=None,
    )
    assert fake_boto3.calls
    content = fake_boto3.calls[0]["messages"][0]["content"]
    assert not any("image" in block for block in content)
    joined = " ".join(block.get("text", "") for block in content)
    assert "must not independently interpret" in joined.lower() or "narrating results" in joined.lower()


def test_overlay_is_labeled_and_raw_scan_is_not_attached(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    monkeypatch.setenv("BEDROCK_GUARDRAIL_ID", "gr-1")
    from src.llm.client import generate_clinical_prose

    raw_scan = b"\xff\xd8\xff" + b"RAW_DIAGNOSTIC_PIXELS"
    overlay = b"\x89PNG\r\n\x1a\n" + b"HEATMAP_ONLY"
    generate_clinical_prose(
        "Narrate the classifier output.",
        query="explain findings",
        grounding_payload=GLIOMA_PAYLOAD,
        visual_overlay=overlay,
    )
    content = fake_boto3.calls[0]["messages"][0]["content"]
    images = [b["image"]["source"]["bytes"] for b in content if "image" in b]
    assert images == [overlay]
    assert raw_scan not in images
    texts = []
    for block in content:
        if "text" in block:
            texts.append(block["text"])
        gc = (block.get("guardContent") or {}).get("text") or {}
        if gc.get("text"):
            texts.append(gc["text"])
    assert any(MODEL_OVERLAY_CAPTION[:40] in t for t in texts)
