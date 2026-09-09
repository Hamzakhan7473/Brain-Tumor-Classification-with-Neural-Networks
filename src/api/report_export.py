"""Serialize signed report text, FHIR R4-ish DiagnosticReport JSON, and PDF bytes."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]


def serialize_report_for_hash(report: dict[str, Any]) -> str:
    """Deterministic plain text used for sign-off SHA-256 (radiologist-owned final narrative)."""
    chunks: list[str] = []
    sections = sorted(report.get("sections") or [], key=lambda s: str(s.get("name") or ""))
    for s in sections:
        name = s.get("name") or ""
        if s.get("text"):
            chunks.append(f"[{name}]\n{s['text']}")
        if s.get("findings"):
            for row in s["findings"]:
                chunks.append(f"[{name}:{row.get('region')}]\n{row.get('text') or ''}")
        if s.get("impressions"):
            for im in sorted(s["impressions"], key=lambda x: int(x.get("order") or 0)):
                chunks.append(f"[{name}:{im.get('order')}]\n{im.get('text') or ''}")
    body = "\n\n".join(chunks)
    meta = json.dumps(
        {
            "report_id": report.get("report_id"),
            "study_uid": report.get("study_uid"),
            "template_id": report.get("template_id"),
            "measurements": report.get("measurements"),
        },
        sort_keys=True,
        default=str,
    )
    return body + "\n\n---\n" + meta


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def build_fhir_diagnostic_report(report: dict[str, Any], *, pdf_url: str) -> dict[str, Any]:
    """FHIR R4 DiagnosticReport-shaped document (research build — validate in consuming systems)."""
    assert_export_allowed(report)
    rid = str(report.get("report_id") or "report")
    study = str(report.get("study_uid") or report.get("case_id") or "unknown-study")
    signed_at = str(report.get("signed_at") or report.get("last_modified") or "")
    text_hash = str(report.get("signed_text_hash") or "")
    sig_audit = str(report.get("signature_audit_id") or "")

    impression_lines: list[str] = []
    for s in report.get("sections") or []:
        if s.get("name") == "impression" and s.get("impressions"):
            for im in sorted(s["impressions"], key=lambda x: int(x.get("order") or 0)):
                impression_lines.append(str(im.get("text") or ""))
    conclusion = "\n".join(impression_lines).strip() or "See report sections."

    obs_refs: list[dict[str, str]] = []
    for m in report.get("measurements") or []:
        mid = str(m.get("id") or "obs")
        obs_refs.append(
            {
                "reference": f"Observation/{rid}-{mid}",
                "display": f"{m.get('label') or mid} {m.get('value')} {m.get('unit') or ''}".strip(),
            }
        )

    return {
        "resourceType": "DiagnosticReport",
        "id": rid,
        "meta": {"profile": ["http://hl7.org/fhir/StructureDefinition/DiagnosticReport"]},
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "30746-2",
                    "display": "MR Brain",
                }
            ]
        },
        "subject": {"reference": f"Patient/{study}", "display": study},
        "effectiveDateTime": signed_at,
        "issued": signed_at,
        "performer": [{"reference": f"Practitioner/{report.get('signed_by') or 'unknown'}"}],
        "result": obs_refs,
        "conclusion": conclusion,
        "conclusionCode": [
            {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": "230690007",
                        "display": "Cerebral small vessel disease",
                    }
                ]
            }
        ],
        "presentedForm": [
            {
                "contentType": "application/pdf",
                "url": pdf_url,
                "hash": text_hash,
                "title": "Signed radiology report PDF",
            }
        ],
        "extension": [
            {"url": "https://neurosight.app/fhir/extensions/ai-generated", "valueBoolean": True},
            {"url": "https://neurosight.app/fhir/extensions/audit-id", "valueString": sig_audit},
        ],
    }


def build_fhir_observations_bundle(report: dict[str, Any]) -> dict[str, Any]:
    """Bundle of Observation resources for population-health style queries."""
    rid = str(report.get("report_id") or "report")
    study = str(report.get("study_uid") or "unknown")
    entries: list[dict[str, Any]] = []
    for m in report.get("measurements") or []:
        mid = str(m.get("id") or "m")
        oid = f"{rid}-{mid}"
        entries.append(
            {
                "fullUrl": f"urn:uuid:{oid}",
                "resource": {
                    "resourceType": "Observation",
                    "id": oid,
                    "status": "final",
                    "code": {"text": str(m.get("label") or mid)},
                    "subject": {"reference": f"Patient/{study}"},
                    "valueQuantity": {
                        "value": m.get("value"),
                        "unit": m.get("unit") or "",
                    },
                    "extension": [
                        {
                            "url": "https://neurosight.app/fhir/extensions/model-audit-ref",
                            "valueString": str(m.get("audit_ref") or ""),
                        }
                    ],
                },
            }
        )
    return {"resourceType": "Bundle", "type": "collection", "entry": entries}


def assert_export_allowed(report: dict[str, Any]) -> None:
    """Defense in depth: refuse to serialize unsigned, demo, or 2D-only reports."""
    from src.ingest.path import is_triage_only

    if str(report.get("ingest_path") or "") == "demo":
        raise PermissionError("Demo / non-clinical path cannot be signed or exported.")
    if is_triage_only(report):
        raise PermissionError("2D research triage without a trusted 3D volume cannot be signed or exported.")
    if report.get("status") != "signed":
        raise PermissionError("Report must be signed before PDF/FHIR export.")


def render_report_pdf_bytes(report: dict[str, Any], *, footer_audit: str, footer_hash: str) -> bytes:
    """Render HTML → PDF via WeasyPrint when available; deterministic SOURCE_DATE_EPOCH."""
    assert_export_allowed(report)
    os.environ.setdefault("SOURCE_DATE_EPOCH", "946684800")
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        from weasyprint import HTML
    except ImportError as exc:
        raise RuntimeError("weasyprint and jinja2 are required for PDF export") from exc

    tpl_dir = str(_ROOT / "src" / "api" / "templates")
    env = Environment(
        loader=FileSystemLoader(tpl_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    tpl = env.get_template("report.html")
    html_str = tpl.render(
        report=report,
        footer_audit=footer_audit,
        footer_hash=footer_hash,
    )
    return HTML(string=html_str, base_url=tpl_dir).write_pdf()
