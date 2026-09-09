import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AppPage } from "../components/layout/AppPage";
import ShadowModeBanner from "../components/shadow/ShadowModeBanner";
import { IosButton } from "../components/ui/IosButton";
import {
  BicrRole,
  enrollBicrCase,
  fetchBicrQueue,
  formatApiConnectionHint,
  getBicrCase,
  submitBicrAdjudication,
  submitBicrRead,
} from "../api/client";

type Verdict = "agree" | "partial" | "disagree";

const SEVERITIES = ["Normal", "Mild", "Moderate", "Severe"] as const;

export default function BicrReview() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const caseId = searchParams.get("caseId") || "";
  const role = (searchParams.get("role") || "reader1") as BicrRole;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bicr, setBicr] = useState<Record<string, unknown> | null>(null);
  const [caseReview, setCaseReview] = useState<Record<string, unknown> | null>(null);
  const [queue, setQueue] = useState<Array<Record<string, unknown>>>([]);

  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [gtClass, setGtClass] = useState<string | null>(null);
  const [gtSev, setGtSev] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [signerName, setSignerName] = useState("");
  const [signerRole, setSignerRole] = useState("");
  const [meaningOk, setMeaningOk] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (caseId) {
        try {
          const payload = await getBicrCase(caseId, role);
          setBicr((payload.bicr as Record<string, unknown>) || null);
          setCaseReview((payload.case_review as Record<string, unknown>) || null);
        } catch {
          await enrollBicrCase({ case_id: caseId, timepoint: "baseline" });
          const payload = await getBicrCase(caseId, role);
          setBicr((payload.bicr as Record<string, unknown>) || null);
          setCaseReview((payload.case_review as Record<string, unknown>) || null);
        }
      }
      const q = await fetchBicrQueue(role, 30);
      setQueue((q.items as Array<Record<string, unknown>>) || []);
    } catch (e) {
      setError(formatApiConnectionHint(e instanceof Error ? e.message : String(e)));
    } finally {
      setLoading(false);
    }
  }, [caseId, role]);

  useEffect(() => {
    void load();
  }, [load]);

  const task = String(caseReview?.task || "classification");
  const mr = (caseReview?.model_run as Record<string, unknown>) || {};
  const probs = (mr.class_probabilities as Record<string, number>) || {};
  const classKeys = useMemo(() => Object.keys(probs), [probs]);
  const bicrState = bicr || {};
  const canSubmit = Boolean(
    verdict &&
      meaningOk &&
      signerName.trim() &&
      signerRole.trim() &&
      (verdict === "agree" || (task === "classification" ? gtClass : gtSev)) &&
      (bicrState.can_submit as boolean),
  );

  async function handleSubmit() {
    if (!canSubmit || !caseId || !verdict) return;
    setSubmitting(true);
    setError(null);
    try {
      const groundTruth =
        verdict === "agree"
          ? null
          : task === "classification"
            ? { class: gtClass }
            : { severity: gtSev };
      const eSignature = {
        signer_name: signerName.trim(),
        signer_role: signerRole.trim(),
        credentials: "MD",
        meaning_acknowledged: meaningOk,
      };
      if (role === "adjudicator") {
        await submitBicrAdjudication(caseId, {
          verdict,
          ground_truth: groundTruth,
          clinical_notes: notes.trim() || null,
          time_spent_s: 60,
          e_signature: eSignature,
        });
      } else {
        const slot = role === "reader1" ? 1 : 2;
        await submitBicrRead(caseId, {
          reader_slot: slot,
          verdict,
          ground_truth: groundTruth,
          error_categories: [],
          clinical_notes: notes.trim() || null,
          time_spent_s: 60,
          e_signature: eSignature,
        });
      }
      setDone(true);
      void load();
    } catch (e) {
      setError(formatApiConnectionHint(e instanceof Error ? e.message : String(e)));
    } finally {
      setSubmitting(false);
    }
  }

  if (!caseId) {
    return (
      <AppPage title="BICR review queue" subtitle={`Role: ${role} · Dual independent read + adjudication`} wide>
        <ShadowModeBanner />
        {loading ? <p>Loading…</p> : null}
        {error ? <p className="app-text-error">{error}</p> : null}
        <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: 8 }}>
          {queue.map((row) => {
            const uid = String(row.case_id || "");
            return (
              <li key={uid}>
                <Link
                  to={`/bicr-review?caseId=${encodeURIComponent(uid)}&role=${role}`}
                  className="card"
                  style={{ display: "block", padding: 12, textDecoration: "none", color: "inherit" }}
                >
                  <div className="app-card-title">{uid}</div>
                  <div className="app-text-muted text-ios-caption1">
                    {String(row.timepoint || "—")} · {String(row.status || "—")}
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
        {!queue.length && !loading ? (
          <p className="app-text-muted">No cases in queue. Enroll from a case: add ?caseId=STUDY_UID</p>
        ) : null}
      </AppPage>
    );
  }

  if (loading) {
    return (
      <AppPage wide>
        <ShadowModeBanner />
        <p>Loading BICR case…</p>
      </AppPage>
    );
  }

  if (done || bicrState.status === "complete" || bicrState.status === "locked") {
    return (
      <AppPage title={`BICR ${String(bicrState.status || "submitted")}`} wide>
        <ShadowModeBanner />
        {bicrState.consensus ? (
          <pre className="app-report-pre">{JSON.stringify(bicrState.consensus, null, 2)}</pre>
        ) : null}
        <div style={{ marginTop: 12 }}>
          <IosButton variant="primary" size="md" onClick={() => navigate(`/bicr-review?role=${role}`)}>
            Back to queue
          </IosButton>
        </div>
      </AppPage>
    );
  }

  return (
    <AppPage wide>
      <ShadowModeBanner />
      <p className="app-text-muted text-ios-footnote" style={{ marginBottom: 10 }}>
        BICR mode — model label hidden for readers. Independent reads; adjudication when readers disagree.
      </p>
      <header className="app-page-header" style={{ marginBottom: 12 }}>
        <h1>BICR review · {role}</h1>
        <p>
          Study <span className="app-text-mono">{caseId}</span> · status{" "}
          <strong>{String(bicrState.status || "—")}</strong>
          {bicrState.timepoint ? ` · timepoint ${String(bicrState.timepoint)}` : ""}
        </p>
      </header>

      {role === "adjudicator" && bicrState.read_1_summary ? (
        <div className="card" style={{ marginBottom: 10 }}>
          <div style={{ fontWeight: 800 }}>Reader summaries (for adjudication)</div>
          <pre style={{ fontSize: 11, marginTop: 8 }}>{JSON.stringify(bicrState.read_1_summary, null, 2)}</pre>
          <pre style={{ fontSize: 11, marginTop: 8 }}>{JSON.stringify(bicrState.read_2_summary, null, 2)}</pre>
        </div>
      ) : null}

      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ fontWeight: 800 }}>Imaging task</div>
        <div style={{ marginTop: 6 }}>{task === "segmentation" ? "WMH segmentation review" : "Classification review"}</div>
        {task === "classification" ? (
          <div className="text-ios-caption1" style={{ marginTop: 8, color: "var(--ink-mute)" }}>
            Classes: {classKeys.join(", ") || "—"}
          </div>
        ) : null}
      </div>

      {(bicrState.can_submit as boolean) ? (
        <>
          <div className="app-chip-grid" style={{ marginBottom: 12 }}>
            {(["agree", "partial", "disagree"] as Verdict[]).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setVerdict(v)}
                className={`app-chip${verdict === v ? " app-chip--selected" : ""}`}
              >
                {v}
              </button>
            ))}
          </div>

          {verdict && verdict !== "agree" ? (
            <div className="card" style={{ marginBottom: 12 }}>
              <div style={{ fontWeight: 800, marginBottom: 8 }}>Ground truth</div>
              {task === "classification" ? (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {classKeys.map((c) => (
                    <button key={c} type="button" onClick={() => setGtClass(c)} style={{ padding: "8px 10px" }}>
                      {c}
                    </button>
                  ))}
                </div>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {SEVERITIES.map((s) => (
                    <button key={s} type="button" onClick={() => setGtSev(s)} style={{ padding: "8px 10px" }}>
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : null}

          <div className="card" style={{ marginBottom: 12 }}>
            <div style={{ fontWeight: 800, marginBottom: 8 }}>Part 11 electronic signature</div>
            <p className="text-ios-caption1" style={{ color: "var(--ink-mute)", marginBottom: 8 }}>
              {String(bicrState.part11_meaning || "")}
            </p>
            <input
              placeholder="Signer name"
              value={signerName}
              onChange={(e) => setSignerName(e.target.value)}
              style={{ width: "100%", marginBottom: 8, padding: 8 }}
            />
            <input
              placeholder="Signer role (e.g. neuroradiologist)"
              value={signerRole}
              onChange={(e) => setSignerRole(e.target.value)}
              style={{ width: "100%", marginBottom: 8, padding: 8 }}
            />
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 13 }}>
              <input type="checkbox" checked={meaningOk} onChange={(e) => setMeaningOk(e.target.checked)} />
              I acknowledge this electronic signature is legally binding (21 CFR Part 11 research build).
            </label>
          </div>

          <textarea
            placeholder="Clinical notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            style={{ width: "100%", marginBottom: 12, padding: 10 }}
          />

          {error ? <p className="app-text-error" style={{ whiteSpace: "pre-wrap" }}>{error}</p> : null}

          <IosButton variant="primary" size="md" disabled={!canSubmit || submitting} onClick={() => void handleSubmit()}>
            {submitting ? "Submitting…" : role === "adjudicator" ? "Submit adjudication" : "Submit independent read"}
          </IosButton>
        </>
      ) : (
        <p style={{ color: "var(--ink-mute)" }}>
          Your slot is complete or this case is not accepting submissions for role <strong>{role}</strong>.
        </p>
      )}
    </AppPage>
  );
}
