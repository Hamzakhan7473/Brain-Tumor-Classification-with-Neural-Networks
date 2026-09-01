"""Structured RSNA-style report drafts — measurements from model, prose from LLM where allowed."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.inference.audit_log import log_report_draft_event
from src.llm.client import generate_clinical_prose, get_llm_client
from src.llm.narrative_schema import (
    RegionNarrative,
    StructuredNarrativeError,
    interpolate_narrative,
    leaked_numeric_literals,
    log_structured_number_leak,
)
from src.llm.validation import (
    ValidationResult,
    enforce_clinical_gate,
    grounding_from_measurements,
    log_grounding_assessment,
    validate_no_invented_numbers,
)
from src.llm.versions import audit_llm_generation


def _draft_provenance(finding_gates: list[ValidationResult]) -> dict[str, Any]:
    from src.llm.content_provenance import build_content_provenance

    combined = ValidationResult.combine(*finding_gates) if finding_gates else ValidationResult(passed=True)
    return build_content_provenance(prompt_template_name="report_draft", gate=combined)

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


def _llm_text(
    prompt: str,
    max_tokens: int = 200,
    *,
    grounding_payload: dict | None = None,
    query: str | None = None,
) -> tuple[str, dict]:
    """Text-only generation. Never attach scan pixels (FDA Non-Device CDS Criterion 1)."""
    if grounding_payload is not None:
        try:
            return generate_clinical_prose(
                prompt,
                query=query or "Draft the clinical findings section.",
                grounding_payload=grounding_payload,
                max_tokens=max_tokens,
            )
        except Exception:
            return "", {}
    try:
        client = get_llm_client()
        gen_cfg = {"max_output_tokens": max_tokens}
        resp = client.generate_content(prompt, generation_config=gen_cfg)
        return (getattr(resp, "text", None) or "").strip(), {}
    except Exception:
        return "", {}


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

    def _format_measurement_slots(self, measures: list[dict]) -> str:
        lines = []
        for x in measures:
            unit = x.get("unit") or ""
            lines.append(f"- {{{x['id']}}}  ({x.get('label') or x['id']}{(' ' + unit) if unit else ''})")
        return "\n".join(lines) if lines else "(none)"

    def _llm_region_narrative(
        self,
        prompt: str,
        payload: dict,
        region: dict[str, Any],
        relevant: list[dict],
    ) -> tuple[str, dict]:
        """Prefer Bedrock structured (text-only) output; fall back to free-text generation."""
        query = f"Draft the {region.get('label') or 'findings'} section using measurement slots only."
        try:
            from src.llm.bedrock import BedrockClient

            client = get_llm_client()
            if isinstance(client, BedrockClient):
                try:
                    nar = client.generate_structured_narrative(
                        payload,
                        RegionNarrative,
                        prompt=prompt,
                        query=query,
                        generation_config={"max_output_tokens": 160},
                        tool_name="region_narrative",
                    )
                    meta = getattr(client, "last_grounding_meta", {}) or {}
                    return (getattr(nar, "text", None) or "").strip(), meta
                except StructuredNarrativeError:
                    # Schema-layer failure: do not retry as free text (that would
                    # re-enable number invention). Caller uses the template fallback.
                    return "", {}
        except Exception:
            pass
        try:
            return _llm_text(
                prompt,
                max_tokens=160,
                grounding_payload=payload,
                query=query,
            )
        except Exception:
            return "", {}

    def _validate_no_invented_numbers(
        self,
        text: str,
        allowed_measurements: list[dict],
    ) -> str | None:
        """Backward-compatible wrapper around the shared number gate."""
        if not text:
            return text
        result = validate_no_invented_numbers(text, {"measurements": allowed_measurements})
        if result.passed:
            return text
        for n in result.invented_numbers:
            log_report_draft_event(
                event_type="llm_hallucination_blocked",
                user_id="system",
                payload={"invented_number": n, "text": text[:500]},
            )
        return None

    def _render_template_string(self, template: str, measurements: list[dict]) -> str:
        return interpolate_narrative(template, measurements)

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
Available measurement SLOTS (insert these placeholders — never write the numbers yourself):
{self._format_measurement_slots(relevant)}

Model findings for this region:
{region_hint}

Write 1-2 sentences of prose. Quantities MUST appear only as {{slot_id}} placeholders
(e.g. {{wmh_volume_cc}} or {{{{measure:wmh_volume_cc}}}}). Do not write numeric literals.
Do not name anatomical regions, findings, or severity grades that are not in the measurements above."""

        fallback = region.get("fallback", f"{region['label']}: see findings.")
        payload = grounding_from_measurements(
            relevant,
            model_run=None,
            regions=[region.get("label"), region.get("id")],
        )
        mids = set(region.get("measurement_ids") or [])
        if mids & {"predicted_label", "dominant_class_probability", "model_confidence", "model_confidence_raw"}:
            payload["label"] = model_run.get("label") or model_run.get("prediction")
            payload["confidence"] = model_run.get("confidence")
            payload["probabilities"] = model_run.get("probabilities") or model_run.get("class_probabilities")
        if any(str(mid).startswith("wmh") or str(mid) in {"lesion_voxels", "age_percentile"} for mid in mids):
            if isinstance(model_run.get("wmh"), dict):
                payload["wmh"] = model_run["wmh"]

        raw, gmeta = self._llm_region_narrative(prompt, payload, region, relevant)
        if not (raw or "").strip():
            text, gate = fallback, ValidationResult(passed=True, used_fallback=True)
        else:
            leaked = leaked_numeric_literals(raw)
            if leaked:
                log_structured_number_leak({"region": leaked}, raw)
                text, gate = fallback, ValidationResult(passed=True, used_fallback=True)
            else:
                interpolated = interpolate_narrative(raw, relevant)

                def _retry(corrective: str) -> str:
                    retry_text, _retry_meta = self._llm_region_narrative(
                        prompt + "\n\n" + corrective,
                        payload,
                        region,
                        relevant,
                    )
                    if _retry_meta:
                        gmeta.update(_retry_meta)
                    if leaked_numeric_literals(retry_text):
                        log_structured_number_leak({"region_retry": leaked_numeric_literals(retry_text)}, retry_text)
                        return ""
                    return interpolate_narrative(retry_text, relevant)

                text, gate = enforce_clinical_gate(
                    interpolated,
                    payload,
                    fallback_text=fallback,
                    retry_fn=_retry,
                )
        if gmeta:
            gate.contextual_grounding = gmeta
            log_grounding_assessment(gmeta, gate)
        audit_llm_generation(
            prompt_template_name="report_draft",
            output_text=text,
            grounding_payload=payload,
            gate=gate,
        )
        mids_out = [m["id"] for m in relevant]
        return {
            "region": region["label"],
            "text": text,
            "measurements": mids_out,
            "citations": [],
            "validation": gate.to_dict(),
        }

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
        for im in impressions:
            im["text"] = interpolate_narrative(im.get("text") or "", meas_ext)
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
        finding_gates: list[ValidationResult] = []
        for region in self.template.get("finding_regions") or []:
            row = self._build_finding_row(region, measurements, model_run, severity_bucket)
            findings.append(row)
            v = row.get("validation")
            if isinstance(v, dict):
                finding_gates.append(
                    ValidationResult(
                        passed=bool(v.get("passed")),
                        invented_numbers=list(v.get("invented_numbers") or []),
                        invented_entities=list(v.get("invented_entities") or []),
                        omitted_findings=list(v.get("omitted_findings") or []),
                        contradicted_claims=list(v.get("contradicted_claims") or []),
                        unaddressed_claims=list(v.get("unaddressed_claims") or []),
                        used_fallback=bool(v.get("used_fallback")),
                        regenerated=bool(v.get("regenerated")),
                        chain_of_verification=v.get("chain_of_verification")
                        if isinstance(v.get("chain_of_verification"), dict)
                        else None,
                    )
                )

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
            im["text"] = interpolate_narrative(im.get("text") or "", measurements)

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
            "provenance": _draft_provenance(finding_gates),
            "attested_by": None,
            "attested_at": None,
            "attestation_text": None,
            "attestation_audit_id": None,
            "validation": (
                ValidationResult.combine(*finding_gates).to_dict()
                if finding_gates
                else ValidationResult(passed=True).to_dict()
            ),
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
                im["text"] = interpolate_narrative(im.get("text") or "", measurements)
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
