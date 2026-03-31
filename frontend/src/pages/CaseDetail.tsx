import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
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

export default function CaseDetail() {
  const { studyId } = useParams<{ studyId: string }>();
  const [stored, setStored] = useState<StoredPrediction | null>(null);
  const [apiLoaded, setApiLoaded] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let mounted = true;
    (async () => {
      setError("");
      if (!studyId) return;
      try {
        const payload = await getCase(studyId);
        if (!mounted) return;
        const inf = payload?.inference || {};
        // Backend does not store image bytes; reuse session scan if present.
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
          shadow_mode: Boolean(inf.shadow_mode),
          prediction: {
            label: inf.label || "—",
            confidence: typeof inf.confidence === "number" ? inf.confidence : 0,
          },
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

  if (!stored) {
    return (
      <div className="container">
        <h2 style={{ marginTop: 16 }}>Case detail</h2>
        {error ? <p style={{ color: "crimson", marginTop: 8 }}>{error}</p> : null}
        <p style={{ color: "var(--ink-mute)", marginTop: 8 }}>
          If MongoDB is not enabled or this study is not present, upload a scan first from{" "}
          <Link to="/upload" style={{ textDecoration: "underline" }}>
            Upload &amp; Predict
          </Link>
          .
        </p>
      </div>
    );
  }

  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Case · {stored.study_instance_uid}</h2>
      <p style={{ color: "var(--ink-mute)", marginBottom: 16 }}>
        {apiLoaded
          ? "Loaded from MongoDB (image preview uses session cache when available)."
          : "Session-only view of the latest case."}
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
                  Image preview not available (backend does not store images). Upload again to cache preview in this
                  session.
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
              Saliency overlay is illustrative only. Full interpretability should be done in PACS / dedicated viewer.
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
          </div>

          <div style={{ marginTop: 18, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Link to="/report" className="btn-large-outline">
              Open report draft
            </Link>
            <Link to="/clinical-feedback" className="btn-primary">
              Give feedback
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

