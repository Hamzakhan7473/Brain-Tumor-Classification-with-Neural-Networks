"""
Text-only LLM narrative schemas + deterministic slot interpolation.

Numeric values never originate from the model: they are substituted from
the grounding payload at render time. Placeholders:

  {wmh_volume_cc}
  {{wmh_volume_cc}}
  {{measure:wmh_volume_cc}}
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, ValidationError

from src.inference.audit_log import log_report_draft_event

_PLACEHOLDER_DOUBLE = re.compile(r"\{\{measure:([a-zA-Z_][a-zA-Z0-9_]*)\}\}")
_PLACEHOLDER_BRACES = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}")
_PLACEHOLDER_SINGLE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_CITE = re.compile(r"\[cite:[^\]]+\]")
_NUMBER = re.compile(r"\b\d+\.?\d*\b")
_NUMERIC_JSON_TYPES = frozenset({"number", "integer"})


class StructuredNarrativeError(ValueError):
    """The model violated the text-only schema (numeric field or embedded literal)."""


class ReportNarrative(BaseModel):
    """LLM-visible report fields — strings only. No measurement numbers."""

    model_config = ConfigDict(extra="forbid")
    findings_narrative: str
    impression_narrative: str


class RegionNarrative(BaseModel):
    """One findings-region paragraph. Numbers only via placeholders."""

    model_config = ConfigDict(extra="forbid")
    text: str


def assert_schema_text_only(schema: type[BaseModel]) -> None:
    """Raise if the Pydantic schema declares any numeric JSON type."""
    leaked = _numeric_schema_paths(schema.model_json_schema())
    if leaked:
        raise StructuredNarrativeError(
            f"Narrative schema must be text-only; numeric fields are not allowed: {leaked}"
        )


def _numeric_schema_paths(node: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if not isinstance(node, dict):
        return found
    json_type = node.get("type")
    types = json_type if isinstance(json_type, list) else [json_type] if json_type else []
    if any(t in _NUMERIC_JSON_TYPES for t in types):
        found.append(path or "<root>")
    props = node.get("properties")
    if isinstance(props, dict):
        for key, child in props.items():
            found.extend(_numeric_schema_paths(child, f"{path}.{key}" if path else key))
    for key in ("items", "additionalProperties"):
        if key in node:
            found.extend(_numeric_schema_paths(node[key], f"{path}[]" if key == "items" else path))
    defs = node.get("$defs") or node.get("definitions")
    if isinstance(defs, dict):
        for key, child in defs.items():
            found.extend(_numeric_schema_paths(child, f"$defs.{key}"))
    return found


def extra_numeric_fields(payload: dict, schema: type[BaseModel]) -> list[str]:
    """Keys in the model output that look like numbers and are not in the schema."""
    allowed = set(schema.model_fields.keys())
    leaked: list[str] = []
    numeric_str = re.compile(r"[+-]?\d+(?:\.\d+)?")
    for key, value in (payload or {}).items():
        if key in allowed:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            leaked.append(key)
        elif isinstance(value, str) and numeric_str.fullmatch(value.strip() or ""):
            leaked.append(key)
    return leaked


def strip_slots(text: str) -> str:
    """Remove allowed placeholders so leftover digits are true literals."""
    t = _PLACEHOLDER_DOUBLE.sub("", text or "")
    t = _PLACEHOLDER_BRACES.sub("", t)
    t = _PLACEHOLDER_SINGLE.sub("", t)
    t = _CITE.sub("", t)
    return t


def leaked_numeric_literals(text: str) -> list[str]:
    return _NUMBER.findall(strip_slots(text or ""))


def interpolate_narrative(text: str, measurements: Iterable[dict]) -> str:
    """Replace slot placeholders with deterministic measurement values."""
    md = {str(m["id"]): m.get("value") for m in measurements if isinstance(m, dict) and m.get("id")}

    def _repl_measure(match: re.Match) -> str:
        key = match.group(1)
        return str(md[key]) if key in md else match.group(0)

    def _repl_id(match: re.Match) -> str:
        key = match.group(1)
        return str(md[key]) if key in md else match.group(0)

    out = _PLACEHOLDER_DOUBLE.sub(_repl_measure, text or "")
    out = _PLACEHOLDER_BRACES.sub(_repl_id, out)
    out = _PLACEHOLDER_SINGLE.sub(_repl_id, out)
    return out


def assemble_report_narratives(
    narrative: ReportNarrative,
    measurements: Iterable[dict],
) -> dict[str, str]:
    """
    Merge LLM prose with deterministic slots.

    Raises StructuredNarrativeError if the LLM text still contains numeric
    literals (structural constraint failed — distinct from the Prompt 1 gate).
    """
    meas = list(measurements)
    leaked: dict[str, list[str]] = {}
    for field_name in ("findings_narrative", "impression_narrative"):
        nums = leaked_numeric_literals(getattr(narrative, field_name))
        if nums:
            leaked[field_name] = nums
    if leaked:
        log_structured_number_leak(leaked, str(narrative.findings_narrative)[:400])
        raise StructuredNarrativeError(f"LLM narrative contained numeric literals: {leaked}")

    findings = interpolate_narrative(narrative.findings_narrative, meas)
    impression = interpolate_narrative(narrative.impression_narrative, meas)
    doubled = double_substituted_numbers(
        narrative.findings_narrative + "\n" + narrative.impression_narrative,
        findings + "\n" + impression,
        meas,
    )
    if doubled:
        log_structured_number_leak({"double_substituted": doubled}, findings[:400])
        raise StructuredNarrativeError(
            f"Final report contains LLM-emitted numbers plus interpolated slots: {doubled}"
        )
    return {"findings_narrative": findings, "impression_narrative": impression}


def double_substituted_numbers(
    raw: str,
    interpolated: str,
    measurements: Iterable[dict],
) -> list[str]:
    """
    Payload numbers that appear both as an LLM literal (in slot-stripped raw text)
    and again after interpolation — e.g. "10.9 cc measured at 10.9 cc".
    """
    leaked_in_raw = set(leaked_numeric_literals(raw))
    if not leaked_in_raw:
        return []
    doubled: list[str] = []
    for m in measurements:
        if not isinstance(m, dict) or m.get("value") is None:
            continue
        token = str(m["value"])
        if token in leaked_in_raw and interpolated.count(token) >= 2:
            doubled.append(token)
    return doubled


def log_structured_number_leak(leaked: dict[str, list[str]], text: str, user_id: str = "system") -> None:
    log_report_draft_event(
        event_type="llm_structured_number_leak",
        user_id=user_id,
        payload={
            "severity": "high",
            "leaked_literals": leaked,
            "text": text[:500],
            "note": "Structural constraint failed: LLM emitted numbers instead of slots. "
            "Distinct from llm_hallucination_blocked (Prompt 1 validator).",
        },
    )


def validate_parsed_narrative(data: dict, schema: type[BaseModel]) -> BaseModel:
    """Parse tool input; reject extra numeric fields and embedded literals."""
    extra = extra_numeric_fields(data, schema)
    if extra:
        log_structured_number_leak({"extra_numeric_fields": extra}, str(data)[:400])
        raise StructuredNarrativeError(
            f"Model attempted to emit numeric fields reserved for grounding_payload: {extra}"
        )
    try:
        parsed = schema.model_validate(data)
    except ValidationError as exc:
        raise StructuredNarrativeError(f"Narrative failed schema validation: {exc}") from exc
    leaked: dict[str, list[str]] = {}
    for name, field in schema.model_fields.items():
        value = getattr(parsed, name)
        if isinstance(value, str):
            nums = leaked_numeric_literals(value)
            if nums:
                leaked[name] = nums
    if leaked:
        log_structured_number_leak(leaked, str(data)[:400])
        raise StructuredNarrativeError(f"LLM narrative contained numeric literals: {leaked}")
    return parsed
