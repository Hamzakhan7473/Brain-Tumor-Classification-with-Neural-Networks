"""
Deterministic clinical-output gate for LLM prose.

This is the authoritative safety check in front of every report / explanation
path. Later prompt changes must not bypass it.

Checks:
  1. No invented numbers (existing behaviour, extracted here).
  2. Faithfulness / precision — clinical entities in the prose must appear in
     the deterministic grounding payload (CNN label, WMH volumes, regions).
  3. Recall — material findings in the payload must be mentioned in the prose.
  4. No independent image interpretation — prose must not claim to have
     visually read the scan (FDA Non-Device CDS Criterion 1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Optional

from src.inference.audit_log import log_report_draft_event

# ── Materiality (recall) ─────────────────────────────────────────────────────
DEFAULT_MATERIALITY: dict[str, float] = {
    "tumor_confidence": 0.55,
    "wmh_volume_cc": 1.0,
    "regional_volume_cc": 1.0,
}

_NEGATIVE_LABELS = frozenset(
    {"notumor", "no_tumor", "no-tumor", "no tumor", "background", "negative"}
)

# ── Controlled vocabulary (longest phrases first at runtime) ────────────────
# Only these clinical terms are gated. Everyday words are ignored.
_FINDING_TERMS: tuple[str, ...] = (
    "white matter hyperintensities",
    "white-matter hyperintensities",
    "white matter hyperintensity",
    "white-matter hyperintensity",
    "high-grade glioma",
    "low-grade glioma",
    "pituitary macroadenoma",
    "pituitary microadenoma",
    "pituitary adenoma",
    "midline shift",
    "mass effect",
    "vasogenic edema",
    "cytotoxic edema",
    "acute infarct",
    "chronic infarct",
    "intracranial hemorrhage",
    "subarachnoid hemorrhage",
    "subdural hematoma",
    "epidural hematoma",
    "leukoaraiosis",
    "hydrocephalus",
    "herniation",
    "microbleed",
    "microbleeds",
    "metastasis",
    "metastases",
    "meningioma",
    "glioblastoma",
    "glioma",
    "pituitary",
    "hemorrhage",
    "haemorrhage",
    "hematoma",
    "infarct",
    "infarction",
    "stroke",
    "edema",
    "oedema",
    "abscess",
    "aneurysm",
    "stenosis",
    "fazekas",
    "wmh",
)

_ANATOMY_TERMS: tuple[str, ...] = (
    "deep subcortical",
    "deep/subcortical",
    "posterior fossa",
    "basal ganglia",
    "corpus callosum",
    "periventricular",
    "infratentorial",
    "supratentorial",
    "subcortical",
    "hippocampus",
    "thalamus",
    "brainstem",
    "cerebellum",
    "occipital",
    "parietal",
    "temporal",
    "frontal",
    "insula",
    "sylvian",
    "hippocampal",
    "caudate",
    "putamen",
)

_SEVERITY_TERMS: tuple[str, ...] = (
    "very high",
    "high-grade",
    "low-grade",
    "critical",
    "severe",
    "moderate",
    "mild",
)

_CLASS_LABELS: tuple[str, ...] = ("glioma", "meningioma", "pituitary", "notumor", "no tumor")

_ALL_GATED_PHRASES: tuple[str, ...] = tuple(
    sorted(
        set(_FINDING_TERMS + _ANATOMY_TERMS + _SEVERITY_TERMS + _CLASS_LABELS),
        key=lambda s: (-len(s), s),
    )
)

# Survey anatomy that a brain MRI report may name without a dedicated payload row.
_SURVEY_ANATOMY = frozenset(
    {
        "brain",
        "ventricle",
        "ventricles",
        "cortex",
        "cortical",
        "white matter",
        "vasculature",
        "sulci",
        "sulcus",
    }
)

_SEVERITY_RANK = {
    "normal": 0,
    "mild": 1,
    "moderate": 2,
    "severe": 3,
    "critical": 4,
    "high-grade": 3,
    "very high": 4,
    "low-grade": 1,
}

_ENTITY_ALIASES: dict[str, frozenset[str]] = {
    "glioma": frozenset({"glioma", "gliomas", "glial", "glioblastoma", "high-grade glioma", "low-grade glioma"}),
    "meningioma": frozenset({"meningioma", "meningiomas"}),
    "pituitary": frozenset(
        {"pituitary", "pituitary adenoma", "pituitary macroadenoma", "pituitary microadenoma"}
    ),
    "notumor": frozenset({"notumor", "no tumor", "no-tumor", "no_tumor", "tumor-negative"}),
    "wmh": frozenset(
        {
            "wmh",
            "white matter hyperintensity",
            "white matter hyperintensities",
            "white-matter hyperintensity",
            "white-matter hyperintensities",
            "leukoaraiosis",
        }
    ),
    "periventricular": frozenset({"periventricular"}),
    "deep subcortical": frozenset({"deep subcortical", "deep/subcortical", "subcortical"}),
    "infratentorial": frozenset({"infratentorial", "posterior fossa", "brainstem", "cerebellum"}),
    "supratentorial": frozenset({"supratentorial"}),
}

_MEASUREMENT_ID_ENTITIES: dict[str, tuple[str, ...]] = {
    "wmh_volume_cc": ("wmh", "white matter"),
    "wmh_volume_periventricular_cc": ("periventricular", "wmh"),
    "wmh_volume_deep_subcortical_cc": ("deep subcortical", "wmh"),
    "wmh_volume_infratentorial_cc": ("infratentorial", "wmh"),
    "lesion_voxels": ("wmh",),
    "age_percentile": ("wmh",),
    "predicted_label": (),
    "dominant_class_probability": (),
    "wmh_volume_delta_cc": ("wmh",),
    "wmh_volume_prior_cc": ("wmh",),
}


@dataclass
class ValidationResult:
    passed: bool
    invented_numbers: list[str] = field(default_factory=list)
    invented_entities: list[str] = field(default_factory=list)
    omitted_findings: list[str] = field(default_factory=list)
    contradicted_claims: list[str] = field(default_factory=list)
    unaddressed_claims: list[str] = field(default_factory=list)
    independent_visual_claims: list[str] = field(default_factory=list)
    rejection_codes: list[str] = field(default_factory=list)
    used_fallback: bool = False
    regenerated: bool = False
    contextual_grounding: Optional[dict] = None
    chain_of_verification: Optional[dict] = None

    @property
    def violations(self) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for n in self.invented_numbers:
            out.append({"type": "invented_number", "value": n, "severity": "high"})
        for e in self.invented_entities:
            out.append({"type": "invented_entity", "value": e, "severity": "high"})
        for fnd in self.omitted_findings:
            out.append({"type": "omitted_finding", "value": fnd, "severity": "high"})
        for c in self.contradicted_claims:
            out.append({"type": "contradicted_claim", "value": c, "severity": "high", "tier": "0"})
        for v in self.independent_visual_claims:
            out.append(
                {
                    "type": "independent_visual_interpretation",
                    "value": v,
                    "severity": "high",
                    "tier": "cds1",
                }
            )
        for code in self.rejection_codes:
            out.append({"type": code, "value": code, "severity": "high"})
        return out

    def to_dict(self) -> dict[str, Any]:
        d = {
            "passed": self.passed and not self.used_fallback,
            "invented_numbers": list(self.invented_numbers),
            "invented_entities": list(self.invented_entities),
            "omitted_findings": list(self.omitted_findings),
            "contradicted_claims": list(self.contradicted_claims),
            "unaddressed_claims": list(self.unaddressed_claims),
            "independent_visual_claims": list(self.independent_visual_claims),
            "rejection_codes": list(self.rejection_codes),
            "used_fallback": self.used_fallback,
            "regenerated": self.regenerated,
            "violations": self.violations,
        }
        if self.contextual_grounding:
            d["contextual_grounding"] = dict(self.contextual_grounding)
        if self.chain_of_verification:
            d["chain_of_verification"] = dict(self.chain_of_verification)
        return d

    def summary(self) -> str:
        parts = []
        if self.invented_numbers:
            parts.append(f"invented_numbers={self.invented_numbers}")
        if self.invented_entities:
            parts.append(f"invented_entities={self.invented_entities}")
        if self.omitted_findings:
            parts.append(f"omitted_findings={self.omitted_findings}")
        if self.contradicted_claims:
            parts.append(f"contradicted_claims={self.contradicted_claims}")
        if self.independent_visual_claims:
            parts.append(f"independent_visual_claims={self.independent_visual_claims}")
        if self.rejection_codes:
            parts.append(f"rejection_codes={self.rejection_codes}")
        return "; ".join(parts) if parts else "passed"

    @classmethod
    def combine(cls, *results: "ValidationResult") -> "ValidationResult":
        invented_numbers: list[str] = []
        invented_entities: list[str] = []
        omitted: list[str] = []
        contradicted: list[str] = []
        unaddressed: list[str] = []
        visual: list[str] = []
        codes: list[str] = []
        for r in results:
            invented_numbers.extend(r.invented_numbers)
            invented_entities.extend(r.invented_entities)
            omitted.extend(r.omitted_findings)
            contradicted.extend(r.contradicted_claims)
            unaddressed.extend(r.unaddressed_claims)
            visual.extend(r.independent_visual_claims)
            codes.extend(r.rejection_codes)

        def _uniq(xs: list[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for x in xs:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
            return out

        invented_numbers = _uniq(invented_numbers)
        invented_entities = _uniq(invented_entities)
        omitted = _uniq(omitted)
        contradicted = _uniq(contradicted)
        unaddressed = _uniq(unaddressed)
        visual = _uniq(visual)
        codes = _uniq(codes)
        return cls(
            passed=not (invented_numbers or invented_entities or omitted or contradicted or visual or codes),
            invented_numbers=invented_numbers,
            invented_entities=invented_entities,
            omitted_findings=omitted,
            contradicted_claims=contradicted,
            unaddressed_claims=unaddressed,
            independent_visual_claims=visual,
            rejection_codes=codes,
            used_fallback=any(r.used_fallback for r in results),
            regenerated=any(r.regenerated for r in results),
        )


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+./\s-]", " ", (text or "").lower())).strip()


def _phrase_in(blob: str, phrase: str) -> bool:
    if not phrase:
        return False
    pat = r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])"
    return re.search(pat, blob) is not None


_SAFE_TESLA = frozenset({1.5, 3.0})
_UNTRUSTED_STATUSES = frozenset({"omitted", "unreliable"})

_NUM_UNIT_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>cc|cm3|cm³|ml|mm|%|days?|tesla|T\b)",
    re.IGNORECASE,
)
_FAZEKAS_NUM_RE = re.compile(r"fazekas(?:\s+grade)?\s*(?P<num>\d+(?:\.\d+)?)", re.IGNORECASE)
_COMPARE_NUM_RE = re.compile(
    r"(?:increased|decreased|delta|Δ|change(?:d)?)\s+(?:by\s+)?(?P<num>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _canonical_unit(unit: str) -> str:
    u = (unit or "").strip().lower().replace("³", "3")
    if u in {"cc", "cm3", "ml"}:
        return "cc"
    if u == "mm":
        return "mm"
    if u in {"%", "percent", "pct"}:
        return "%"
    if u == "fazekas":
        return "fazekas"
    if u in {"day", "days"}:
        return "days"
    if u in {"t", "tesla"}:
        return "T"
    return u


def _unit_from_id(mid: str) -> str:
    key = (mid or "").lower()
    if key.endswith("_cc") or "volume_cc" in key or key.endswith(".cc"):
        return "cc"
    if "pct" in key or "percent" in key:
        return "%"
    if "fazekas" in key:
        return "fazekas"
    if "days" in key:
        return "days"
    return ""


def _float_or_none(raw: Any) -> Optional[float]:
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _add_measure(bucket: list[dict[str, Any]], value: Any, unit: str, *, trusted: bool, label: str = "") -> None:
    fv = _float_or_none(value)
    if fv is None:
        return
    cu = _canonical_unit(unit)
    bucket.append({"value": fv, "unit": cu, "trusted": trusted, "label": label or cu})


def _collect_payload_measures(payload: dict) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return out

    for fnd in payload.get("findings") or []:
        if not isinstance(fnd, dict):
            continue
        status = str(fnd.get("status") or "ok").lower()
        unit = str(fnd.get("unit") or _unit_from_id(str(fnd.get("code") or fnd.get("id") or "")))
        _add_measure(out, fnd.get("value"), unit, trusted=status not in _UNTRUSTED_STATUSES, label=str(fnd.get("code") or fnd.get("id") or ""))

    for m in payload.get("measurements") or []:
        if not isinstance(m, dict):
            continue
        status = str(m.get("status") or "ok").lower()
        unit = str(m.get("unit") or _unit_from_id(str(m.get("id") or "")))
        _add_measure(out, m.get("value"), unit, trusted=status not in _UNTRUSTED_STATUSES, label=str(m.get("id") or m.get("label") or ""))

    wmh = payload.get("wmh") if isinstance(payload.get("wmh"), dict) else {}
    qc = payload.get("qc") if isinstance(payload.get("qc"), dict) else {}
    engines = qc.get("engines") if isinstance(qc.get("engines"), dict) else {}
    wmh_eng = engines.get("wmh_3d") if isinstance(engines.get("wmh_3d"), dict) else {}
    wmh_status = str(wmh.get("status") or "ok").lower()
    wmh_trusted = wmh_status not in _UNTRUSTED_STATUSES
    if engines:
        if wmh_eng.get("run") is False or wmh_eng.get("trusted") is False:
            wmh_trusted = False
        if str(qc.get("overall") or "") == "fail" and not wmh_eng.get("run"):
            wmh_trusted = False
    for key, lab in (
        ("volume_cc", "wmh_total_cc"),
        ("volume_cc_periventricular", "wmh_pv_cc"),
        ("volume_cc_deep_subcortical", "wmh_deep_cc"),
        ("volume_cc_infratentorial", "wmh_infra_cc"),
    ):
        if wmh.get(key) is not None:
            _add_measure(out, wmh.get(key), "cc", trusted=wmh_trusted, label=lab)

    et = payload.get("ET_VOL")
    if et is None and isinstance(payload.get("tumor"), dict):
        et = payload["tumor"].get("et_cc") or payload["tumor"].get("ET_VOL")
    et_trusted = True
    if engines and (wmh_eng.get("run") is False or str(qc.get("overall") or "") == "fail"):
        et_trusted = False
    _add_measure(out, et, "cc", trusted=et_trusted, label="ET_VOL")

    conf = _payload_confidence(payload)
    if conf:
        _add_measure(out, conf * 100.0, "%", trusted=True, label="confidence")

    comps: list[Any] = []
    if isinstance(payload.get("comparisons"), list):
        comps.extend(payload["comparisons"])
    elif isinstance(payload.get("comparisons"), dict):
        comps.append(payload["comparisons"])
    if isinstance(payload.get("longitudinal"), dict):
        comps.append(payload["longitudinal"])
    for row in comps:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "")
        _add_measure(out, row.get("current_volume_cc") or row.get("current_cc"), "cc", trusted=True, label="current_cc")
        _add_measure(out, row.get("prior_volume_cc") or row.get("prior_cc"), "cc", trusted=True, label="prior_cc")
        if status == "comparable":
            _add_measure(out, row.get("volume_delta_cc") or row.get("delta_cc"), "cc", trusted=True, label="delta_cc")
            _add_measure(out, row.get("volume_pct_change") or row.get("pct_change"), "%", trusted=True, label="pct_change")

    days = payload.get("days_between")
    if days is None:
        for row in comps:
            if isinstance(row, dict) and row.get("days_between") is not None:
                days = row.get("days_between")
                break
    _add_measure(out, days, "days", trusted=True, label="days_between")

    tesla = None
    qc = payload.get("qc") if isinstance(payload.get("qc"), dict) else {}
    tesla = qc.get("tesla") or qc.get("field_strength") or payload.get("scanner_field_strength")
    if isinstance(tesla, str) and tesla.lower().endswith("t"):
        tesla = tesla[:-1]
    tv = _float_or_none(tesla)
    if tv is not None:
        _add_measure(out, tv, "T", trusted=True, label="tesla")
    return out


def _iter_measurement_mentions(text: str) -> list[tuple[float, str, str]]:
    """Return (value, canonical_unit, raw) for unit-bearing or comparison numbers only."""
    hits: list[tuple[float, str, str]] = []
    for m in _NUM_UNIT_RE.finditer(text or ""):
        fv = _float_or_none(m.group("num"))
        if fv is None:
            continue
        hits.append((fv, _canonical_unit(m.group("unit")), m.group(0).strip()))
    for m in _FAZEKAS_NUM_RE.finditer(text or ""):
        fv = _float_or_none(m.group("num"))
        if fv is None:
            continue
        hits.append((fv, "fazekas", m.group(0).strip()))
    for m in _COMPARE_NUM_RE.finditer(text or ""):
        fv = _float_or_none(m.group("num"))
        if fv is None:
            continue
        if not any(abs(h[0] - fv) < 1e-6 for h in hits):
            hits.append((fv, "", m.group(0).strip()))
    return hits


def _value_matches(fv: float, allowed: float) -> bool:
    return abs(fv - allowed) < 1e-6


def validate_no_invented_numbers(generated_text: str, grounding_payload: dict) -> ValidationResult:
    """Flag a number only when it appears with a measurement unit/noun or comparison phrase."""
    text = generated_text or ""
    if not text.strip():
        return ValidationResult(passed=True)
    measures = _collect_payload_measures(grounding_payload or {})
    invented: list[str] = []
    codes: list[str] = []
    for fv, unit, raw in _iter_measurement_mentions(text):
        if unit == "T" and fv in _SAFE_TESLA:
            continue
        trusted_same = [m for m in measures if m["trusted"] and _value_matches(fv, m["value"])]
        untrusted_same = [m for m in measures if (not m["trusted"]) and _value_matches(fv, m["value"])]
        if unit == "T" and any(m["unit"] == "T" and _value_matches(fv, m["value"]) for m in measures):
            continue
        if not trusted_same and untrusted_same:
            invented.append(raw)
            codes.append("REJECT_OMITTED_NUMBER_USED")
            continue
        if not trusted_same:
            invented.append(raw)
            codes.append("REJECT_INVENTED_NUMBER")
            continue
        if unit and not any(m["unit"] == unit for m in trusted_same):
            invented.append(raw)
            codes.append("REJECT_UNIT_MISMATCH")
            continue
    seen: set[str] = set()
    uniq: list[str] = []
    ucodes: list[str] = []
    for n, c in zip(invented, codes):
        if n not in seen:
            seen.add(n)
            uniq.append(n)
            ucodes.append(c)
    return ValidationResult(passed=not uniq, invented_numbers=uniq, rejection_codes=ucodes)


def fail_closed_template(payload: dict) -> str:
    """Measurement table from trusted payload values only. Never splice rejected prose."""
    lines = ["FAIL_CLOSED", "Measurement table (source payload only):"]
    seen: set[tuple[str, float, str]] = set()
    for m in _collect_payload_measures(payload or {}):
        if not m["trusted"]:
            continue
        key = (m["label"], m["value"], m["unit"])
        if key in seen:
            continue
        seen.add(key)
        unit = f" {m['unit']}" if m["unit"] else ""
        lines.append(f"- {m['label']}: {m['value']}{unit}".rstrip())
    label = _payload_label(payload or {})
    if label:
        lines.append(f"- prediction: {label}")
    return "\n".join(lines)


def _payload_label(payload: dict) -> str:
    raw = payload.get("label") or payload.get("prediction") or payload.get("predicted_label")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower().replace(" ", "")
    for m in payload.get("measurements") or []:
        if isinstance(m, dict) and m.get("id") == "predicted_label":
            return str(m.get("value") or "").strip().lower().replace(" ", "")
    return ""


def _payload_confidence(payload: dict) -> float:
    for key in ("confidence", "model_confidence"):
        try:
            v = float(payload.get(key))
            return v / 100.0 if v > 1.0 else v
        except (TypeError, ValueError):
            continue
    for m in payload.get("measurements") or []:
        if isinstance(m, dict) and m.get("id") in ("model_confidence_raw", "dominant_class_probability"):
            try:
                v = float(m.get("value"))
                return v / 100.0 if v > 1.0 else v
            except (TypeError, ValueError):
                continue
    return 0.0


def _payload_severity_rank(payload: dict) -> int:
    candidates: list[str] = []
    for key in ("severity", "severity_grade"):
        v = payload.get(key)
        if isinstance(v, str):
            candidates.append(v.lower())
    wmh = payload.get("wmh")
    if isinstance(wmh, dict):
        for key in ("severity_grade", "severity"):
            v = wmh.get(key)
            if isinstance(v, str):
                candidates.append(v.lower())
    for m in payload.get("measurements") or []:
        if isinstance(m, dict) and isinstance(m.get("severity"), str):
            candidates.append(str(m["severity"]).lower())
    rank = 0
    for c in candidates:
        rank = max(rank, _SEVERITY_RANK.get(c, 0))
    return rank


def _expand_allowed_entities(payload: dict) -> set[str]:
    allowed: set[str] = set(_SURVEY_ANATOMY)

    def _add(term: str) -> None:
        t = _norm(term)
        if not t:
            return
        allowed.add(t)
        for canon, aliases in _ENTITY_ALIASES.items():
            if t == canon or t in aliases:
                allowed.update(aliases)
                allowed.add(canon)

    label = _payload_label(payload)
    if label:
        _add(label)
        if label == "notumor":
            _add("no tumor")

    probs = payload.get("probabilities") or payload.get("class_probabilities") or {}
    if isinstance(probs, dict):
        for k in probs:
            _add(str(k))

    for r in payload.get("regions") or []:
        _add(str(r))

    for m in payload.get("measurements") or []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "")
        for ent in _MEASUREMENT_ID_ENTITIES.get(mid, ()):
            _add(ent)
        if mid == "predicted_label":
            _add(str(m.get("value") or ""))
        lab = m.get("label")
        if isinstance(lab, str):
            _add(lab)
            for part in re.split(r"[·,/]", lab):
                _add(part)

    wmh = payload.get("wmh")
    if isinstance(wmh, dict):
        _add("wmh")
        _add("white matter")
        if wmh.get("volume_cc_periventricular") is not None:
            _add("periventricular")
        if wmh.get("volume_cc_deep_subcortical") is not None:
            _add("deep subcortical")
        if wmh.get("volume_cc_infratentorial") is not None:
            _add("infratentorial")
        for key in ("severity_grade", "severity", "risk_level"):
            if isinstance(wmh.get(key), str):
                _add(str(wmh[key]))

    for key in ("severity", "severity_grade"):
        if isinstance(payload.get(key), str):
            _add(str(payload[key]))

    rank = _payload_severity_rank(payload)
    for term, rnk in _SEVERITY_RANK.items():
        if rnk <= rank:
            _add(term)
    if rank == 0:
        _add("mild")
        _add("normal")

    return allowed


def _extract_gated_mentions(text: str) -> list[str]:
    blob = " " + _norm(text) + " "
    hits: list[str] = []
    occupied = [False] * len(blob)
    for phrase in _ALL_GATED_PHRASES:
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])")
        for m in pat.finditer(blob):
            if any(occupied[m.start() : m.end()]):
                continue
            hits.append(phrase)
            for i in range(m.start(), m.end()):
                    occupied[i] = True
    return hits


def _mention_allowed(mention: str, allowed: set[str]) -> bool:
    n = _norm(mention)
    if n in _SURVEY_ANATOMY:
        return True
    if n in allowed:
        return True
    for canon, aliases in _ENTITY_ALIASES.items():
        if n == canon or n in aliases:
            return canon in allowed or bool(aliases & allowed)
    return False


def validate_faithfulness(generated_text: str, grounding_payload: dict) -> ValidationResult:
    """Every gated clinical entity in the prose must trace to the payload."""
    text = generated_text or ""
    if not text.strip():
        return ValidationResult(passed=True)
    allowed = _expand_allowed_entities(grounding_payload or {})
    invented: list[str] = []
    payload_rank = _payload_severity_rank(grounding_payload or {})
    for mention in _extract_gated_mentions(text):
        rnk = _SEVERITY_RANK.get(mention, None)
        if rnk is not None and rnk > max(payload_rank, 1):
            invented.append(mention)
            continue
        if rnk is not None and rnk <= max(payload_rank, 1):
            continue
        if not _mention_allowed(mention, allowed):
            invented.append(mention)
    seen: set[str] = set()
    uniq: list[str] = []
    for e in invented:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    return ValidationResult(passed=not uniq, invented_entities=uniq)


def _material_findings(
    payload: dict,
    thresholds: dict[str, float],
) -> list[tuple[str, tuple[str, ...]]]:
    """Return (finding_id, mention_aliases) that must appear in prose."""
    th = {**DEFAULT_MATERIALITY, **(thresholds or {})}
    findings: list[tuple[str, tuple[str, ...]]] = []

    label = _payload_label(payload)
    conf = _payload_confidence(payload)
    if label and label not in {x.replace(" ", "") for x in _NEGATIVE_LABELS} and conf >= th["tumor_confidence"]:
        aliases = tuple(_ENTITY_ALIASES.get(label, {label}))
        findings.append((f"{label} (confidence {conf:.2f})", aliases))

    wmh = payload.get("wmh") if isinstance(payload.get("wmh"), dict) else None
    vol = None
    if wmh is not None:
        try:
            vol = float(wmh.get("volume_cc"))
        except (TypeError, ValueError):
            vol = None
    if vol is None:
        for m in payload.get("measurements") or []:
            if isinstance(m, dict) and m.get("id") == "wmh_volume_cc":
                try:
                    vol = float(m.get("value"))
                except (TypeError, ValueError):
                    vol = None
    if vol is not None and vol >= th["wmh_volume_cc"]:
        findings.append(
            (
                f"wmh_volume_cc={vol}",
                tuple(_ENTITY_ALIASES["wmh"]) + ("white matter",),
            )
        )

    et = _float_or_none(payload.get("ET_VOL"))
    if et is None and isinstance(payload.get("tumor"), dict):
        et = _float_or_none(payload["tumor"].get("et_cc") or payload["tumor"].get("ET_VOL"))
    if et is None:
        for fnd in payload.get("findings") or []:
            if not isinstance(fnd, dict):
                continue
            code = str(fnd.get("code") or fnd.get("id") or "").lower()
            if ("et" in code and "vol" in code) or code.endswith(".et_cc") or code == "et_vol":
                et = _float_or_none(fnd.get("value"))
                if et is not None:
                    break
    if et is not None and et > 0:
        findings.append(
            (
                f"ET_VOL={et}",
                ("enhancing tumor", "enhancing", "contrast-enhancing"),
            )
        )

    regional = (
        ("volume_cc_periventricular", "periventricular", th["regional_volume_cc"]),
        ("volume_cc_deep_subcortical", "deep subcortical", th["regional_volume_cc"]),
        ("volume_cc_infratentorial", "infratentorial", th["regional_volume_cc"]),
    )
    meas_map = {
        "wmh_volume_periventricular_cc": "periventricular",
        "wmh_volume_deep_subcortical_cc": "deep subcortical",
        "wmh_volume_infratentorial_cc": "infratentorial",
    }
    if wmh:
        for key, alias, floor in regional:
            try:
                rv = float(wmh.get(key))
            except (TypeError, ValueError):
                continue
            if rv >= floor:
                findings.append((f"{key}={rv}", (alias, "wmh")))
    else:
        for m in payload.get("measurements") or []:
            if not isinstance(m, dict):
                continue
            alias = meas_map.get(str(m.get("id") or ""))
            if not alias:
                continue
            try:
                rv = float(m.get("value"))
            except (TypeError, ValueError):
                continue
            if rv >= th["regional_volume_cc"]:
                findings.append((f"{m['id']}={rv}", (alias, "wmh")))

    return findings


def validate_recall(
    generated_text: str,
    grounding_payload: dict,
    materiality_thresholds: Optional[dict] = None,
) -> ValidationResult:
    """Material payload findings must be mentioned (no silent omission)."""
    text = generated_text or ""
    blob = " " + _norm(text) + " "
    omitted: list[str] = []
    for finding_id, aliases in _material_findings(grounding_payload or {}, materiality_thresholds or {}):
        if any(_phrase_in(blob, a) for a in aliases):
            continue
        omitted.append(finding_id)
    return ValidationResult(passed=not omitted, omitted_findings=omitted)


_VISUAL_INTERPRETATION_RE = re.compile(
    r"("
    r"\bi can see\b|"
    r"\bi see\b|"
    r"\bthe image shows\b|"
    r"\bthe scan shows\b|"
    r"\bon the image\b|"
    r"\bthe mri shows\b|"
    r"\bvisually appears(?:\s+to)?\b|"
    r"\bupon inspection of the (?:scan|image|mri)\b|"
    r"\bon visual inspection\b|"
    r"\blooking at (?:the )?(?:scan|image|mri)\b|"
    r"\bfrom the (?:image|scan) (?:i|we) (?:can )?(?:see|observe)\b|"
    r"\bappears on the (?:image|scan|mri)\b"
    r")",
    re.IGNORECASE,
)

_SALIENCY_NARRATION_RE = re.compile(
    r"("
    r"saliency|"
    r"grad-?cam|"
    r"heatmap|"
    r"highlighted region|"
    r"model (?:measured|predicted|output|highlighted|classified)|"
    r"\bclassifier\b|"
    r"structured (?:data|payload|measurements)|"
    r"per the (?:model|saliency)"
    r")",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def validate_no_independent_image_interpretation(
    generated_text: str,
    grounding_payload: dict,
) -> ValidationResult:
    """
    Flags language patterns suggesting the model is describing what
    it visually perceived rather than narrating provided data — e.g.
    phrases like "I can see", "the image shows", "visually appears
    to", "upon inspection of the scan" that aren't tied to a
    specific value in grounding_payload.

    This is a heuristic/pattern check, not perfect — flagged cases
    also go to the audit trail. Benign narration of the saliency
    overlay or explicit model measurements is not flagged.
    """
    text = (generated_text or "").strip()
    if not text:
        return ValidationResult(passed=True)
    flagged: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        sent = sentence.strip()
        if not sent:
            continue
        match = _VISUAL_INTERPRETATION_RE.search(sent)
        if not match:
            continue
        if _SALIENCY_NARRATION_RE.search(sent):
            continue
        flagged.append(sent[:240])
    if flagged:
        log_report_draft_event(
            event_type="llm_independent_visual_interpretation",
            user_id="system",
            payload={
                "flagged": flagged,
                "text": text[:500],
                "payload_keys": sorted(str(k) for k in (grounding_payload or {})),
            },
        )
    return ValidationResult(
        passed=not flagged,
        independent_visual_claims=flagged,
        rejection_codes=["REJECT_INDEPENDENT_VISUAL"] if flagged else [],
    )


_CHANGE_LANGUAGE_RE = re.compile(
    r"\b(increased|decreased|stable|slight[ -]increase|slight[ -]decrease|"
    r"interval change|unchanged)\b",
    re.IGNORECASE,
)


def validate_comparison_language(generated_text: str, grounding_payload: dict) -> ValidationResult:
    """Change adjectives are allowed only when a comparable direction is in the payload."""
    text = generated_text or ""
    if not text.strip() or not _CHANGE_LANGUAGE_RE.search(text):
        return ValidationResult(passed=True)
    lon = None
    if isinstance(grounding_payload, dict):
        lon = grounding_payload.get("longitudinal")
        if lon is None:
            comps = grounding_payload.get("comparisons")
            if isinstance(comps, list) and comps:
                lon = comps[0]
            elif isinstance(comps, dict):
                lon = comps
    direction = ""
    status = ""
    if isinstance(lon, dict):
        status = str(lon.get("status") or "")
        direction = str(lon.get("direction") or "").lower()
    has_delta = False
    if isinstance(lon, dict):
        has_delta = lon.get("volume_delta_cc") is not None or lon.get("delta_cc") is not None
    if status != "comparable" or not (direction or has_delta):
        return ValidationResult(
            passed=False,
            contradicted_claims=["REJECT_COMPARISON_LANGUAGE"],
            rejection_codes=["REJECT_COMPARISON_LANGUAGE"],
        )
    return ValidationResult(passed=True)


_ATTEST_FORGE_RE = re.compile(
    r"("
    r"\bi (?:have )?reviewed these statements\b|"
    r"\bi hereby (?:attest|sign)\b|"
    r"\belectronically signed\b|"
    r"\battested by\b|"
    r"\bi attest that\b"
    r")",
    re.IGNORECASE,
)


def validate_attestation_forged(generated_text: str) -> ValidationResult:
    text = generated_text or ""
    if not text.strip() or not _ATTEST_FORGE_RE.search(text):
        return ValidationResult(passed=True)
    return ValidationResult(
        passed=False,
        contradicted_claims=["REJECT_ATTESTATION_FORGED"],
        rejection_codes=["REJECT_ATTESTATION_FORGED"],
    )


def validate_payload_pixels(grounding_payload: dict) -> ValidationResult:
    from src.llm.pixel_leak import REJECT_PIXEL_LEAK, find_pixel_leaks

    leaks = find_pixel_leaks(grounding_payload or {})
    if leaks:
        return ValidationResult(
            passed=False,
            independent_visual_claims=[f"{REJECT_PIXEL_LEAK}:{p}" for p in leaks[:8]],
            rejection_codes=["REJECT_PIXEL_LEAK"],
        )
    return ValidationResult(passed=True)


def validate_draft(draft: str, grounding_payload: dict, materiality_thresholds: Optional[dict] = None) -> ValidationResult:
    """Every numeric token must match a payload value; fail closed on leak or comparison abuse."""
    return validate_clinical_output(draft, grounding_payload, materiality_thresholds)


def validate_clinical_output(
    generated_text: str,
    grounding_payload: dict,
    materiality_thresholds: Optional[dict] = None,
) -> ValidationResult:
    """Authoritative gate: numbers + faithfulness + recall + CDS image-narration."""
    pixels = validate_payload_pixels(grounding_payload)
    if not pixels.passed:
        return pixels
    numbers = validate_no_invented_numbers(generated_text, grounding_payload)
    faithfulness = validate_faithfulness(generated_text, grounding_payload)
    recall = validate_recall(generated_text, grounding_payload, materiality_thresholds)
    visual = validate_no_independent_image_interpretation(generated_text, grounding_payload)
    comparison = validate_comparison_language(generated_text, grounding_payload)
    attest = validate_attestation_forged(generated_text)
    return ValidationResult.combine(numbers, faithfulness, recall, visual, comparison, attest)


def log_grounding_assessment(
    meta: Optional[dict],
    gate: ValidationResult,
    *,
    user_id: str = "system",
) -> None:
    """
    Audit the Bedrock contextual-grounding scores next to the deterministic gate.

    Below-threshold scores request human review; they do not fail the gate.
    """
    if not meta:
        return
    if meta.get("grounding_score") is None and meta.get("relevance_score") is None:
        return
    below = bool(meta.get("below_threshold") or meta.get("human_review"))
    log_report_draft_event(
        event_type="llm_contextual_grounding_review" if below else "llm_contextual_grounding",
        user_id=user_id,
        payload={
            "grounding_score": meta.get("grounding_score"),
            "relevance_score": meta.get("relevance_score"),
            "grounding_threshold": meta.get("grounding_threshold"),
            "relevance_threshold": meta.get("relevance_threshold"),
            "below_threshold": below,
            "human_review_required": below,
            "deterministic_passed": gate.passed,
            "deterministic_violations": gate.violations,
            "used_fallback": gate.used_fallback,
        },
    )


def _log_gate_failure(
    result: ValidationResult,
    text: str,
    *,
    used_fallback: bool,
    regenerated: bool,
    user_id: str = "system",
) -> None:
    log_report_draft_event(
        event_type="llm_clinical_gate_failed",
        user_id=user_id,
        payload={
            "violations": result.violations,
            "invented_numbers": result.invented_numbers,
            "invented_entities": result.invented_entities,
            "omitted_findings": result.omitted_findings,
            "contradicted_claims": result.contradicted_claims,
            "independent_visual_claims": result.independent_visual_claims,
            "used_fallback": used_fallback,
            "regenerated": regenerated,
            "text": (text or "")[:500],
        },
    )


def _merge_cov(det: ValidationResult, cov: Optional[Any]) -> ValidationResult:
    if cov is None:
        return det
    return replace(
        det,
        passed=det.passed and bool(getattr(cov, "passed", True)),
        contradicted_claims=list(getattr(cov, "contradicted", None) or []),
        unaddressed_claims=list(getattr(cov, "not_addressed", None) or []),
        chain_of_verification=cov.to_dict() if hasattr(cov, "to_dict") else None,
    )


def _evaluate_clinical_text(
    generated_text: str,
    grounding_payload: dict,
    materiality_thresholds: Optional[dict],
    *,
    user_id: str = "system",
) -> ValidationResult:
    """Prompt 1 deterministic gate, then optional chain-of-verification (Prompt 4)."""
    first = validate_clinical_output(generated_text, grounding_payload, materiality_thresholds)
    if not first.passed:
        return first
    from src.llm.chain_of_verification import apply_chain_of_verification

    cov = apply_chain_of_verification(generated_text, grounding_payload, user_id=user_id)
    return _merge_cov(first, cov)


def enforce_clinical_gate(
    generated_text: str,
    grounding_payload: dict,
    *,
    fallback_text: str,
    retry_fn: Optional[Callable[[str], str]] = None,
    materiality_thresholds: Optional[dict] = None,
    user_id: str = "system",
) -> tuple[str, ValidationResult]:
    """
    Run the gate. On failure, regenerate once with a corrective note, then
    fall back to template-only prose. Never returns unvalidated LLM text.

    When ENABLE_CHAIN_OF_VERIFICATION is on, a CONTRADICTED claim is treated
    as the same Tier 0 failure as a Prompt 1 validator miss.
    """
    first = _evaluate_clinical_text(
        generated_text, grounding_payload, materiality_thresholds, user_id=user_id
    )
    if first.passed:
        return generated_text, first

    _log_gate_failure(first, generated_text, used_fallback=False, regenerated=False, user_id=user_id)

    if retry_fn is not None:
        extra = ""
        if first.contradicted_claims:
            extra = (
                " A chain-of-verification step found claims contradicted by the "
                f"measurements: {first.contradicted_claims}. Correct those characterizations."
            )
        corrective = (
            "Your previous draft was rejected by a deterministic clinical safety gate. "
            f"Violations: {first.summary()}. "
            "Rewrite using ONLY findings, regions, severity terms, and numbers that appear "
            "in the provided measurements. Do not add anatomy or diagnoses that were not listed. "
            "Mention every material finding from the measurements. "
            "Do not claim to see, inspect, or visually interpret the scan or image; "
            "narrate the structured model output only."
            + extra
        )
        try:
            second_text = retry_fn(corrective) or ""
        except Exception:
            second_text = ""
        second = _evaluate_clinical_text(
            second_text, grounding_payload, materiality_thresholds, user_id=user_id
        )
        if second.passed:
            return second_text, replace(second, regenerated=True)
        _log_gate_failure(second, second_text, used_fallback=True, regenerated=True, user_id=user_id)
        closed = fail_closed_template(grounding_payload) or fallback_text
        return closed, replace(
            second,
            used_fallback=True,
            regenerated=True,
            passed=False,
            rejection_codes=list(second.rejection_codes) + ["FAIL_CLOSED"],
        )

    closed = fail_closed_template(grounding_payload) or fallback_text
    return closed, replace(
        first,
        used_fallback=True,
        passed=False,
        rejection_codes=list(first.rejection_codes) + ["FAIL_CLOSED"],
    )


def grounding_from_prediction(
    label: str,
    confidence: float,
    probabilities: Optional[dict] = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "prediction": label,
        "confidence": confidence,
        "probabilities": probabilities or {},
    }


def grounding_from_measurements(
    measurements: Iterable[dict],
    *,
    model_run: Optional[dict] = None,
    regions: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"measurements": list(measurements)}
    if regions:
        payload["regions"] = [str(r) for r in regions]
    if model_run:
        from src.ingest.path import is_2d_triage_run

        if not is_2d_triage_run(model_run):
            payload["label"] = model_run.get("label") or model_run.get("prediction")
            payload["confidence"] = model_run.get("confidence")
            payload["probabilities"] = model_run.get("probabilities") or model_run.get("class_probabilities")
        if isinstance(model_run.get("wmh"), dict):
            payload["wmh"] = model_run["wmh"]
    return payload
