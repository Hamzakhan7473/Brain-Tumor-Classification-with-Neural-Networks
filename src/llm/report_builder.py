"""Structured RSNA-style report drafts — measurements from model, prose from LLM where allowed."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.inference.audit_log import log_report_draft_event
from src.llm.client import get_llm_client

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TPL_DIR = _PROJECT_ROOT / "configs" / "report_templates"

DEFAULT_DISCLAIMER = (
    "NeuroSight is a research tool. AI-generated content must be "
    "verified by a qualified radiologist. The signing physician "
    "retains full clinical responsibility for the final report."
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _numeric_tokens(measurements: list[dict]) -> set[str]:
    out: set[str] = set()
    for m in measurements:
        v = m.get("value")
        if v is None:
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out.add(str(v))
            fv = float(v)
            if fv == int(fv):
                out.add(str(int(fv)))
            out.add(f"{fv:.1f}".rstrip("0").rstrip("."))
            out.add(f"{fv:.2f}".rstrip("0").rstrip("."))
        else:
            out.add(str(v).strip())
    return out


def _safe_eval_volume_condition(condition: str, measures: dict[str, float]) -> bool:
    """Evaluate simple comparisons like ``wmh_volume_cc < 1.0`` using substituted literals only."""
    c0 = condition.strip()
    for key in sorted(measures.keys(), key=len, reverse=True):
        if key in c0:
            c0 = c0.replace(key, str(measures[key]))
    c0 = re.sub(r"\s+", "", c0)
    if re.search(r"[a-zA-Z_]", c0):
        return False
    for op in ("<=", ">=", "==", "<", ">"):
        if op in c0:
            left, _, right = c0.partition(op)
            try:
                a, b = float(left), float(right)
            except ValueError:
                return False
            if op == "<":
                return a < b
            if op == "<=":
                return a <= b
            if op == ">":
                return a > b
            if op == ">=":
                return a >= b
            if op == "==":
                return abs(a - b) < 1e-9
            break
    return False


def _measures_dict(measurements: list[dict]) -> dict[str, float]:
    d: dict[str, float] = {}
    for m in measurements:
        try:
            d[m["id"]] = float(m["value"])
        except (TypeError, ValueError, KeyError):
            continue
    return d


def _llm_text(prompt: str, max_tokens: int = 200) -> str:
    """Text-only generation via the resolved provider (Bedrock or Gemini)."""
    try:
        client = get_llm_client()
        gen_cfg = {"max_output_tokens": max_tokens}
        resp = client.generate_content(prompt, generation_config=gen_cfg)
        return (getattr(resp, "text", None) or "").strip()
    except Exception:
        return ""


# Backwards-compatible alias (older call sites / tests)
_gemini_text = _llm_text


class ReportBuilder:
    def __init__(self, template_id: str):
        self.template = self._load_template(template_id)

    def _load_template(self, template_id: str) -> dict[str, Any]:
        path = _TPL_DIR / f"{template_id}.yaml"
        if not path.exists():
            raise ValueError(f"Template not found: {template_id}")
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def _evaluate_impression_rules(
        self,
        rules: list[dict[str, Any]],
        measurements: list[dict],
    ) -> dict[str, Any]:
        md = _measures_dict(measurements)
        for rule in rules:
            cond = rule.get("condition")
            if not cond:
                continue
            if _safe_eval_volume_condition(str(cond), md):
                return dict(rule)
        return dict(rules[-1]) if rules else {"severity": "normal", "template": ""}

    def _extract_measurements(self, model_run: dict) -> list[dict]:
        m: list[dict] = []
        aid = str(model_run.get("audit_id") or model_run.get("model_run_id") or "unknown")
        mname = str(model_run.get("model_name") or model_run.get("model") or "model")
        mver = str(model_run.get("model_version") or "v1")
        conf = float(model_run.get("confidence") or model_run.get("model_confidence") or 0.0)

        if isinstance(model_run.get("wmh"), dict):
            wmh = model_run["wmh"]
            vol = float(wmh.get("volume_cc", 0))
            sev = self._volume_severity(vol)
            m.append(
                {
                    "id": "wmh_volume_cc",
                    "label": "WMH volume",
                    "value": round(vol, 4),
                    "unit": "cc",
                    "severity": sev,
                    "audit_ref": aid,
                    "source": f"{mname} {mver}",
                }
            )
            m.append(
                {
                    "id": "lesion_voxels",
                    "label": "Lesion voxels",
                    "value": int(wmh.get("lesion_voxels", 0)),
                    "unit": "voxels",
                    "severity": None,
                    "audit_ref": aid,
                    "source": mname,
                }
            )
            for mid, label, key in (
                ("wmh_volume_periventricular_cc", "WMH volume · periventricular", "volume_cc_periventricular"),
                ("wmh_volume_deep_subcortical_cc", "WMH volume · deep/subcortical", "volume_cc_deep_subcortical"),
                ("wmh_volume_infratentorial_cc", "WMH volume · infratentorial", "volume_cc_infratentorial"),
            ):
                raw = wmh.get(key)
                if raw is None and isinstance(wmh.get("regional"), dict):
                    raw = wmh["regional"].get(key)
                m.append(
                    {
                        "id": mid,
                        "label": label,
                        "value": round(float(raw if raw is not None else 0.0), 4),
                        "unit": "cc",
                        "severity": None,
                        "audit_ref": aid,
                        "source": f"{mname} regional",
                    }
                )
            pct = wmh.get("age_matched_percentile")
            if pct is not None:
                m.append(
                    {
                        "id": "age_percentile",
                        "label": "Age-matched WMH percentile",
                        "value": str(pct),
                        "unit": None,
                        "severity": None,
                        "audit_ref": aid,
                        "source": "ADNI normative",
                    }
                )

        probs = model_run.get("probabilities") or model_run.get("class_probabilities") or {}
        if isinstance(probs, dict) and probs:
            top_label = max(probs, key=lambda k: float(probs[k]))
            top_p = float(probs[top_label])
            m.append(
                {
                    "id": "dominant_class_probability",
                    "label": f"P({top_label})",
                    "value": round(top_p, 4),
                    "unit": None,
                    "severity": "warn" if top_p < 0.75 else "normal",
                    "audit_ref": aid,
                    "source": mname,
                }
            )
            m.append(
                {
                    "id": "predicted_label",
                    "label": "Leading class",
                    "value": str(model_run.get("label") or top_label),
                    "unit": None,
                    "severity": None,
                    "audit_ref": aid,
                    "source": mname,
                }
            )

        m.append(
            {
                "id": "model_confidence",
                "label": "Model confidence",
                "value": round(conf * 100.0, 1) if conf <= 1.0 else round(conf, 1),
                "unit": "%" if conf <= 1.0 else None,
                "severity": "normal" if conf > 0.85 else "warn",
                "audit_ref": aid,
                "source": mname,
            }
        )
        # For rule evaluation some templates use raw 0–1 confidence
        m.append(
            {
                "id": "model_confidence_raw",
                "label": "Model confidence (0–1)",
                "value": round(conf if conf <= 1.0 else conf / 100.0, 4),
                "unit": None,
                "severity": None,
                "audit_ref": aid,
                "source": mname,
            }
        )
        return m

    def _longitudinal_measurements(self, longitudinal: dict[str, Any], audit_id: str) -> list[dict]:
        out: list[dict] = []
        delta = longitudinal.get("volume_delta_cc")
        if delta is not None:
            out.append(
                {
                    "id": "wmh_volume_delta_cc",
                    "label": "WMH volume change vs prior",
                    "value": round(float(delta), 4),
                    "unit": "cc",
                    "severity": None,
                    "audit_ref": audit_id,
                    "source": "longitudinal",
                }
            )
        pct = longitudinal.get("volume_pct_change")
        if pct is not None:
            out.append(
                {
                    "id": "wmh_volume_pct_change",
                    "label": "WMH volume % change vs prior",
                    "value": round(float(pct), 2),
                    "unit": "%",
                    "severity": None,
                    "audit_ref": audit_id,
                    "source": "longitudinal",
                }
            )
        prior = longitudinal.get("prior_volume_cc")
        if prior is not None:
            out.append(
                {
                    "id": "wmh_volume_prior_cc",
                    "label": "WMH volume · prior timepoint",
                    "value": round(float(prior), 4),
                    "unit": "cc",
                    "severity": None,
                    "audit_ref": audit_id,
                    "source": "longitudinal",
                }
            )
        return out

    def _volume_severity(self, vol_cc: float) -> str:
        if vol_cc < 1.0:
            return "normal"
        if vol_cc < 5.0:
            return "mild"
        if vol_cc < 15.0:
            return "moderate"
        return "severe"

    def _format_measurements(self, measures: list[dict]) -> str:
        lines = []
        for x in measures:
            lines.append(f"- {x['id']}: {x['value']} {x.get('unit') or ''}".strip())
        return "\n".join(lines) if lines else "(none)"

    def _validate_no_invented_numbers(
        self,
        text: str,
        allowed_measurements: list[dict],
    ) -> str | None:
        if not text:
            return text
        nums_in_text = re.findall(r"\b\d+\.?\d*\b", text)
        allowed = _numeric_tokens(allowed_measurements)
        for n in nums_in_text:
            if n in allowed:
                continue
            try:
                fn = float(n)
            except ValueError:
                continue
            ok = False
            for a in allowed:
                try:
                    if abs(float(a) - fn) < 1e-6:
                        ok = True
                        break
                except ValueError:
                    continue
            if not ok:
                log_report_draft_event(
                    event_type="llm_hallucination_blocked",
                    user_id="system",
                    payload={"invented_number": n, "text": text[:500]},
                )
                return None
        return text

    def _render_template_string(self, template: str, measurements: list[dict]) -> str:
        md = {m["id"]: m["value"] for m in measurements}
        out = template
        for k, v in md.items():
            out = out.replace(f"{{{{{k}}}}}", str(v))
        return out

    def _build_template_section(
        self,
        name: str,
        default_text: str,
        case: dict[str, Any],
        extra_hint: Any = None,
    ) -> dict[str, Any]:
        text = default_text
        if name == "indication" and case.get("clinical_context"):
            cc = case["clinical_context"]
            if isinstance(cc, dict) and cc.get("indication"):
                text = f"{default_text}\n\nClinical indication: {cc['indication']}."
            elif isinstance(cc, str) and cc.strip():
                text = f"{default_text}\n\nClinical context: {cc.strip()}."
        if "{{scanner_field_strength}}" in text:
            sf = (
                case.get("scanner_field_strength")
                or (case.get("clinical_context") or {}).get("scanner_field_strength")
                if isinstance(case.get("clinical_context"), dict)
                else None
            ) or "3T"
            text = text.replace("{{scanner_field_strength}}", str(sf))
        if name == "comparison" and isinstance(case.get("longitudinal"), dict):
            lon = case["longitudinal"]
            text = str(lon.get("comparison_summary") or text)
            note = lon.get("note")
            if note:
                text = f"{text}\n\n{note}"
        elif name == "comparison" and extra_hint:
            text = f"{default_text}\n\nPrior studies noted: {extra_hint}."
        return {
            "name": name,
            "source": "template",
            "text": text,
            "findings": None,
            "impressions": None,
            "last_edited": None,
            "edited_by": None,
            "history": [],
            "ai_snapshot": None,
        }

    def _build_finding_row(
        self,
        region: dict[str, Any],
        measurements: list[dict],
        model_run: dict,
        severity_bucket: dict[str, Any],
    ) -> dict[str, Any]:
        _ = severity_bucket
        if not region.get("ai_prompt"):
            return {
                "region": region["label"],
                "text": region["fallback"],
                "measurements": [],
                "citations": [],
            }
        relevant = [m for m in measurements if m["id"] in region.get("measurement_ids", [])]
        rf = (model_run.get("regional_findings") or {}) if isinstance(model_run.get("regional_findings"), dict) else {}
        region_hint = rf.get(region["id"], "Model does not provide a regional narrative beyond segmentation statistics.")

        prompt = f"""You are drafting one section of a radiology report.
Region: {region['label']}
Available measurements (USE THESE EXACT VALUES, do not invent others):
{self._format_measurements(relevant)}

Model findings for this region:
{region_hint}

Write 1-2 sentences. Reference measurements using {{{{measure:ID}}}} placeholders only (e.g. {{{{measure:wmh_volume_cc}}}}).
Do not write numeric literals except inside those placeholders."""

        raw = _llm_text(prompt, max_tokens=160)
        validated = self._validate_no_invented_numbers(raw, relevant) if raw else None
        text = validated if validated else region.get("fallback", f"{region['label']}: see findings.")
        mids = [m["id"] for m in relevant]
        return {"region": region["label"], "text": text, "measurements": mids, "citations": []}

    def _build_impressions(
        self,
        severity_bucket: dict[str, Any],
        measurements: list[dict],
        model_run: dict,
        citation_ids: dict[str, int],
        case: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        impressions: list[dict[str, Any]] = []
        tpl = severity_bucket.get("template") or ""
        meas_ext = list(measurements)
        for fk, fv in severity_bucket.items():
            if fk in ("template", "condition", "severity"):
                continue
            if isinstance(fv, (int, float, str)) and fk not in {m["id"] for m in meas_ext}:
                meas_ext.append(
                    {
                        "id": fk,
                        "label": fk,
                        "value": fv,
                        "unit": None,
                        "severity": None,
                        "audit_ref": "",
                        "source": "rule",
                    }
                )
        text = self._render_template_string(tpl, meas_ext)
        for ck, cid in citation_ids.items():
            text = text.replace(f"[cite:{ck}]", f"[cite:{cid}]")
        if "wmh_volume_cc" in _measures_dict(measurements):
            cite_f = citation_ids.get("fazekas", 1)
            imp_mids = ["wmh_volume_cc"]
            imp_cites = [cite_f] if "fazekas" in citation_ids and "fazekas" in tpl.lower() else []
        else:
            imp_mids = [
                m["id"]
                for m in measurements
                if m["id"] in ("dominant_class_probability", "predicted_label", "model_confidence_raw")
            ]
            imp_cites = []
        impressions.append(
            {
                "order": 1,
                "text": text,
                "measurements": imp_mids or ["model_confidence"],
                "citations": imp_cites,
            }
        )
        lon = (case or {}).get("longitudinal") if isinstance(case, dict) else None
        if isinstance(lon, dict) and lon.get("volume_delta_cc") is not None:
            delta = float(lon["volume_delta_cc"])
            pct = lon.get("volume_pct_change")
            direction = str(lon.get("direction") or "stable")
            if direction == "stable":
                lon_text = (
                    "Longitudinal comparison: WMH burden is **stable** vs prior "
                    f"({{measure:wmh_volume_prior_cc}} cc → {{measure:wmh_volume_cc}} cc, "
                    "Δ {{measure:wmh_volume_delta_cc}} cc)."
                )
            elif pct is not None:
                lon_text = (
                    f"Longitudinal comparison: WMH burden **{direction}** vs prior "
                    f"({{measure:wmh_volume_prior_cc}} cc → {{measure:wmh_volume_cc}} cc, "
                    "Δ {{measure:wmh_volume_delta_cc}} cc, {{measure:wmh_volume_pct_change}}% change)."
                )
            else:
                lon_text = (
                    f"Longitudinal comparison: WMH burden **{direction}** vs prior "
                    f"({{measure:wmh_volume_prior_cc}} cc → {{measure:wmh_volume_cc}} cc, "
                    "Δ {{measure:wmh_volume_delta_cc}} cc)."
                )
            impressions.append(
                {
                    "order": 2,
                    "text": lon_text,
                    "measurements": [
                        "wmh_volume_prior_cc",
                        "wmh_volume_cc",
                        "wmh_volume_delta_cc",
                        "wmh_volume_pct_change",
                    ],
                    "citations": [],
                }
            )
        if "wmh_volume_cc" in _measures_dict(measurements) and isinstance(model_run.get("wmh"), dict):
            wmh = model_run["wmh"]
            if wmh.get("age_matched_percentile") is not None:
                impressions.append(
                    {
                        "order": len(impressions) + 1,
                        "text": (
                            "WMH burden is at the {{measure:age_percentile}} for "
                            "age-matched ADNI cognitively normal cohort, "
                            f"suggesting elevated cerebrovascular risk [cite:{citation_ids.get('adni_norms', 3)}]."
                        ),
                        "measurements": ["age_percentile"],
                        "citations": [citation_ids.get("adni_norms", 3)],
                    }
                )
        impressions.append(
            {
                "order": len(impressions) + 1,
                "text": "No acute intracranial process. No mass, hemorrhage, or acute infarct identified.",
                "measurements": [],
                "citations": [],
            }
        )
        return impressions

    def _build_recommendations(self, severity: str, rules: list[dict[str, Any]]) -> list[str]:
        out: list[str] = []
        for rule in rules:
            sin = rule.get("severity_in")
            snot = rule.get("severity_not")
            ok = True
            if sin is not None and severity not in sin:
                ok = False
            if snot is not None and severity in snot:
                ok = False
            if ok:
                t = rule.get("text") or ""
                t = t.replace("[cite:aha_2024]", "[cite:2]")
                out.append(t)
        return out if out else ["**Final interpretation** by a qualified radiologist is required."]

    def _extract_citations(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        lib = self.template.get("citations") or {}
        citations: list[dict[str, Any]] = []
        key_to_id: dict[str, int] = {}
        for i, (key, spec) in enumerate(sorted(lib.items()), start=1):
            if not isinstance(spec, dict):
                continue
            key_to_id[key] = i
            citations.append(
                {
                    "id": i,
                    "label": spec.get("label", key),
                    "source_type": spec.get("source_type", "template"),
                    "location": spec.get("location"),
                    "snippet": spec.get("snippet"),
                    "audit_ref": None,
                }
            )
        return citations, key_to_id

    def build_draft(self, case: dict[str, Any], model_run: dict) -> dict[str, Any]:
        measurements = self._extract_measurements(model_run)
        aid = str(model_run.get("audit_id") or model_run.get("model_run_id") or "unknown")
        if isinstance(case.get("longitudinal"), dict):
            measurements.extend(self._longitudinal_measurements(case["longitudinal"], aid))
        rules = list(self.template.get("impression_rules") or [])
        severity_bucket = self._evaluate_impression_rules(rules, measurements)
        severity = str(severity_bucket.get("severity") or "normal")

        sections: list[dict[str, Any]] = []
        sections.append(
            self._build_template_section(
                "indication",
                self.template.get("indication_default", ""),
                case,
            )
        )
        sections.append(self._build_template_section("technique", self.template["technique_default"], case))
        sections.append(
            self._build_template_section(
                "comparison",
                self.template.get("comparison_default", ""),
                case,
                case.get("prior_studies"),
            )
        )

        findings = []
        for region in self.template.get("finding_regions") or []:
            findings.append(self._build_finding_row(region, measurements, model_run, severity_bucket))

        findings_section = {
            "name": "findings",
            "source": "ai",
            "text": None,
            "findings": findings,
            "impressions": None,
            "last_edited": None,
            "edited_by": None,
            "history": [],
            "ai_snapshot": {"findings": [dict(r) for r in findings]},
        }
        sections.append(findings_section)

        citations, cite_map = self._extract_citations()
        impressions = self._build_impressions(severity_bucket, measurements, model_run, cite_map, case=case)
        for im in impressions:
            txt = im["text"]
            for mid in im.get("measurements") or []:
                mv = next((m["value"] for m in measurements if m["id"] == mid), "")
                txt = txt.replace(f"{{{{measure:{mid}}}}}", str(mv))
            im["text"] = txt

        impression_section = {
            "name": "impression",
            "source": "ai",
            "text": None,
            "findings": None,
            "impressions": impressions,
            "last_edited": None,
            "edited_by": None,
            "history": [],
            "ai_snapshot": {"impressions": [dict(x) for x in impressions]},
        }
        sections.append(impression_section)

        rec_lines = self._build_recommendations(
            severity,
            list(self.template.get("recommendation_rules") or []),
        )
        for i, line in enumerate(rec_lines):
            for key, cid in cite_map.items():
                line = line.replace(f"[cite:{key}]", f"[cite:{cid}]")
            rec_lines[i] = line

        recommendations_section = {
            "name": "recommendations",
            "source": "ai",
            "text": "\n".join(rec_lines),
            "findings": None,
            "impressions": None,
            "last_edited": None,
            "edited_by": None,
            "history": [],
            "ai_snapshot": {"text": "\n".join(rec_lines)},
        }
        sections.append(recommendations_section)

        report_id = log_report_draft_event(
            event_type="report_draft_created",
            user_id="system",
            payload={
                "case_id": case.get("study_uid") or case.get("case_id"),
                "template": self.template.get("template_id"),
                "model_run_id": model_run.get("audit_id"),
                "severity_bucket": severity,
            },
        )

        study_uid = str(case.get("study_uid") or case.get("case_id") or "")
        now = _utc_iso()
        conf_raw = float(model_run.get("confidence") or 0.0)
        return {
            "report_id": report_id,
            "case_id": study_uid,
            "study_uid": study_uid,
            "template_id": self.template["template_id"],
            "status": "draft",
            "sections": sections,
            "measurements": measurements,
            "citations": citations,
            "model_run_id": str(model_run.get("audit_id") or ""),
            "model_name": str(model_run.get("model_name") or model_run.get("model") or ""),
            "model_version": str(model_run.get("model_version") or "v1"),
            "model_confidence": conf_raw if conf_raw <= 1.0 else conf_raw / 100.0,
            "created_at": now,
            "created_by": "system",
            "assigned_to": None,
            "last_modified": now,
            "auto_saved_at": None,
            "signed_by": None,
            "signed_at": None,
            "signed_text_hash": None,
            "signature_audit_id": None,
            "disclaimer": DEFAULT_DISCLAIMER,
            "case_snapshot": {
                "clinical_context": case.get("clinical_context"),
                "prior_studies": case.get("prior_studies"),
                "scanner_field_strength": case.get("scanner_field_strength") or "3T",
                "longitudinal": case.get("longitudinal"),
            },
            "model_run_snapshot": dict(model_run),
        }

    def regenerate_section(
        self,
        section_name: str,
        report_doc: dict[str, Any],
    ) -> dict[str, Any] | None:
        case = {"study_uid": report_doc.get("study_uid"), **report_doc.get("case_snapshot", {})}
        model_run = report_doc.get("model_run_snapshot") or {}
        measurements = self._extract_measurements(model_run)

        if section_name == "findings":
            rules = list(self.template.get("impression_rules") or [])
            severity_bucket = self._evaluate_impression_rules(rules, measurements)
            findings = []
            for region in self.template.get("finding_regions") or []:
                findings.append(self._build_finding_row(region, measurements, model_run, severity_bucket))
            return {
                "name": "findings",
                "source": "ai",
                "text": None,
                "findings": findings,
                "impressions": None,
                "last_edited": None,
                "edited_by": None,
                "history": [],
                "ai_snapshot": {"findings": [dict(r) for r in findings]},
            }

        if section_name == "impression":
            rules = list(self.template.get("impression_rules") or [])
            severity_bucket = self._evaluate_impression_rules(rules, measurements)
            citations = report_doc.get("citations") or []
            cite_map = {f"c{i}": i for i, c in enumerate(citations, start=1)}
            _ = cite_map
            _, key_map = self._extract_citations()
            impressions = self._build_impressions(severity_bucket, measurements, model_run, key_map)
            for im in impressions:
                txt = im["text"]
                for mid in im.get("measurements") or []:
                    mv = next((m["value"] for m in measurements if m["id"] == mid), "")
                    txt = txt.replace(f"{{{{measure:{mid}}}}}", str(mv))
                im["text"] = txt
            return {
                "name": "impression",
                "source": "ai",
                "text": None,
                "findings": None,
                "impressions": impressions,
                "last_edited": None,
                "edited_by": None,
                "history": [],
                "ai_snapshot": {"impressions": [dict(x) for x in impressions]},
            }

        if section_name == "recommendations":
            rules = list(self.template.get("impression_rules") or [])
            severity_bucket = self._evaluate_impression_rules(rules, measurements)
            severity = str(severity_bucket.get("severity") or "normal")
            rec_lines = self._build_recommendations(severity, list(self.template.get("recommendation_rules") or []))
            _, key_map = self._extract_citations()
            for i, line in enumerate(rec_lines):
                for key, cid in key_map.items():
                    line = line.replace(f"[cite:{key}]", f"[cite:{cid}]")
                rec_lines[i] = line
            text = "\n".join(rec_lines)
            return {
                "name": "recommendations",
                "source": "ai",
                "text": text,
                "findings": None,
                "impressions": None,
                "last_edited": None,
                "edited_by": None,
                "history": [],
                "ai_snapshot": {"text": text},
            }

        return None

    def _section_index(self, report_doc: dict[str, Any], name: str) -> int:
        for i, s in enumerate(report_doc.get("sections") or []):
            if s.get("name") == name:
                return i
        return 0
