import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import ShadowModeBanner from "../components/shadow/ShadowModeBanner";
import { IosButton } from "../components/ui/IosButton";
import {
  formatApiConnectionHint,
  getCase,
  getClinicalFeedbackRecent,
  getClinicalFeedbackStats,
  submitStructuredClinicalFeedback,
} from "../api/client";
import { fetchShadowQueue } from "../lib/api";
import type { ShadowQueueResponse } from "../lib/api";

type LabelClass = "ok" | "warn" | "danger";
type Verdict = "agree" | "partial" | "disagree";
type Task = "classification" | "segmentation";

type CaseReview = {
  case_id: string;
  study_uid: string;
  received_at?: string | null;
  task: Task;
  site_id?: string | null;
  patient: { age?: number; sex?: string };
  model_run: {
    audit_id: string;
    model_name: string;
    model_version: string;
    label: string;
    label_class: LabelClass;
    confidence: number;
    class_probabilities: Record<string, number>;
    inference_time_ms: number;
    input_shape: number[];
    wmh_metrics?: Record<string, unknown>;
  };
  feedback?: {
    status?: string;
    verdict?: string;
    feedback_id?: string | null;
    submitted_at?: string | null;
    error_categories?: string[];
    ground_truth?: Record<string, unknown> | null;
    clinical_notes?: string | null;
    legacy?: boolean;
  } | null;
};

const ERROR_TAGS = [
  "wrong_class",
  "confidence_too_high",
  "confidence_too_low",
  "saliency_wrong_region",
  "missed_finding",
  "out_of_distribution",
  "image_quality",
  "sequence_mismatch",
] as const;

const SEVERITIES = ["Normal", "Mild", "Moderate", "Severe"] as const;

function labelTone(lc: LabelClass): string {
  if (lc === "danger") return "#dc2626";
  if (lc === "warn") return "#d97706";
  return "var(--modern-ink)";
}

function FeedbackSkeleton() {
  return (
    <div className="container" style={{ marginTop: 20 }}>
      <div className="card" style={{ height: 120, animation: "pulse 1.2s ease-in-out infinite" }} />
      <div className="card" style={{ height: 220, marginTop: 12 }} />
    </div>
  );
}

function CasePicker({ onPick }: { onPick: (uid: string) => void }) {
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      setErr(null);
      try {
        const p = new URLSearchParams();
        p.set("feedback", "pending");
        p.set("limit", "40");
        const res: ShadowQueueResponse = await fetchShadowQueue(p);
        if (!mounted) return;
        setRows((res.items || []) as Array<Record<string, unknown>>);
      } catch (e) {
        if (!mounted) return;
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [reloadToken]);

  if (loading) return <FeedbackSkeleton />;
  if (err) {
    return (
      <div className="container" style={{ marginTop: 16 }}>
        <p style={{ color: "#dc2626" }}>{err}</p>
        <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
          <IosButton variant="secondary" size="md" onClick={() => setReloadToken((n) => n + 1)}>
            Refresh list
          </IosButton>
          <Link to="/dashboard">Back to dashboard</Link>
        </div>
      </div>
    );
  }
  if (!rows.length) {
    return (
      <div className="container" style={{ marginTop: 16 }}>
        <h2 className="text-ios-title2" style={{ marginBottom: 8 }}>
          Choose a case to review
        </h2>
        <p style={{ color: "var(--ink-mute)" }}>All caught up — no cases pending review in the shadow queue.</p>
        <div style={{ marginTop: 12 }}>
          <IosButton variant="secondary" size="md" onClick={() => window.history.back()}>
            Back
          </IosButton>
        </div>
      </div>
    );
  }

  return (
    <div className="container" style={{ marginTop: 16, maxWidth: 720 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <h2 className="text-ios-title2" style={{ marginBottom: 12 }}>
          Choose a case to review
        </h2>
        <IosButton variant="secondary" size="sm" disabled={loading} onClick={() => setReloadToken((n) => n + 1)}>
          {loading ? "Loading…" : "Refresh"}
        </IosButton>
      </div>
      <p className="text-ios-footnote" style={{ color: "var(--ink-mute)", marginBottom: 14 }}>
        Pending shadow-queue cases (feedback = pending).
      </p>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 8 }}>
        {rows.map((r) => {
          const uid = String(r.study_uid || r.study_instance_uid || "");
          const mr = (r.model_run as Record<string, unknown>) || {};
          return (
            <li key={uid}>
              <button
                type="button"
                className="card"
                aria-label={`Open case ${uid}`}
                style={{
                  width: "100%",
                  textAlign: "left",
                  cursor: "pointer",
                  border: "1px solid var(--line)",
                  background: "rgba(255,255,255,0.92)",
                }}
                onClick={() => onPick(uid)}
              >
                <div style={{ fontWeight: 800 }}>{uid}</div>
                <div className="text-ios-caption1" style={{ color: "var(--ink-mute)", marginTop: 4 }}>
                  {String(mr.model_name || "—")} · {String(mr.label || "—")} ·{" "}
                  {typeof mr.confidence === "number" ? `${(mr.confidence * 100).toFixed(1)}%` : "—"}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function PredictionCard({ cr }: { cr: CaseReview }) {
  const mr = cr.model_run;
  const probs = mr.class_probabilities || {};
  const sorted = Object.entries(probs).sort((a, b) => b[1] - a[1]);
  const top = sorted[0]?.[0];

  if (cr.task === "segmentation" && mr.wmh_metrics) {
    const wm = mr.wmh_metrics;
    return (
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ fontWeight: 800, marginBottom: 8 }}>AI segmentation summary</div>
        <div style={{ fontSize: 22, fontWeight: 800, color: labelTone(mr.label_class) }}>
          {mr.label} · {(mr.confidence * 100).toFixed(1)}% confidence
        </div>
        <div className="text-ios-footnote" style={{ color: "var(--ink-mute)", marginTop: 8 }}>
          WMH volume: {String(wm.volume_cc ?? "—")} cc · Severity: {String(wm.severity_grade ?? "—")} · Voxels:{" "}
          {String(wm.lesion_voxels ?? "—")}
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div style={{ fontWeight: 800, marginBottom: 8 }}>AI prediction</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: labelTone(mr.label_class) }}>
        {mr.label} · {(mr.confidence * 100).toFixed(1)}% confidence
      </div>
      <div style={{ marginTop: 12 }}>
        {sorted.map(([cls, p]) => {
          const isTop = cls === top;
          const pct = Math.round((p as number) * 1000) / 10;
          return (
            <div key={cls} style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: isTop ? "var(--ink)" : "var(--ink-soft)" }}>{cls}</span>
                <span style={{ color: isTop ? "var(--modern-primary)" : "var(--ink-mute)" }}>{pct}%</span>
              </div>
              <div style={{ height: 8, borderRadius: 999, background: "var(--line)", overflow: "hidden" }}>
                <div
                  style={{
                    height: "100%",
                    width: `${Math.max(2, (p as number) * 100)}%`,
                    background: isTop ? "var(--modern-primary)" : "var(--ink-mute)",
                    opacity: isTop ? 1 : 0.45,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VerdictPicker({ value, onChange }: { value: Verdict | null; onChange: (v: Verdict) => void }) {
  const btn = (v: Verdict, label: string, hint: string, icon: string) => {
    const sel = value === v;
    return (
      <button
        type="button"
        key={v}
        aria-pressed={sel}
        aria-label={label}
        onClick={() => onChange(v)}
        className={`app-verdict-btn${sel ? " app-verdict-btn--selected" : ""}`}
      >
        <div style={{ fontSize: 18 }}>{icon}</div>
        <div style={{ fontWeight: 800, marginTop: 4 }}>{label}</div>
        <div className="text-ios-caption2" style={{ color: "var(--ink-mute)", marginTop: 2 }}>
          {hint}
        </div>
      </button>
    );
  }
  return (
    <div role="group" aria-label="Verdict" className="app-verdict-grid">
      {btn("agree", "Agree", "Model matches your read", "✓")}
      {btn("partial", "Partially", "Mostly right with material caveats", "◐")}
      {btn("disagree", "Disagree", "Wrong finding or severity", "✕")}
    </div>
  );
}

export default function ClinicalFeedback() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const caseId = searchParams.get("caseId");
  const fromQueue = searchParams.get("fromQueue") === "1";

  const [cr, setCr] = useState<CaseReview | null>(null);
  const [loading, setLoading] = useState(Boolean(caseId));
  const [error, setError] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [gtClass, setGtClass] = useState<string | null>(null);
  const [gtSev, setGtSev] = useState<string | null>(null);
  const [errors, setErrors] = useState<Set<string>>(new Set());
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<{ feedback_id: string; audit_id: string } | null>(null);
  const [stats, setStats] = useState<{ reviewed_this_month: number; agreement_rate: number; avg_time_s: number } | null>(
    null,
  );
  const [recent, setRecent] = useState<Array<Record<string, unknown>>>([]);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [countdown, setCountdown] = useState<number>(0);
  const [caseTimerTick, setCaseTimerTick] = useState(0);
  const openedAt = useRef(Date.now());
  const notesRef = useRef<HTMLTextAreaElement | null>(null);

  const loadCase = useCallback(async () => {
    if (!caseId) {
      setLoading(false);
      setCr(null);
      return;
    }
    setLoading(true);
    setError(null);
    setVerdict(null);
    setGtClass(null);
    setGtSev(null);
    setErrors(new Set());
    setNotes("");
    setDone(null);
    openedAt.current = Date.now();
    setCaseTimerTick(0);
    try {
      const payload = await getCase(caseId);
      const review = payload?.case_review as CaseReview | undefined;
      if (!review) {
        throw new Error("Case response missing case_review payload; update the API.");
      }
      setCr(review);
    } catch (e) {
      setCr(null);
      setError(formatApiConnectionHint(e instanceof Error ? e.message : String(e)));
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    void loadCase();
  }, [loadCase]);

  useEffect(() => {
    if (!caseId) return;
    (async () => {
      try {
        const [s, r] = await Promise.all([getClinicalFeedbackStats(), getClinicalFeedbackRecent(6)]);
        setStats(s);
        setRecent(r.items || []);
      } catch {
        setStats(null);
      }
    })();
  }, [caseId, done]);

  const isReadOnly = Boolean(cr?.feedback?.status && cr.feedback.status === "submitted");

  useEffect(() => {
    if (!cr || isReadOnly || done) return;
    const id = window.setInterval(() => setCaseTimerTick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, [cr, isReadOnly, done]);

  const classKeys = useMemo(() => Object.keys(cr?.model_run.class_probabilities || {}), [cr]);

  const canSubmit = useMemo(() => {
    if (!verdict || !cr) return false;
    if (verdict === "agree") return true;
    if (cr.task === "classification") return Boolean(gtClass);
    return Boolean(gtSev);
  }, [verdict, cr, gtClass, gtSev]);

  const toggleErr = (t: string) => {
    setErrors((prev) => {
      const n = new Set(prev);
      if (n.has(t)) n.delete(t);
      else n.add(t);
      return n;
    });
  };

  const pickNextFromQueue = useCallback(async () => {
    try {
      const p = new URLSearchParams();
      p.set("feedback", "pending");
      p.set("limit", "50");
      const res = await fetchShadowQueue(p);
      const items = (res.items || []) as Array<Record<string, unknown>>;
      const next = items.map((i) => String(i.study_uid || "")).find((u) => u && u !== caseId);
      if (next) {
        const q = new URLSearchParams();
        q.set("caseId", next);
        if (fromQueue) q.set("fromQueue", "1");
        navigate(`/clinical-feedback?${q.toString()}`, { replace: true });
        return;
      }
    } catch {
      /* ignore */
    }
    navigate("/clinical-feedback", { replace: true });
  }, [caseId, fromQueue, navigate]);

  useEffect(() => {
    if (!done || !fromQueue) return;
    let n = 5;
    setCountdown(n);
    const iv = window.setInterval(() => {
      n -= 1;
      setCountdown(Math.max(0, n));
      if (n <= 0) {
        window.clearInterval(iv);
        void pickNextFromQueue();
      }
    }, 1000);
    return () => window.clearInterval(iv);
  }, [done, fromQueue, pickNextFromQueue]);

  const handleSubmit = useCallback(async () => {
    if (!canSubmit || !cr || !caseId || verdict == null) return;
    setSubmitting(true);
    setError(null);
    try {
      const groundTruth =
        verdict === "agree"
          ? null
          : cr.task === "classification"
            ? { class: gtClass }
            : { severity: gtSev };
      const out = await submitStructuredClinicalFeedback({
        case_id: cr.case_id,
        verdict,
        ground_truth: groundTruth,
        error_categories: Array.from(errors),
        clinical_notes: notes.trim() || null,
        time_spent_s: Math.floor((Date.now() - openedAt.current) / 1000),
      });
      setDone({ feedback_id: out.feedback_id, audit_id: out.audit_id });
    } catch (ex) {
      setError(formatApiConnectionHint(ex instanceof Error ? ex.message : String(ex)));
    } finally {
      setSubmitting(false);
    }
  }, [canSubmit, cr, caseId, verdict, gtClass, gtSev, errors, notes]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) {
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canSubmit && !submitting && !isReadOnly) {
          e.preventDefault();
          void handleSubmit();
        }
        return;
      }
      if (e.key === "a" || e.key === "A") setVerdict("agree");
      if (e.key === "p" || e.key === "P") setVerdict("partial");
      if (e.key === "d" || e.key === "D") setVerdict("disagree");
      if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        notesRef.current?.focus();
      }
      if (e.key === "Escape") navigate(fromQueue ? "/shadow-queue" : "/dashboard");
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canSubmit && !submitting && !isReadOnly) {
        e.preventDefault();
        void handleSubmit();
      }
      if (cr?.task === "classification" && verdict && verdict !== "agree") {
        const n = Number(e.key);
        if (n >= 1 && n <= 4 && classKeys[n - 1]) setGtClass(classKeys[n - 1]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [canSubmit, submitting, isReadOnly, navigate, fromQueue, cr, verdict, classKeys, handleSubmit]);

  const secondsOnCase = useMemo(
    () => Math.floor((Date.now() - openedAt.current) / 1000),
    [caseTimerTick, cr?.case_id],
  );

  if (!caseId) {
    return (
      <div className="page">
        <ShadowModeBanner />
        <CasePicker
          onPick={(uid) => {
            const q = new URLSearchParams();
            q.set("caseId", uid);
            navigate(`/clinical-feedback?${q.toString()}`);
          }}
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="page">
        <ShadowModeBanner />
        <FeedbackSkeleton />
      </div>
    );
  }

  if (error || !cr) {
    return (
      <div className="page container" style={{ marginTop: 16 }}>
        <ShadowModeBanner />
        <h2 className="text-ios-title2">Could not load case</h2>
        <p style={{ color: "#dc2626", marginTop: 8, whiteSpace: "pre-wrap" }}>{error || "Case not found"}</p>
        <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
          <IosButton variant="primary" size="md" onClick={() => void loadCase()}>
            Try again
          </IosButton>
          <IosButton variant="secondary" size="md" onClick={() => navigate("/dashboard")}>
            Back to dashboard
          </IosButton>
        </div>
      </div>
    );
  }

  if (done) {
    return (
      <div className="page container" style={{ marginTop: 20, maxWidth: 560 }}>
        <ShadowModeBanner />
        <div style={{ fontSize: 48, color: "var(--modern-primary)" }}>✓</div>
        <h2 className="text-ios-title2" style={{ marginTop: 8 }}>
          Feedback submitted
        </h2>
        <p className="text-ios-footnote" style={{ color: "var(--ink-mute)", marginTop: 8 }}>
          Audit ID (immutable)
        </p>
        <pre
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: 13,
            padding: 10,
            background: "var(--surface)",
            border: "1px solid var(--line)",
            borderRadius: "var(--radius-sm)",
            marginTop: 6,
          }}
        >
          {done.audit_id}
        </pre>
        {fromQueue ? (
          <p className="text-ios-footnote" style={{ marginTop: 10 }}>
            Loading next case in {countdown}s…
          </p>
        ) : null}
        <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
          <IosButton variant="primary" size="md" onClick={() => void pickNextFromQueue()}>
            Review next case
          </IosButton>
          <IosButton variant="secondary" size="md" onClick={() => navigate("/dashboard")}>
            Back to dashboard
          </IosButton>
        </div>
      </div>
    );
  }

  if (isReadOnly) {
    const fb = cr.feedback!;
    return (
      <div className="page container" style={{ marginTop: 16, maxWidth: 900 }}>
        <ShadowModeBanner />
        <h2 className="text-ios-title2">Already reviewed</h2>
        <p style={{ color: "var(--ink-mute)", marginTop: 8 }}>
          This case was already reviewed{fb.submitted_at ? ` on ${String(fb.submitted_at)}` : ""}.
        </p>
        <PredictionCard cr={cr} />
        <div className="card" style={{ marginTop: 12, opacity: 0.85 }}>
          <div style={{ fontWeight: 800 }}>Verdict</div>
          <div style={{ marginTop: 6 }}>{fb.verdict}</div>
          {fb.ground_truth ? (
            <pre style={{ marginTop: 8, fontSize: 12 }}>{JSON.stringify(fb.ground_truth, null, 2)}</pre>
          ) : null}
          {fb.clinical_notes ? <p style={{ marginTop: 8 }}>{fb.clinical_notes}</p> : null}
        </div>
        <div style={{ marginTop: 14 }}>
          <IosButton variant="secondary" size="md" onClick={() => navigate("/shadow-queue")}>
            Back to queue
          </IosButton>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <ShadowModeBanner />
      <div className="container" style={{ maxWidth: 1040, marginTop: 12 }}>
        <p className="text-ios-footnote" style={{ color: "var(--modern-ink-soft)", marginBottom: 12 }}>
          Shadow mode feedback: verdict is recorded for model improvement only — not sent to the clinical record.
        </p>

        <header style={{ marginBottom: 12 }}>
          <h1 className="text-ios-title2" style={{ margin: 0 }}>
            Clinical feedback
          </h1>
          <p className="text-ios-footnote" style={{ color: "var(--ink-mute)", marginTop: 4 }}>
            Study <span style={{ fontFamily: "ui-monospace, monospace" }}>{cr.study_uid}</span> · {cr.model_run.model_name}{" "}
            · {cr.task}
          </p>
        </header>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: 14,
            alignItems: "start",
          }}
        >
          <div>
            <PredictionCard cr={cr} />
            <VerdictPicker value={verdict} onChange={setVerdict} />

            {verdict && verdict !== "agree" ? (
              <div
                className="card"
                style={{
                  marginTop: 10,
                  border: "1px solid var(--line)",
                  animation: "none",
                }}
              >
                <div style={{ fontWeight: 800, marginBottom: 8 }}>Ground truth</div>
                {cr.task === "classification" ? (
                  <div>
                    <div className="text-ios-caption1" style={{ color: "var(--ink-mute)", marginBottom: 6 }}>
                      Correct finding
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 8 }}>
                      {classKeys.map((c) => (
                        <button
                          type="button"
                          key={c}
                          onClick={() => setGtClass(c)}
                          style={{
                            padding: "10px 8px",
                            borderRadius: "var(--radius-sm)",
                            border: gtClass === c ? "1px solid var(--modern-primary)" : "1px solid var(--line)",
                            background: gtClass === c ? "color-mix(in srgb, var(--modern-primary) 8%, var(--modern-surface))" : "var(--surface)",
                            cursor: "pointer",
                            fontWeight: 600,
                          }}
                        >
                          {c}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div>
                    <div className="text-ios-caption1" style={{ color: "var(--ink-mute)", marginBottom: 6 }}>
                      Correct severity
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {SEVERITIES.map((s) => (
                        <button
                          type="button"
                          key={s}
                          onClick={() => setGtSev(s)}
                          style={{
                            padding: "8px 12px",
                            borderRadius: 999,
                            border: gtSev === s ? "1px solid var(--modern-primary)" : "1px solid var(--line)",
                            background: gtSev === s ? "color-mix(in srgb, var(--modern-primary) 8%, var(--modern-surface))" : "var(--surface)",
                            cursor: "pointer",
                            fontWeight: 700,
                          }}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <div style={{ fontWeight: 800, marginTop: 14, marginBottom: 6 }}>Error categories</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {ERROR_TAGS.map((t) => {
                    const on = errors.has(t);
                    return (
                      <button
                        type="button"
                        key={t}
                        onClick={() => toggleErr(t)}
                        style={{
                          fontSize: 11,
                          padding: "4px 8px",
                          borderRadius: 999,
                          border: on ? "1px solid var(--modern-primary)" : "1px solid var(--line)",
                          background: on ? "rgba(37,196,143,0.12)" : "rgba(248,250,249,0.9)",
                          cursor: "pointer",
                        }}
                      >
                        {t}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}

            <div style={{ marginTop: 12 }}>
              <label style={{ fontWeight: 700 }}>Clinical notes (optional)</label>
              <textarea
                ref={notesRef}
                maxLength={500}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="What did you see that the model missed or got wrong?"
                rows={4}
                style={{
                  width: "100%",
                  marginTop: 6,
                  padding: 10,
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--line)",
                  fontFamily: "inherit",
                }}
              />
              <div className="text-ios-caption2" style={{ color: "var(--ink-mute)", marginTop: 4 }}>
                {notes.length}/500 · Notes improve retraining quality when tied to error tags.
              </div>
            </div>

            {error ? (
              <div style={{ marginTop: 12, color: "#dc2626", fontWeight: 600, whiteSpace: "pre-wrap" }}>{error}</div>
            ) : null}

            <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap", alignItems: "center" }}>
              <IosButton variant="primary" size="md" disabled={!canSubmit || submitting} onClick={() => void handleSubmit()}>
                {submitting ? "Submitting…" : "Submit verdict"}
              </IosButton>
              <IosButton variant="ghost" size="md" onClick={() => navigate(fromQueue ? "/shadow-queue" : "/dashboard")}>
                Skip
              </IosButton>
              <span className="text-ios-caption1" style={{ color: "var(--ink-mute)", marginLeft: "auto" }}>
                Time on case: {secondsOnCase}s
              </span>
            </div>
          </div>

          <aside>
            <div className="card" style={{ marginBottom: 10 }}>
              <div style={{ fontWeight: 800, marginBottom: 8 }}>Case context</div>
              <div className="text-ios-caption1" style={{ color: "var(--ink-soft)" }}>
                Site: {cr.site_id || "—"}
              </div>
              <div className="text-ios-caption1" style={{ color: "var(--ink-soft)", marginTop: 4 }}>
                Model: {cr.model_run.model_name} ({cr.model_run.model_version})
              </div>
              <div className="text-ios-caption1" style={{ color: "var(--ink-soft)", marginTop: 4 }}>
                Inference: {cr.model_run.inference_time_ms} ms
              </div>
              <div className="text-ios-caption1" style={{ color: "var(--ink-soft)", marginTop: 4 }}>
                Patient: age {cr.patient?.age ?? "—"} · sex {cr.patient?.sex ?? "—"}
              </div>
            </div>

            <div className="card" style={{ marginBottom: 10 }}>
              <div style={{ fontWeight: 800, marginBottom: 8 }}>This month</div>
              {stats ? (
                <>
                  <div className="text-ios-body">Reviewed: {stats.reviewed_this_month}</div>
                  <div className="text-ios-body" style={{ marginTop: 4 }}>
                    Agreement rate: {(stats.agreement_rate * 100).toFixed(1)}%
                  </div>
                  <div className="text-ios-body" style={{ marginTop: 4 }}>
                    Avg time: {stats.avg_time_s}s
                  </div>
                </>
              ) : (
                <div className="text-ios-footnote" style={{ color: "var(--ink-mute)" }}>
                  Stats unavailable offline.
                </div>
              )}
            </div>

            <div className="card">
              <div style={{ fontWeight: 800, marginBottom: 6 }}>How feedback is used</div>
              <p className="text-ios-caption1" style={{ color: "var(--ink-mute)", lineHeight: 1.45 }}>
                Verdicts are de-identified for model retraining and quality metrics. They are not written to the EHR in
                shadow mode.
              </p>
              {recent.length ? (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4 }}>Recent</div>
                  <ul style={{ paddingLeft: 16, fontSize: 11, color: "var(--ink-soft)" }}>
                    {recent.map((r) => (
                      <li key={String(r.feedback_id)} style={{ marginBottom: 4 }}>
                        {String(r.case_id)} · {String(r.verdict)}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      </div>

      <button
        type="button"
        title="Keyboard shortcuts"
        aria-label="Keyboard shortcuts"
        onClick={() => setShortcutsOpen(true)}
        style={{
          position: "fixed",
          right: 16,
          bottom: 16,
          width: 36,
          height: 36,
          borderRadius: 999,
          border: "1px solid var(--line)",
          background: "var(--white)",
          cursor: "pointer",
          fontWeight: 800,
        }}
      >
        ?
      </button>

      {shortcutsOpen ? (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(5,46,28,0.35)",
            zIndex: 50,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
          }}
          role="presentation"
          onClick={() => setShortcutsOpen(false)}
        >
          <div
            className="card"
            style={{ maxWidth: 420, width: "100%" }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="clinical-feedback-shortcuts-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div id="clinical-feedback-shortcuts-title" style={{ fontWeight: 800, marginBottom: 8 }}>
              Shortcuts
            </div>
            <ul className="text-ios-footnote" style={{ color: "var(--ink-soft)", paddingLeft: 18, lineHeight: 1.6 }}>
              <li>A — Agree</li>
              <li>P — Partially</li>
              <li>D — Disagree</li>
              <li>1–4 — Pick class (when disagree/partial, classification)</li>
              <li>N — Focus notes</li>
              <li>Cmd/Ctrl + Enter — Submit</li>
              <li>Esc — Skip / back</li>
            </ul>
            <div style={{ marginTop: 10 }}>
              <IosButton variant="secondary" size="sm" onClick={() => setShortcutsOpen(false)}>
                Close
              </IosButton>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
