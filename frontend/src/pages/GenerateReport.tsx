import React, { useEffect, useState } from "react";
import { generateReport, ReportResponse } from "../api/client";

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

function dataUrlToFile(dataUrl: string, filename: string, mime = "application/octet-stream"): Promise<File> {
  return new Promise((resolve, reject) => {
    try {
      const [header, b64] = dataUrl.split(",");
      const mimeMatch = header.match(/data:(.*);base64/);
      const realMime = mimeMatch?.[1] || mime;
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const blob = new Blob([bytes], { type: realMime });
      resolve(new File([blob], filename, { type: realMime }));
    } catch (e) {
      reject(e);
    }
  });
}

export default function GenerateReport() {
  const [stored, setStored] = useState<StoredPrediction | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<ReportResponse | null>(null);

  useEffect(() => {
    const raw = sessionStorage.getItem("lastPrediction");
    if (!raw) return;
    try {
      setStored(JSON.parse(raw) as StoredPrediction);
    } catch {
      // ignore
    }
  }, []);

  async function onGenerate() {
    if (!stored) return;
    setLoading(true);
    setError("");
    setReport(null);
    try {
      const file = await dataUrlToFile(stored.scanBase64, stored.filename);
      const r = await generateReport({
        file,
        model: stored.model,
        study_instance_uid: stored.study_instance_uid,
        site_id: stored.site_id,
        shadow_mode: stored.shadow_mode,
      });
      setReport(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Report draft</h2>

      {!stored ? (
        <div style={{ marginTop: 14, color: "var(--muted)" }}>
          No prediction found in this session. Go to <a href="/upload">Upload & Predict</a>.
        </div>
      ) : (
        <div className="grid2" style={{ marginTop: 14 }}>
          <div className="card">
            <div style={{ fontWeight: 800 }}>Structured context</div>
            <div style={{ marginTop: 10, color: "var(--muted)" }}>
              <div><b>Study UID:</b> {stored.study_instance_uid}</div>
              <div><b>Site ID:</b> {stored.site_id || "—"}</div>
              <div><b>Model:</b> {stored.model}</div>
            </div>
            <div style={{ marginTop: 18 }}>
              <button className="btnPrimary" disabled={loading} onClick={onGenerate} style={{ width: "100%", padding: "12px 18px" }}>
                {loading ? "Generating..." : "Generate report (LLM)"}
              </button>
            </div>
            {error ? <div style={{ marginTop: 12, color: "crimson", fontWeight: 600 }}>{error}</div> : null}
          </div>

          <div className="card">
            <div style={{ fontWeight: 800 }}>LLM report (review &amp; sign)</div>
            <div style={{ marginTop: 10, color: "var(--muted)" }}>
              {report
                ? "Review the grounded report text below. In a clinical deployment this would be signed off inside the RIS/PACS."
                : "Click generate to draft a grounded report via the backend."}
            </div>
            {report ? (
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.5,
                  background: "rgba(79,70,229,0.05)",
                  border: "1px solid rgba(79,70,229,0.12)",
                  padding: 14,
                  borderRadius: 12,
                  marginTop: 12,
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                }}
              >
                {report.report_text}
              </pre>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

