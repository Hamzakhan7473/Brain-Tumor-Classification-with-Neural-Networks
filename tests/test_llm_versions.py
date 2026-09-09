"""Version pinning + llm_generation audit (no AWS credentials)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from src.inference.audit_log import log_llm_generation
from src.llm.validation import ValidationResult
from src.llm.versions import (
    PROMPT_TEMPLATE_VERSION,
    llm_version_manifest,
    pinned_bedrock_model_id,
    startup_version_lines,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _no_latest_alias(monkeypatch):
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    monkeypatch.delenv("BEDROCK_GUARDRAIL_ID", raising=False)
    monkeypatch.delenv("BEDROCK_GUARDRAIL_VERSION", raising=False)


def test_manifest_reads_env_pin_at_call_time(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    monkeypatch.setenv("BEDROCK_GUARDRAIL_ID", "gr-aaa")
    monkeypatch.setenv("BEDROCK_GUARDRAIL_VERSION", "2")
    snap = llm_version_manifest("report")
    assert snap["model_id"] == "us.anthropic.claude-sonnet-4-6"
    assert snap["model_version"] == snap["model_id"]
    assert snap["prompt_template_name"] == "report"
    assert snap["prompt_template_version"] == "v1.0"
    assert snap["prompt_template_version_umbrella"] == PROMPT_TEMPLATE_VERSION
    assert snap["guardrail_id"] == "gr-aaa"
    assert snap["guardrail_version"] == "2"


def test_env_model_id_change_is_picked_up_without_reload(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-a-pinned")
    assert llm_version_manifest("explanation")["model_id"] == "model-a-pinned"
    monkeypatch.setenv("BEDROCK_MODEL_ID", "model-b-pinned")
    snap = llm_version_manifest("explanation")
    assert snap["model_id"] == "model-b-pinned"
    assert snap["model_version"] == "model-b-pinned"
    assert snap["prompt_template_name"] == "explanation"
    assert pinned_bedrock_model_id() == "model-b-pinned"


def test_latest_alias_is_rejected(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "latest")
    with pytest.raises(ValueError, match="pinned"):
        pinned_bedrock_model_id()
    monkeypatch.setenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-6:latest")
    with pytest.raises(ValueError, match="pinned"):
        llm_version_manifest("report")


def test_llm_generation_audit_includes_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.anthropic.claude-test-pin")
    monkeypatch.setenv("BEDROCK_GUARDRAIL_ID", "gr-audit")
    monkeypatch.setenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    monkeypatch.setattr("src.inference.audit_log._audit_dir", lambda: tmp_path)

    gate = ValidationResult(
        passed=True,
        contextual_grounding={"grounding_score": 0.9, "below_threshold": False},
        chain_of_verification={"passed": True, "tier_0_failure": False},
    )
    audit_id = log_llm_generation(
        user_id="tester",
        prompt_template_name="report",
        grounding_payload={"label": "glioma", "confidence": 0.91},
        gate=gate,
        output_text="The classifier favors glioma with confidence 0.91.",
    )
    assert len(audit_id) == 16
    lines = (tmp_path / "llm_generation.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["event_type"] == "llm_generation"
    payload = rec["payload"]
    assert payload["model_id"] == "us.anthropic.claude-test-pin"
    assert payload["model_version"] == "us.anthropic.claude-test-pin"
    assert payload["prompt_template_name"] == "report"
    assert payload["prompt_template_version"] == "v1.0"
    assert payload["guardrail_id"] == "gr-audit"
    assert payload["guardrail_version"] == "DRAFT"
    assert payload["grounding"]["payload"]["label"] == "glioma"
    assert payload["validators"]["prompt_1_deterministic"]["passed"] is True
    assert payload["validators"]["prompt_2_contextual_grounding"]["grounding_score"] == 0.9
    assert payload["validators"]["prompt_4_chain_of_verification"]["passed"] is True
    assert "glioma" in payload["output"]["text"]
    assert "sha256" in payload["output"]


def test_audit_reflects_new_model_id_after_env_change(tmp_path, monkeypatch):
    monkeypatch.setattr("src.inference.audit_log._audit_dir", lambda: tmp_path)
    monkeypatch.setenv("BEDROCK_MODEL_ID", "pin-one")
    log_llm_generation(user_id="t", prompt_template_name="report", output_text="a")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "pin-two")
    log_llm_generation(user_id="t", prompt_template_name="report", output_text="b")
    rows = [
        json.loads(line)
        for line in (tmp_path / "llm_generation.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows[0]["payload"]["model_id"] == "pin-one"
    assert rows[1]["payload"]["model_id"] == "pin-two"


def test_startup_lines_include_live_pin(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "startup-pin-id")
    monkeypatch.setenv("BEDROCK_GUARDRAIL_ID", "gr-start")
    text = "\n".join(startup_version_lines())
    assert "startup-pin-id" in text
    assert "gr-start" in text
    assert "report=v1.0" in text


def test_iam_addon_has_required_logging_actions():
    addon = json.loads(
        (ROOT / "scripts/iam/NeuroSightBedrockInvoke-logging-addon.json").read_text(encoding="utf-8")
    )
    actions = {a for stmt in addon["Statement"] for a in stmt.get("Action", [])}
    for required in (
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "s3:PutObject",
    ):
        assert required in actions


def test_s3_lifecycle_glacier_without_expiration():
    spec = importlib.util.spec_from_file_location(
        "enable_bedrock_invocation_logging",
        ROOT / "scripts/enable_bedrock_invocation_logging.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    rules = mod.s3_lifecycle_configuration("invocations/")
    rule = rules["Rules"][0]
    assert rule["Status"] == "Enabled"
    assert rule["Transitions"][0]["Days"] == 90
    assert rule["Transitions"][0]["StorageClass"] == "GLACIER"
    assert "Expiration" not in rule
    assert mod.HIPAA_MIN_RETENTION_DAYS >= 365 * 6
