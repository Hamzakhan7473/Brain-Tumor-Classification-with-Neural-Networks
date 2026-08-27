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
