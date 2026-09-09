"""Shadow feedback events join audit_id and persist only (clicks are not training data)."""

from __future__ import annotations

from src.clinical.feedback_event import (
    FEEDBACK_CODES_V1,
    aggregate_feedback_metrics,
    build_feedback_event,
    is_allowed_feedback_code,
    map_feedback_code,
    measurements_unedited,
)


def test_v1_codes_include_radiologist_shortcuts():
    assert FEEDBACK_CODES_V1 == {
        "agree",
        "overcall",
        "undercall",
        "wrong_anatomy",
        "wrong_delta",
        "useless",
    }
    assert is_allowed_feedback_code("wrong_delta")
    assert is_allowed_feedback_code("disagree")  # legacy mapped on write
    assert not is_allowed_feedback_code("retrain_now")


def test_legacy_codes_map_keep_raw():
    assert map_feedback_code("disagree") == ("undercall", "disagree")
    assert map_feedback_code("partial") == ("useless", "partial")
    assert map_feedback_code("overcall") == ("overcall", "overcall")


def test_feedback_event_joins_audit_id():
    ev = build_feedback_event(
        feedback_id="fb_1",
        audit_id="aud_abc",
        study_uid="1.2.3",
        codes=["overcall"],
        submitted_by="rad-1",
        submitted_at="2026-09-08T00:00:00Z",
        time_to_draft_s=12,
        time_to_feedback_s=47,
        engine_versions={"wmh": "v1"},
    )
    assert ev["schema"] == "neurosight.feedback.v1"
    assert ev["audit_id"] == "aud_abc"
    assert ev["codes"] == ["overcall"]
    assert ev["codes_raw"] == ["overcall"]
    assert ev["measurements_unedited"] is False
    assert measurements_unedited(["agree"]) is True
    assert ev["timing"]["time_to_feedback_s"] == 47


def test_legacy_disagree_not_stored_as_primary():
    ev = build_feedback_event(
        feedback_id="fb_2",
        audit_id="join_audit_01",
        study_uid="1.2.3",
        codes=["disagree"],
        submitted_by="rad-1",
        submitted_at="2026-09-08T00:01:00Z",
        ingest_at="2026-09-08T00:00:00Z",
        draft_ready_at="2026-09-08T00:00:10Z",
    )
    assert ev["codes"] == ["undercall"]
    assert ev["codes_raw"] == ["disagree"]
    assert ev["timing"]["time_to_draft_s"] == 10


def test_aggregate_feedback_metrics_from_stored_events():
    rows = [
        build_feedback_event(
            feedback_id="a",
            audit_id="aud1",
            study_uid="s1",
            codes=["agree"],
            submitted_by="u",
            submitted_at="2026-09-08T00:02:00Z",
            time_to_draft_s=8,
            time_to_feedback_s=20,
            measurements_unedited=True,
            engine_versions={"wmh": "v1"},
        ),
        build_feedback_event(
            feedback_id="b",
            audit_id="aud2",
            study_uid="s2",
            codes=["disagree"],
            submitted_by="u",
            submitted_at="2026-09-08T00:03:00Z",
            time_to_draft_s=12,
            time_to_feedback_s=40,
            measurements_unedited=False,
            engine_versions={"wmh": "v1"},
        ),
    ]
    m = aggregate_feedback_metrics(rows)
    assert m["n"] == 2
    assert m["time_to_draft_s_mean"] == 10.0
    assert m["time_to_feedback_s_mean"] == 30.0
    assert m["measurements_unedited_pct"] == 0.5
    assert m["disagreement_codes_by_engine"]["wmh=v1"]["undercall"] == 1
