import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import EvidenceDrawer, { EvidenceCitation } from "../components/EvidenceDrawer";
import { getCase } from "../api/client";

type StoredPrediction = {
  scanBase64: string;
  filename: string;
  model: string;
  study_instance_uid: string;
  site_id?: string;
  shadow_mode: boolean;
  prediction: {
    label: string;
    confidence: number;
  };
};

type StoredReport = {
  study_instance_uid: string;
  report_text: string;
  timestamp: string;
};

function getSessionPrediction(studyId: string): StoredPrediction | null {
  const raw = sessionStorage.getItem("lastPrediction");
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as StoredPrediction;
    if (parsed.study_instance_uid !== studyId) return null;
    return parsed;
  } catch {
    return null;
  }
}

function getSessionReport(studyId: string): StoredReport | null {
  const raw = sessionStorage.getItem("lastReport");
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as StoredReport;
    if (parsed.study_instance_uid !== studyId) return null;
    return parsed;
  } catch {
    return null;
  }
}

export default function ReadingMode() {
  const { studyId } = useParams<{ studyId: string }>();
  const [pred, setPred] = useState<StoredPrediction | null>(null);
  const [report, setReport] = useState<StoredReport | null>(null);
  const [apiLoaded, setApiLoaded] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

  const [check1, setCheck1] = useState<boolean>(false);
  const [check2, setCheck2] = useState<boolean>(false);
  const [check3, setCheck3] = useState<boolean>(false);
  const allChecked = check1 && check2 && check3;

  useEffect(() => {
    let mounted = true;
    (async () => {
      setError("");
      if (!studyId) return;

      // Always seed from session first (best for image preview + report text).
      const sessionPred = getSessionPrediction(studyId);
      const sessionReport = getSessionReport(studyId);
      if (mounted) {
        setPred(sessionPred);
        setReport(sessionReport);
      }

      // Then try Mongo-backed case detail (for metadata consistency).
      try {
        const payload = await getCase(studyId);
        if (!mounted) return;
        const inf = payload?.inference || {};
        setApiLoaded(true);

        setPred((prev) => {
          const scanBase64 = prev?.scanBase64 || sessionPred?.scanBase64 || "";
          return {
            scanBase64,
            filename: inf.filename || prev?.filename || "scan",
            model: inf.model || prev?.model || "custom_cnn",
            study_instance_uid: studyId,
            site_id: inf.site_id || prev?.site_id,
            shadow_mode: Boolean(inf.shadow_mode ?? prev?.shadow_mode ?? true),
            prediction: {
              label: inf.label || prev?.prediction?.label || "—",
              confidence: typeof inf.confidence === "number" ? inf.confidence : prev?.prediction?.confidence || 0,
            },
          };
        });
      } catch (e) {
        if (!mounted) return;
        setApiLoaded(false);
        // Only show error if we also have nothing useful in session.
        if (!sessionPred && !sessionReport) setError(e instanceof Error ? e.message : String(e));
      }
    })();

    return () => {
      mounted = false;
    };
  }, [studyId]);

  const citations: EvidenceCitation[] = useMemo(() => {
    if (!studyId) return [];
    return [
      {
        id: `case-${studyId}-1`,
        title: "Shadow mode sign-off",
        source: "docs/clinical-workflow.md",
        snippet:
          "In shadow mode, results should be reviewed retrospectively with clinician feedback captured. Low-confidence cases should be routed for mandatory review.",
        score: 0.93,
      },
      {
        id: `case-${studyId}-2`,
        title: "Audit trail requirement",
        source: "docs/workflows-and-features.md",
        snippet:
          "Every AI-assisted decision needs traceability: request metadata, model version, timestamps, and clinician feedback status.",
        score: 0.89,
      },
    ];
  }, [studyId]);

  function onMarkReviewed() {
    if (!studyId) return;
    sessionStorage.setItem(
      `readingReviewed:${studyId}`,
      JSON.stringify({ reviewed: true, timestamp: new Date().toISOString() })
    );
    alert("Marked as reviewed (session-only). Next step: persist sign-off to backend.");
  }

  function onPrint() {
    window.print();
  }

  if (!studyId) {
    return (
      <div className="container">
        <h2 style={{ marginTop: 16 }}>Reading mode</h2>
        <p style={{ color: "var(--ink-mute)" }}>Missing study ID.</p>
      </div>
    );
  }

  return (
    <div className="container" style={{ maxWidth: 1080 }}>
      <div style={{ marginTop: 16, display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0 }}>Reading mode</h2>
          <div style={{ color: "var(--ink-mute)", marginTop: 6 }}>
            Case <b>{studyId}</b> · {apiLoaded ? "Mongo-backed metadata" : "Session view"} ·{" "}
            <button className="btn" type="button" onClick={() => setDrawerOpen(true)} style={{ padding: "6px 10px" }}>
              Evidence
            </button>
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <button className="btn btnOutline" type="button" onClick={onPrint}>
            Print
          </button>
          <button className="btnPrimary" type="button" disabled={!allChecked} onClick={onMarkReviewed}>
            Sign / Mark reviewed
          </button>
        </div>
      </div>

      {error ? (
        <div className="card" style={{ marginTop: 14, borderColor: "rgba(220, 38, 38, 0.25)" }}>
          <div style={{ color: "crimson", fontWeight: 700 }}>Unable to load case</div>
          <div style={{ color: "var(--ink-mute)", marginTop: 6 }}>{error}</div>
          <div style={{ marginTop: 10 }}>
            <Link to="/upload" className="btn">
              Upload again
            </Link>
          </div>
        </div>
      ) : null}

      <div style={{ display: "grid", gridTemplateColumns: "1.05fr 0.95fr", gap: 14, marginTop: 14 }}>
        <div className="card">
          <div style={{ fontWeight: 900 }}>Scan review</div>
          <div style={{ marginTop: 10 }}>
            {pred?.scanBase64 ? (
              <div style={{ position: "relative", borderRadius: 16, overflow: "hidden", border: "1px solid var(--line)" }}>
                <img src={pred.scanBase64} alt="Scan preview" style={{ width: "100%", display: "block" }} />
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    background:
                      "radial-gradient(circle at 50% 40%, rgba(244, 63, 94, 0.22), transparent 55%), radial-gradient(circle at 30% 70%, rgba(59, 130, 246, 0.18), transparent 55%)",
                    mixBlendMode: "screen",
                    pointerEvents: "none",
                  }}
                />
              </div>
            ) : (
              <div style={{ color: "var(--ink-mute)" }}>
                No image preview in this session. Open the case from <Link to="/upload">Upload</Link> to cache the scan.
              </div>
            )}
          </div>

          <div style={{ marginTop: 14, display: "grid", gap: 8, color: "var(--ink-mute)" }}>
            <div>
              <b>Model:</b> {pred?.model || "—"}
            </div>
            <div>
              <b>Site:</b> {pred?.site_id || "—"}
            </div>
            <div>
              <b>AI:</b> {pred?.prediction?.label || "—"}{" "}
              {pred ? `(${((pred.prediction.confidence || 0) * 100).toFixed(1)}%)` : ""}
            </div>
          </div>

          <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Link to="/clinical-feedback" className="btn">
              Give feedback
            </Link>
            <Link to="/report" className="btn btnOutline">
              Open report page
            </Link>
          </div>
        </div>

        <div style={{ display: "grid", gap: 14 }}>
          <div className="card">
            <div style={{ fontWeight: 900 }}>Report draft</div>
            <div style={{ marginTop: 8, color: "var(--ink-mute)", fontSize: 13 }}>
              Review the draft text and verify it matches imaging findings and clinical context.
            </div>
            <pre
              style={{
                marginTop: 12,
                whiteSpace: "pre-wrap",
                lineHeight: 1.55,
                background: "rgba(2,6,23,0.03)",
                border: "1px solid var(--line)",
                padding: 12,
                borderRadius: 12,
                minHeight: 180,
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
              }}
            >
              {report?.report_text ||
                "No report draft stored for this case in this session.\n\nTip: generate a report on the Report page; it will appear here automatically."}
            </pre>
            {report?.timestamp ? (
              <div style={{ marginTop: 8, fontSize: 12, color: "var(--ink-mute)" }}>
                Draft generated: {new Date(report.timestamp).toLocaleString()}
              </div>
            ) : null}
          </div>

          <div className="card">
            <div style={{ fontWeight: 900 }}>Sign-off checklist</div>
            <div style={{ marginTop: 10, display: "grid", gap: 10, color: "var(--ink)" }}>
              <label style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <input type="checkbox" checked={check1} onChange={(e) => setCheck1(e.target.checked)} />
                <span>
                  I reviewed the scan quality (artifact/motion/sequence) and confirmed the AI output is used as decision
                  support only.
                </span>
              </label>
              <label style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <input type="checkbox" checked={check2} onChange={(e) => setCheck2(e.target.checked)} />
                <span>I verified the report draft against findings and will edit before finalizing in RIS/PACS.</span>
              </label>
              <label style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <input type="checkbox" checked={check3} onChange={(e) => setCheck3(e.target.checked)} />
                <span>I checked supporting evidence/citations (when available) for traceability.</span>
              </label>
            </div>

            <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button className="btn" type="button" onClick={() => setDrawerOpen(true)}>
                View evidence
              </button>
              <button className="btnPrimary" type="button" disabled={!allChecked} onClick={onMarkReviewed}>
                Sign / Mark reviewed
              </button>
            </div>
          </div>
        </div>
      </div>

      <EvidenceDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={`Case ${studyId}`}
        citations={citations}
      />
    </div>
  );
}

