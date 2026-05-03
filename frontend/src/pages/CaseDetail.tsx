import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getCase } from "../api/client";
import { fetchShadowConfig, submitShadowFeedback } from "../lib/api";
import ShadowModeBanner from "../components/shadow/ShadowModeBanner";
import { IosButton } from "../components/ui/IosButton";

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
  metrics?: Record<string, unknown> | null;
};

export default function CaseDetail() {
  const { studyId } = useParams<{ studyId: string }>();
  const [stored, setStored] = useState<StoredPrediction | null>(null);
  const [apiLoaded, setApiLoaded] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [fromShadow, setFromShadow] = useState(false);
  const [shadowCase, setShadowCase] = useState<Record<string, unknown> | null>(null);
  const [classes, setClasses] = useState<string[]>([]);
  const [fbChoice, setFbChoice] = useState<"none" | "agree" | "disagree" | "partial">("none");
  const [correctedClass, setCorrectedClass] = useState<string>("");
  const [notes, setNotes] = useState("");
  const [fbBusy, setFbBusy] = useState(false);
  const [fbOk, setFbOk] = useState(false);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setError("");
      if (!studyId) return;
      try {
        const [payload, cfg] = await Promise.all([getCase(studyId), fetchShadowConfig().catch(() => null)]);
        if (!mounted) return;
        if (cfg?.classes) setClasses(cfg.classes);
        const inf = payload?.inference || {};
        const sh = Boolean(payload?.from_shadow_queue);
        setFromShadow(sh);
        setShadowCase(sh ? ((payload as { shadow_case?: Record<string, unknown> }).shadow_case ?? null) : null);

        let scanBase64 = "";
        const raw = sessionStorage.getItem("lastPrediction");
        if (raw) {
          try {
            const parsed = JSON.parse(raw) as StoredPrediction;
            if (parsed.study_instance_uid === studyId) scanBase64 = parsed.scanBase64;
          } catch {
            // ignore
          }
        }
        setStored({
          scanBase64,
          filename: inf.filename || "scan",
          model: inf.model || "custom_cnn",
          study_instance_uid: studyId,
          site_id: inf.site_id || undefined,
          shadow_mode: Boolean(inf.shadow_mode) || sh,
          prediction: {
            label: inf.label || "—",
            confidence: typeof inf.confidence === "number" ? inf.confidence : 0,
          },
          metrics: (inf.metrics as Record<string, unknown> | null) || null,
        });
        setApiLoaded(true);
      } catch (e) {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : String(e));
        setApiLoaded(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [studyId]);

  const submitFb = async (verdict: "agree" | "disagree" | "partial") => {
    if (!studyId) return;
    setFbBusy(true);
    setFbOk(false);
    try {
      const ground =
        verdict === "disagree" && correctedClass
          ? { corrected_class: correctedClass, severity_note: notes.slice(0, 200) }
          : verdict === "disagree"
            ? { notes_only: true }
            : undefined;
      await submitShadowFeedback(studyId, {
        verdict,
        ground_truth: ground,
        notes: notes.slice(0, 500) || undefined,
      });
      setFbOk(true);
      window.setTimeout(() => {
        window.location.href = "/shadow-queue";
      }, 900);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    } finally {
      setFbBusy(false);
    }
  };

  if (!stored) {
    return (
      <div className="container">
        <h2 style={{ marginTop: 16 }}>Case detail</h2>
        {fromShadow ? <ShadowModeBanner /> : null}
        {error ? <p style={{ color: "crimson", marginTop: 8 }}>{error}</p> : null}
        <p style={{ color: "var(--ink-mute)", marginTop: 8 }}>
          If MongoDB is not enabled or this study is not present, upload a scan first from{" "}
          <Link to="/upload" style={{ textDecoration: "underline" }}>
            Upload &amp; Predict
          </Link>{" "}
          or ingest a shadow case via <span style={{ fontFamily: "ui-monospace, monospace" }}>POST /shadow/ingest</span>.
        </p>
      </div>
    );
  }

  return (
    <div className="container">
      {fromShadow ? <ShadowModeBanner /> : null}

      <h2 style={{ marginTop: 16 }}>Case · {stored.study_instance_uid}</h2>
      <p style={{ color: "var(--ink-mute)", marginBottom: 16 }}>
        {apiLoaded
          ? fromShadow
            ? "Shadow queue case — feedback is the primary action; no clinical report is available."
            : "Loaded from MongoDB (image preview uses session cache when available)."
          : "Loading…"}
      </p>

      <div className="grid2">
        <div className="card">
          <div style={{ fontWeight: 800 }}>Scan &amp; saliency preview</div>
          <div style={{ marginTop: 10 }}>
            <div
              style={{
                position: "relative",
                borderRadius: 16,
                overflow: "hidden",
                border: "1px solid rgba(15, 23, 42, 0.06)",
              }}
            >
              {stored.scanBase64 ? (
                <img src={stored.scanBase64} alt="Case scan" style={{ width: "100%", display: "block" }} />
              ) : (
                <div style={{ padding: 18, color: "var(--ink-mute)" }}>
                  Image preview not available (shadow pipeline stores metadata only in pilot). Use PACS viewer for
                  definitive imaging.
                </div>
              )}
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  background:
                    "radial-gradient(circle at 50% 40%, rgba(244, 63, 94, 0.35), transparent 55%), radial-gradient(circle at 30% 70%, rgba(59, 130, 246, 0.3), transparent 55%)",
                  mixBlendMode: "screen",
                  pointerEvents: "none",
                }}
              />
            </div>
            <p style={{ fontSize: 12, color: "var(--ink-mute)", marginTop: 6 }}>
              Saliency overlay is illustrative only. Shadow mode: not for clinical decisions.
            </p>
          </div>
        </div>

        <div className="card">
          <div style={{ fontWeight: 800 }}>AI summary</div>
          <div style={{ marginTop: 10, color: "var(--ink-mute)" }}>
            <div>
              <b>Study UID:</b> {stored.study_instance_uid}
            </div>
            <div>
              <b>Site:</b> {stored.site_id || "—"}
            </div>
            <div>
              <b>Model:</b> {stored.model}
            </div>
            <div>
              <b>AI label:</b> {stored.prediction.label} ({(stored.prediction.confidence * 100).toFixed(1)}%)
            </div>
            {stored.metrics ? (
              <pre style={{ marginTop: 10, fontSize: 11, color: "var(--ink-mid)", whiteSpace: "pre-wrap" }}>
                {JSON.stringify(stored.metrics, null, 2)}
              </pre>
            ) : null}
          </div>

          {!fromShadow ? (
            <div style={{ marginTop: 18, display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Link to="/report" className="btn-large-outline">
                Open report draft
              </Link>
              <Link to={`/reading/${encodeURIComponent(stored.study_instance_uid)}`} className="btn btnOutline">
                Reading mode
              </Link>
              <Link to="/clinical-feedback" className="btn-primary">
                Give feedback
              </Link>
            </div>
          ) : null}

          {fromShadow ? (
            <div style={{ marginTop: 22 }}>
              <div style={{ fontWeight: 900, fontSize: 16, color: "var(--ink)", marginBottom: 10 }}>
                Radiologist feedback (required for shadow QA)
              </div>
              <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 14 }}>
                There is no report to sign in shadow mode. Confirm or disagree with the AI finding for QMS metrics
                only.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <IosButton
                  variant="primary"
                  size="lg"
                  fullWidth
                  loading={fbBusy && fbChoice === "agree"}
                  disabled={fbBusy}
                  onClick={() => {
                    setFbChoice("agree");
                    void submitFb("agree");
                  }}
                >
                  ✓ Confirm finding
                </IosButton>
                <IosButton
                  variant="danger"
                  size="lg"
                  fullWidth
                  loading={fbBusy && fbChoice === "disagree"}
                  disabled={fbBusy}
                  onClick={() => setFbChoice((c) => (c === "disagree" ? "none" : "disagree"))}
                >
                  ✗ Disagree
                </IosButton>
                {fbChoice === "disagree" ? (
                  <div className="card" style={{ padding: 14, background: "var(--surface)" }}>
                    <div style={{ fontWeight: 800, marginBottom: 8 }}>Structured correction</div>
                    <label style={{ fontSize: 13, color: "var(--ink-mid)" }}>Corrected class</label>
                    <select
                      value={correctedClass}
                      onChange={(e) => setCorrectedClass(e.target.value)}
                      style={{ marginTop: 6, width: "100%" }}
                    >
                      <option value="">Select…</option>
                      {classes.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                    <label style={{ fontSize: 13, color: "var(--ink-mid)", marginTop: 10, display: "block" }}>Notes (max 500)</label>
                    <textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} style={{ marginTop: 6, minHeight: 90 }} />
                    <div style={{ marginTop: 12 }}>
                      <IosButton variant="primary" size="md" loading={fbBusy} disabled={fbBusy} onClick={() => void submitFb("disagree")}>
                        Submit disagreement
                      </IosButton>
                    </div>
                  </div>
                ) : null}
                <IosButton
                  variant="secondary"
                  size="lg"
                  fullWidth
                  loading={fbBusy && fbChoice === "partial"}
                  disabled={fbBusy}
                  onClick={() => {
                    setFbChoice("partial");
                    void submitFb("partial");
                  }}
                >
                  ↻ Need more info
                </IosButton>
              </div>
              {fbOk ? (
                <p style={{ marginTop: 12, color: "var(--green-700)", fontWeight: 700 }}>Feedback recorded — returning to queue…</p>
              ) : null}
              {shadowCase ? (
                <p style={{ marginTop: 14, fontSize: 11, color: "var(--ink-mute)", fontFamily: "ui-monospace, monospace" }}>
                  shadow_case_id: {String(shadowCase.id || "")}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
