"""Immutable JSONL inference audit trail (research / design-partner workflows)."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


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

