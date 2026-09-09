"""Immutable JSONL inference audit trail (research / design-partner workflows)."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _llm_versions_or_empty(prompt_template_name: str) -> dict:
    try:
        from src.llm.versions import llm_version_manifest

        return llm_version_manifest(prompt_template_name)
    except Exception:
        return {}


def _audit_dir() -> Path:
    d = Path(_PROJECT_ROOT / "logs" / "audit")
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_inference(
    file_bytes: bytes,
    filename: str,
    model_name: str,
    model_version: str,
    context: dict,
    request: dict,
    response: dict,
    user_id: str | None,
) -> tuple[str, str]:
    """
    Append one JSONL record. Returns (audit_id, timestamp_utc).
    Omits bulky saliency blobs from persisted response snapshot.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    audit_id = hashlib.sha256(f"{timestamp}{file_hash}{model_name}".encode()).hexdigest()[:16]

    resp_redacted = dict(response)
    if "saliency_map_b64" in resp_redacted and resp_redacted["saliency_map_b64"]:
        resp_redacted["saliency_map_b64"] = "[omitted]"
    wm = resp_redacted.get("wmh") if isinstance(resp_redacted.get("wmh"), dict) else None
    if wm and "saliency_map_b64" in wm:
        wm = dict(wm)
        wm["saliency_map_b64"] = "[omitted]"
        resp_redacted["wmh"] = wm

    record = {
        "audit_id": audit_id,
        "timestamp_utc": timestamp,
        "user_id": user_id,
        "file": {
            "name": filename,
            "sha256": file_hash,
            "size_bytes": len(file_bytes),
        },
        "model": {
            "name": model_name,
            "version": model_version,
        },
        "context": context or {},
        "request_params": request or {},
        "response": resp_redacted,
        "schema_version": "1.0",
    }

    log_path = _audit_dir() / f"{date.today().isoformat()}.jsonl"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")

    return audit_id, timestamp


def audit_record_exists(audit_id: str) -> bool:
    """Linear scan recent JSONL files (small deployments; acceptable for demos)."""
    if not audit_id or len(audit_id) != 16:
        return False
    base = _audit_dir()
    if not base.exists():
        return False
    paths = sorted(base.glob("*.jsonl"), reverse=True)[:120]
    for p in paths:
        try:
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("audit_id") == audit_id:
                        return True
        except OSError:
            continue
    return False


def log_shadow_workflow_event(
    *,
    event_type: str,
    user_id: Optional[str],
    payload: dict,
) -> str:
    """
    Append-only JSONL audit for shadow queue lifecycle (ingest, inference, feedback, export, …).
    Returns a 16-char audit_id (not the same schema as image inference audit_id).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    audit_id = hashlib.sha256(f"{timestamp}{event_type}{json.dumps(payload, sort_keys=True, default=str)}".encode()).hexdigest()[:16]
    record = {
        "audit_id": audit_id,
        "timestamp_utc": timestamp,
        "event_type": event_type,
        "user_id": user_id,
        "payload": payload,
        "schema_version": "1.0",
    }
    log_path = _audit_dir() / "shadow_workflow.jsonl"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
    return audit_id


def log_report_draft_event(
    *,
    event_type: str,
    user_id: Optional[str],
    payload: dict,
) -> str:
    """
    Append-only JSONL audit for structured report drafts (create, edit, sign, …).
    Returns a 16-char audit_id (distinct from image-inference audit_id).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    audit_id = hashlib.sha256(
        f"{timestamp}{event_type}{json.dumps(payload, sort_keys=True, default=str)}".encode()
    ).hexdigest()[:16]
    record = {
        "audit_id": audit_id,
        "timestamp_utc": timestamp,
        "event_type": event_type,
        "user_id": user_id,
        "payload": payload,
        "schema_version": "1.0",
    }
    log_path = _audit_dir() / "report_draft.jsonl"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
    return audit_id


def log_clinical_feedback_audit(
    *,
    event_type: str,
    user_id: Optional[str],
    payload: dict,
) -> str:
    """Append-only JSONL for structured clinical feedback (immutable audit trail)."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    audit_id = hashlib.sha256(
        f"{timestamp}{event_type}{json.dumps(payload, sort_keys=True, default=str)}".encode()
    ).hexdigest()[:16]
    record = {
        "audit_id": audit_id,
        "timestamp_utc": timestamp,
        "event_type": event_type,
        "user_id": user_id,
        "payload": payload,
        "schema_version": "1.0",
    }
    log_path = _audit_dir() / "clinical_feedback_structured.jsonl"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
    return audit_id


def log_docs_assistant_query(
    *,
    user_id: Optional[str],
    question: str,
    doc_filter: Optional[list],
    answer_hash: str,
    citation_count: int,
    confidence: str,
    engine: str,
) -> tuple[str, str]:
    """
    Append a docs assistant query record (JSONL). Returns (audit_id, timestamp_utc).
    Answer text is never stored — only ``answer_hash``. Question is stored for traceability (max 500 chars).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    qhash = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]
    audit_id = hashlib.sha256(f"{timestamp}{qhash}{engine}".encode()).hexdigest()[:16]

    record = {
        "audit_id": audit_id,
        "timestamp_utc": timestamp,
        "event_type": "docs_query",
        "user_id": user_id,
        "engine": engine,
        "payload": {
            "question": (question[:500] + "…") if len(question) > 500 else question,
            "question_sha16": qhash,
            "doc_filter": doc_filter,
            "answer_hash": answer_hash,
            "citation_count": citation_count,
            "confidence": confidence,
            "llm_versions": _llm_versions_or_empty("docs_assistant"),
        },
        "schema_version": "1.0",
    }
    log_path = _audit_dir() / "docs_assistant.jsonl"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")

    return audit_id, timestamp


def append_signoff_event(
    audit_id: str,
    event: str,
    payload: dict,
    user_id: str | None = None,
) -> str:
    """event: sign | defer | feedback_disagree"""
    base = _audit_dir()
    base.mkdir(parents=True, exist_ok=True)
    path = base / "signoffs.jsonl"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rid = hashlib.sha256(f"{ts}{audit_id}{event}{json.dumps(payload, sort_keys=True)}".encode()).hexdigest()[:12]
    record = {
        "signoff_id": rid,
        "timestamp_utc": ts,
        "audit_id": audit_id,
        "event": event,
        "user_id": user_id,
        "payload": payload,
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
    return rid


def log_llm_generation(
    *,
    user_id: Optional[str],
    prompt_template_name: str,
    grounding_payload: Optional[dict] = None,
    gate: object = None,
    output_text: Optional[str] = None,
    model_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> str:
    """
    Append-only JSONL for one LLM generation (event_type=llm_generation).

    Captures the version pin (model, prompt template, guardrail), a compact
    grounding payload (or hash), validator results from Prompts 1/2/4, and a
    hashed/truncated copy of the final text. Images are never stored.
    """
    from src.llm.versions import (
        compact_grounding,
        compact_output,
        llm_version_manifest,
        validator_snapshot,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    versions = llm_version_manifest(prompt_template_name, model_id=model_id)
    payload = {
        **versions,
        "grounding": compact_grounding(grounding_payload),
        "validators": validator_snapshot(gate),
        "output": compact_output(output_text),
    }
    if extra:
        payload["extra"] = extra
    audit_id = hashlib.sha256(
        f"{timestamp}llm_generation{json.dumps(payload, sort_keys=True, default=str)}".encode()
    ).hexdigest()[:16]
    record = {
        "audit_id": audit_id,
        "timestamp_utc": timestamp,
        "event_type": "llm_generation",
        "user_id": user_id,
        "payload": payload,
        "schema_version": "1.1",
    }
    log_path = _audit_dir() / "llm_generation.jsonl"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
    return audit_id


