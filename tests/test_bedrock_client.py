"""Bedrock provider layer — stubbed boto3, no AWS required."""

from __future__ import annotations

import sys
import types

import pytest


class _FakeBedrockRuntime:
    """Records converse() kwargs and returns a canned response."""

    def __init__(self):
        self.calls: list[dict] = []
        self.response = {
            "output": {"message": {"content": [{"text": "GENERATED TEXT"}]}},
            "usage": {"totalTokens": 42},
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


def test_generate_content_text_only(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
    from src.llm.bedrock import BedrockClient

    client = BedrockClient()
    resp = client.generate_content("Write one sentence.", generation_config={"max_output_tokens": 160})

    assert resp.text == "GENERATED TEXT"
    assert resp.usage_metadata.total_token_count == 42
    call = fake_boto3.calls[0]
    assert call["modelId"] == "us.anthropic.claude-sonnet-4-20250514-v1:0"
    assert call["inferenceConfig"]["maxTokens"] == 160
    assert call["messages"][0]["content"] == [{"text": "Write one sentence."}]
    assert "guardrailConfig" not in call


def test_guardrail_config_applied(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    monkeypatch.setenv("BEDROCK_GUARDRAIL_ID", "gr-123")
    monkeypatch.setenv("BEDROCK_GUARDRAIL_VERSION", "3")
    from src.llm.bedrock import BedrockClient

    BedrockClient().generate_content("hello")
    call = fake_boto3.calls[0]
    assert call["guardrailConfig"] == {"guardrailIdentifier": "gr-123", "guardrailVersion": "3"}


def test_image_bytes_become_image_block(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    from src.llm.bedrock import BedrockClient

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    BedrockClient().generate_content(["describe this", png])
    content = fake_boto3.calls[0]["messages"][0]["content"]
    assert content[0] == {"text": "describe this"}
    assert content[1]["image"]["format"] == "png"
    assert content[1]["image"]["source"]["bytes"] == png


def test_provider_resolution_prefers_bedrock_when_configured(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    from src.llm.bedrock import BedrockClient
    from src.llm.client import get_llm_client, resolve_default_provider

    assert resolve_default_provider() == "bedrock"
    assert isinstance(get_llm_client(), BedrockClient)


def test_provider_resolution_falls_back_to_gemini(monkeypatch):
    from src.llm.client import resolve_default_provider

    assert resolve_default_provider() == "gemini"


def test_explicit_llm_provider_env_wins(fake_boto3, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    from src.llm.bedrock import BedrockClient
    from src.llm.client import get_llm_client

    assert isinstance(get_llm_client(), BedrockClient)


def test_generate_with_image_routes_bedrock_directly(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    from src.llm.bedrock import BedrockClient
    from src.llm.client import generate_with_image

    jpeg = b"\xff\xd8\xff" + b"0" * 16
    out = generate_with_image(BedrockClient(), jpeg, "explain")
    assert out == "GENERATED TEXT"
    content = fake_boto3.calls[0]["messages"][0]["content"]
    assert content[1]["image"]["format"] == "jpeg"


def test_features_capabilities_report_bedrock(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from src.api.features import _capabilities

    cap = _capabilities()
    assert cap.bedrock_configured is True
    assert cap.llm_configured is True
    assert cap.llm_provider == "bedrock"


def _trace(grounding: float, relevance: float, g_thr: float = 0.75, r_thr: float = 0.75) -> dict:
    return {
        "guardrail": {
            "outputAssessments": {
                "gr-123": [
                    {
                        "contextualGroundingPolicy": {
                            "filters": [
                                {"type": "GROUNDING", "score": grounding, "threshold": g_thr, "action": "NONE"},
                                {"type": "RELEVANCE", "score": relevance, "threshold": r_thr, "action": "NONE"},
                            ]
                        }
                    }
                ]
            }
        }
    }


def test_generate_grounded_content_attaches_qualifiers(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    from src.llm.bedrock import BedrockClient

    fake_boto3.response["trace"] = _trace(0.9, 0.88)
    client = BedrockClient()
    resp = client.generate_grounded_content(
        query="Draft findings",
        grounding_source='{"label":"glioma","confidence":0.91}',
        prompt="Write 1-2 sentences.",
        guardrail_id="gr-123",
        guardrail_version="DRAFT",
    )
    call = fake_boto3.calls[0]
    content = call["messages"][0]["content"]
    assert content[0]["guardContent"]["text"]["qualifiers"] == ["grounding_source"]
    assert content[0]["guardContent"]["text"]["text"] == '{"label":"glioma","confidence":0.91}'
    assert content[1]["guardContent"]["text"]["qualifiers"] == ["query"]
    assert content[1]["guardContent"]["text"]["text"] == "Draft findings"
    assert content[2] == {"text": "Write 1-2 sentences."}
    assert call["guardrailConfig"] == {
        "guardrailIdentifier": "gr-123",
        "guardrailVersion": "DRAFT",
        "trace": "enabled",
    }
    assert resp.grounding_score == 0.9
    assert resp.relevance_score == 0.88
    assert resp.below_threshold is False
    assert resp.human_review is False


def test_generate_grounded_content_omits_guardrail_config_when_unset(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    from src.llm.bedrock import BedrockClient

    BedrockClient().generate_grounded_content(
        query="q",
        grounding_source="{}",
        prompt="p",
    )
    call = fake_boto3.calls[0]
    assert "guardrailConfig" not in call
    content = call["messages"][0]["content"]
    assert content[0]["guardContent"]["text"]["qualifiers"] == ["grounding_source"]
    assert content[1]["guardContent"]["text"]["qualifiers"] == ["query"]


def test_grounding_source_oversize_raises(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    from src.llm.bedrock import GROUNDING_SOURCE_MAX_CHARS, BedrockClient, serialize_grounding_source

    client = BedrockClient()
    huge = "x" * (GROUNDING_SOURCE_MAX_CHARS + 1)
    with pytest.raises(ValueError, match="grounding_source"):
        client.generate_grounded_content(query="q", grounding_source=huge, prompt="p")
    assert fake_boto3.calls == []

    with pytest.raises(ValueError, match="grounding_source"):
        serialize_grounding_source({"label": "x" * (GROUNDING_SOURCE_MAX_CHARS + 50)})


def test_query_is_truncated_to_1000_chars(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    from src.llm.bedrock import QUERY_MAX_CHARS, BedrockClient

    BedrockClient().generate_grounded_content(
        query="Q" * (QUERY_MAX_CHARS + 80),
        grounding_source="{}",
        prompt="p",
    )
    query_text = fake_boto3.calls[0]["messages"][0]["content"][1]["guardContent"]["text"]["text"]
    assert len(query_text) <= QUERY_MAX_CHARS
    assert query_text.endswith("…")


def test_grounding_scores_logged_and_do_not_fail_deterministic_gate(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    logged: list[dict] = []

    def _capture(*, event_type, user_id, payload):
        logged.append({"event_type": event_type, "user_id": user_id, "payload": payload})
        return "audit"

    monkeypatch.setattr("src.llm.validation.log_report_draft_event", _capture)

    from src.llm.bedrock import BedrockClient
    from src.llm.validation import ValidationResult, log_grounding_assessment

    fake_boto3.response["trace"] = _trace(0.40, 0.90, g_thr=0.75, r_thr=0.75)
    client = BedrockClient()
    grounded = client.generate_grounded_content(
        query="q",
        grounding_source='{"label":"glioma"}',
        prompt="p",
        guardrail_id="gr-123",
    )
    assert grounded.grounding_score == 0.40
    assert grounded.relevance_score == 0.90
    assert grounded.below_threshold is True
    assert grounded.human_review is True

    gate = ValidationResult(passed=True)
    log_grounding_assessment(grounded.to_meta(), gate)
    assert logged, "expected an audit event"
    event = logged[0]
    assert event["event_type"] == "llm_contextual_grounding_review"
    assert event["payload"]["grounding_score"] == 0.40
    assert event["payload"]["relevance_score"] == 0.90
    assert event["payload"]["human_review_required"] is True
    assert event["payload"]["deterministic_passed"] is True
    assert gate.passed is True


def _tool_response(name: str, payload: dict) -> dict:
    return {
        "output": {"message": {"content": [{"toolUse": {"name": name, "input": payload}}]}},
        "usage": {"totalTokens": 12},
    }


def test_generate_structured_narrative_rejects_numeric_field(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    from pydantic import BaseModel
    from src.llm.bedrock import BedrockClient
    from src.llm.narrative_schema import ReportNarrative, StructuredNarrativeError

    fake_boto3.response = _tool_response(
        "report_narrative",
        {
            "findings_narrative": "WMH volume measured at {wmh_volume_cc} cc",
            "impression_narrative": "Burden is moderate.",
            "wmh_volume_cc": 10.9,
        },
    )
    client = BedrockClient()
    with pytest.raises(StructuredNarrativeError, match="numeric"):
        client.generate_structured_narrative(
            {"measurements": [{"id": "wmh_volume_cc", "value": 10.9}]},
            ReportNarrative,
        )
    call = fake_boto3.calls[0]
    assert call["toolConfig"]["toolChoice"] == {"tool": {"name": "report_narrative"}}
    props = call["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"]["properties"]
    assert "wmh_volume_cc" not in props
    for spec in props.values():
        types = spec.get("type")
        types = types if isinstance(types, list) else [types]
        assert "number" not in types
        assert "integer" not in types

    class NumericLeakSchema(BaseModel):
        findings_narrative: str
        wmh_volume_cc: float

    with pytest.raises(StructuredNarrativeError, match="text-only"):
        client.generate_structured_narrative({}, NumericLeakSchema)
    assert len(fake_boto3.calls) == 1


def test_generate_structured_narrative_rejects_embedded_number(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    from src.llm.bedrock import BedrockClient
    from src.llm.narrative_schema import ReportNarrative, StructuredNarrativeError

    fake_boto3.response = _tool_response(
        "report_narrative",
        {
            "findings_narrative": "WMH volume measured at 10.9 cc",
            "impression_narrative": "Stable.",
        },
    )
    client = BedrockClient()
    with pytest.raises(StructuredNarrativeError, match="numeric literals"):
        client.generate_structured_narrative(
            {"measurements": [{"id": "wmh_volume_cc", "value": 10.9}]},
            ReportNarrative,
        )


def test_generate_structured_narrative_accepts_placeholders(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    from src.llm.bedrock import BedrockClient
    from src.llm.narrative_schema import ReportNarrative

    fake_boto3.response = _tool_response(
        "report_narrative",
        {
            "findings_narrative": "WMH volume measured at {wmh_volume_cc} cc",
            "impression_narrative": "Burden is moderate relative to {wmh_volume_cc} cc.",
        },
    )
    parsed = BedrockClient().generate_structured_narrative(
        {"measurements": [{"id": "wmh_volume_cc", "value": 10.9}]},
        ReportNarrative,
    )
    assert parsed.findings_narrative == "WMH volume measured at {wmh_volume_cc} cc"
    assert "10.9" not in parsed.findings_narrative
    content = fake_boto3.calls[0]["messages"][0]["content"]
    assert content[0]["guardContent"]["text"]["qualifiers"] == ["grounding_source"]
    assert content[1]["guardContent"]["text"]["qualifiers"] == ["query"]


def test_generate_tool_json_uses_strict_tool_choice(fake_boto3, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-x")
    from src.llm.bedrock import BedrockClient

    fake_boto3.response = {
        "output": {
            "message": {
                "content": [
                    {"toolUse": {"name": "claim_verdict", "input": {"status": "SUPPORTED", "rationale": "ok"}}}
                ]
            }
        }
    }
    data = BedrockClient().generate_tool_json(
        "Classify the claim.",
        {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]},
        tool_name="claim_verdict",
        generation_config={"max_output_tokens": 80, "temperature": 0},
    )
    assert data == {"status": "SUPPORTED", "rationale": "ok"}
    call = fake_boto3.calls[0]
    assert call["toolConfig"]["toolChoice"] == {"tool": {"name": "claim_verdict"}}
    assert call["inferenceConfig"]["temperature"] == 0.0

