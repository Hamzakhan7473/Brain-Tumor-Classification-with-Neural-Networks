import React, { useEffect, useState } from "react";
import { formatApiConnectionHint, generateReport, ReportResponse } from "../api/client";
import EvidenceDrawer, { EvidenceCitation } from "../components/EvidenceDrawer";
import { AppPage } from "../components/layout/AppPage";
import { IosButton, IosLinkButton } from "../components/ui/IosButton";

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
  const [savedTimestamp, setSavedTimestamp] = useState<string>("");
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

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
    setSavedTimestamp("");
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
      const ts = new Date().toISOString();
      sessionStorage.setItem(
        "lastReport",
        JSON.stringify({ study_instance_uid: stored.study_instance_uid, report_text: r.report_text, timestamp: ts }),
      );
      setSavedTimestamp(ts);
    } catch (e) {
      const raw = e instanceof Error ? e.message : String(e);
      setError(formatApiConnectionHint(raw));
    } finally {
      setLoading(false);
    }
  }

  const reportCitations: EvidenceCitation[] = [
    {
      id: "rag-clinical-1",
      title: "MRI report template snippet",
      source: "local-templates / brain-mri",
      snippet:
        "Standardized template for brain MRI reports including sections for indication, technique, findings, and impression. The AI draft should follow this structure.",
      score: 0.9,
    },
    {
      id: "rag-guideline-1",
      title: "Glioma imaging guideline",
      source: "guidelines / glioma-imaging",
      snippet:
        "In suspected glioma, MRI with and without contrast is recommended to evaluate tumor extent, edema, and mass effect. Reporting should describe size, location, and involvement of eloquent cortex.",
      score: 0.87,
    },
  ];

  return (
    <AppPage title="Report draft">
      {!stored ? (
        <div className="app-text-muted">
          No prediction found in this session. Go to <a href="/upload">Upload &amp; Predict</a>.
        </div>
      ) : (
        <div className="app-grid-2">
          <div className="card">
            <div className="app-card-title">Structured context</div>
            <div className="app-text-muted" style={{ marginTop: 10, fontSize: 13 }}>
              <div><b>Study UID:</b> {stored.study_instance_uid}</div>
              <div><b>Site ID:</b> {stored.site_id || "—"}</div>
              <div><b>Model:</b> {stored.model}</div>
            </div>
            <div style={{ marginTop: 12 }}>
              <IosLinkButton to={`/reading/${encodeURIComponent(stored.study_instance_uid)}`} variant="ghost">
                Open reading mode
              </IosLinkButton>
            </div>
            <div style={{ marginTop: 18 }}>
              <IosButton variant="primary" fullWidth loading={loading} disabled={loading} onClick={() => void onGenerate()}>
                {loading ? "Generating..." : "Generate report (LLM)"}
              </IosButton>
            </div>
            {error ? <div className="app-text-error" style={{ marginTop: 12, fontWeight: 600, whiteSpace: "pre-wrap" }}>{error}</div> : null}
            {savedTimestamp ? (
              <div className="app-text-muted" style={{ marginTop: 10, fontSize: 12 }}>
                Saved to reading mode: {new Date(savedTimestamp).toLocaleString()}
              </div>
            ) : null}
          </div>

          <div className="card">
            <div className="app-card-title">LLM report (review &amp; sign)</div>
            <div className="app-text-muted" style={{ marginTop: 10, fontSize: 13 }}>
              {report
                ? "Review the grounded report text below. In a clinical deployment this would be signed off inside the RIS/PACS."
                : "Click generate to draft a grounded report via the backend."}
            </div>
            <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <IosButton variant="secondary" size="sm" onClick={() => setDrawerOpen(true)}>
                View evidence
              </IosButton>
              <IosLinkButton to={`/reading/${encodeURIComponent(stored.study_instance_uid)}`} variant="ghost" size="sm">
                Open reading mode
              </IosLinkButton>
            </div>
            {report ? (
              <pre className="app-report-pre">{report.report_text}</pre>
            ) : null}
          </div>
        </div>
      )}

      <EvidenceDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Report evidence" citations={reportCitations} />
    </AppPage>
  );
}
