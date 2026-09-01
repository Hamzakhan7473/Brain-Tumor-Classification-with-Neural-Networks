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
        return "; ".join(parts) if parts else "passed"

    @classmethod
    def combine(cls, *results: "ValidationResult") -> "ValidationResult":
        invented_numbers: list[str] = []
        invented_entities: list[str] = []
        omitted: list[str] = []
        contradicted: list[str] = []
        unaddressed: list[str] = []
        visual: list[str] = []
        for r in results:
            invented_numbers.extend(r.invented_numbers)
            invented_entities.extend(r.invented_entities)
            omitted.extend(r.omitted_findings)
            contradicted.extend(r.contradicted_claims)
            unaddressed.extend(r.unaddressed_claims)
            visual.extend(r.independent_visual_claims)

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
        return cls(
            passed=not (invented_numbers or invented_entities or omitted or contradicted or visual),
            invented_numbers=invented_numbers,
            invented_entities=invented_entities,
            omitted_findings=omitted,
            contradicted_claims=contradicted,
            unaddressed_claims=unaddressed,
            independent_visual_claims=visual,
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


def _walk_numbers(obj: Any, into: set[str]) -> None:
    if obj is None or isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        fv = float(obj)
        into.add(str(obj))
        into.add(str(fv))
        if fv == int(fv):
            into.add(str(int(fv)))
        into.add(f"{fv:.1f}".rstrip("0").rstrip("."))
        into.add(f"{fv:.2f}".rstrip("0").rstrip("."))
        into.add(f"{fv:.4f}".rstrip("0").rstrip("."))
        if 0.0 <= fv <= 1.0:
            pct = fv * 100.0
            into.add(f"{pct:.1f}".rstrip("0").rstrip("."))
            into.add(str(int(round(pct))))
        return
    if isinstance(obj, str):
        for n in re.findall(r"\b\d+\.?\d*\b", obj):
            into.add(n)
            try:
                _walk_numbers(float(n), into)
            except ValueError:
                pass
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _walk_numbers(v, into)
        return
    if isinstance(obj, (list, tuple, set)):
        for v in obj:
            _walk_numbers(v, into)


def _allowed_numbers(payload: dict) -> set[str]:
    allowed: set[str] = set()
    _walk_numbers(payload, allowed)
    return {a for a in allowed if a not in {"", ".", "-"}}


def validate_no_invented_numbers(generated_text: str, grounding_payload: dict) -> ValidationResult:
    """Existing number gate, payload-shaped so other checks can share it."""
    text = generated_text or ""
    if not text.strip():
        return ValidationResult(passed=True)
    allowed = _allowed_numbers(grounding_payload or {})
    invented: list[str] = []
    for n in re.findall(r"\b\d+\.?\d*\b", text):
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
            invented.append(n)
    seen: set[str] = set()
    uniq: list[str] = []
    for n in invented:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return ValidationResult(passed=not uniq, invented_numbers=uniq)


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
    return ValidationResult(passed=not flagged, independent_visual_claims=flagged)


def validate_clinical_output(
    generated_text: str,
    grounding_payload: dict,
    materiality_thresholds: Optional[dict] = None,
) -> ValidationResult:
    """Authoritative gate: numbers + faithfulness + recall + CDS image-narration."""
    numbers = validate_no_invented_numbers(generated_text, grounding_payload)
    faithfulness = validate_faithfulness(generated_text, grounding_payload)
    recall = validate_recall(generated_text, grounding_payload, materiality_thresholds)
    visual = validate_no_independent_image_interpretation(generated_text, grounding_payload)
    return ValidationResult.combine(numbers, faithfulness, recall, visual)


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
        return fallback_text, replace(second, used_fallback=True, regenerated=True, passed=False)

    return fallback_text, replace(first, used_fallback=True, passed=False)


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
        payload["label"] = model_run.get("label") or model_run.get("prediction")
        payload["confidence"] = model_run.get("confidence")
        payload["probabilities"] = model_run.get("probabilities") or model_run.get("class_probabilities")
        if isinstance(model_run.get("wmh"), dict):
            payload["wmh"] = model_run["wmh"]
    return payload
