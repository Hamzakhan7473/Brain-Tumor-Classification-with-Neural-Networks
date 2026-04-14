import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { formatApiConnectionHint, predictScan, PredictResponse } from "../api/client";

type StoredPrediction = {
  scanBase64: string;
  filename: string;
  model: string;
  study_instance_uid: string;
  site_id?: string;
  shadow_mode: boolean;
  prediction: PredictResponse;
};

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.onload = () => resolve(String(reader.result || ""));
    reader.readAsDataURL(file);
  });
}

export default function UploadPredict() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [filename, setFilename] = useState<string>("");

  const [model, setModel] = useState<string>("custom_cnn");
  const [siteId, setSiteId] = useState<string>("");
  const [studyUid, setStudyUid] = useState<string>(() => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())));
  const [shadowMode, setShadowMode] = useState<boolean>(true);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [result, setResult] = useState<PredictResponse | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");

  const classes = useMemo(
    () => ["glioma", "meningioma", "pituitary", "notumor"],
    []
  );

  async function onRun() {
    if (!file) return;
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const r = await predictScan({
        file,
        model,
        site_id: siteId || undefined,
        study_instance_uid: studyUid || undefined,
        shadow_mode: shadowMode,
      });
      setResult(r);

      const b64 = await fileToBase64(file);
      const stored: StoredPrediction = {
        scanBase64: b64,
        filename,
        model,
        study_instance_uid: studyUid,
        site_id: siteId || undefined,
        shadow_mode: shadowMode,
        prediction: r,
      };
      sessionStorage.setItem("lastPrediction", JSON.stringify(stored));
      setPreviewUrl(b64);
      navigate("/report");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Upload &amp; Predict</h2>
      <p style={{ color: "var(--ink-mute)", fontSize: 13, marginTop: 4, marginBottom: 8 }}>
        1. Choose source &amp; file · 2. Attach metadata · 3. Run inference and review result.
      </p>
      <div className="grid2" style={{ marginTop: 14 }}>
        <div className="card">
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-mute)", marginBottom: 6 }}>Step 1 · Source</div>
          <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn"
              onClick={() => document.getElementById("file-input")?.click()}
            >
              Camera / Photos
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => document.getElementById("file-input")?.click()}
            >
              Files app / Finder
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => document.getElementById("file-input")?.click()}
            >
              DICOM slice
            </button>
          </div>
          <label style={{ display: "block", marginBottom: 8, fontWeight: 600 }}>MRI file</label>
          <input
            id="file-input"
            type="file"
            accept=".jpg,.jpeg,.png,.dcm,.dicom,image/*"
            capture="environment"
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              setFile(f);
              setFilename(f?.name || "");
              setPreviewUrl("");
            }}
          />

          <div style={{ height: 12 }} />

          <p style={{ fontSize: 12, color: "var(--ink-mute)", marginTop: 6 }}>
            Works with camera photos, Files app uploads, and DICOM slices (single-frame).
          </p>

          <div style={{ height: 12 }} />

          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-mute)", marginBottom: 6 }}>Step 2 · Metadata</div>
          <label style={{ display: "block", marginBottom: 8, fontWeight: 600 }}>Model</label>
          <select value={model} onChange={(e) => setModel(e.target.value)} style={{ width: "100%", padding: 10 }}>
            <option value="custom_cnn">custom_cnn</option>
            <option value="xception">xception</option>
            <option value="transfer">transfer</option>
          </select>

          <div style={{ height: 12 }} />

          <label style={{ display: "block", marginBottom: 8, fontWeight: 600 }}>Site ID (optional)</label>
          <input value={siteId} onChange={(e) => setSiteId(e.target.value)} placeholder="e.g. site-001" style={{ width: "100%", padding: 10 }} />

          <div style={{ height: 12 }} />

          <label style={{ display: "block", marginBottom: 8, fontWeight: 600 }}>Study / case UID</label>
          <input value={studyUid} onChange={(e) => setStudyUid(e.target.value)} style={{ width: "100%", padding: 10 }} />

          <div style={{ height: 12 }} />

          <label style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <input type="checkbox" checked={shadowMode} onChange={(e) => setShadowMode(e.target.checked)} />
            <span style={{ fontWeight: 600 }}>Shadow mode</span>
          </label>

          <div style={{ height: 16 }} />

          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-mute)", marginBottom: 6 }}>Step 3 · Run</div>
          <button
            className="btnPrimary"
            disabled={!file || loading}
            onClick={onRun}
            style={{ width: "100%", padding: "12px 18px" }}
          >
            {loading ? "Running..." : "Run inference"}
          </button>

          {error ? (
            <div style={{ marginTop: 12, color: "crimson", fontWeight: 600, whiteSpace: "pre-wrap" }}>{error}</div>
          ) : null}
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0, marginBottom: 4 }}>Result view</h3>
          {!result ? (
            <div style={{ color: "var(--ink-mute)" }}>Upload a file and run inference to see results.</div>
          ) : (
            <>
              <div style={{ fontSize: 22, fontWeight: 800 }}>
                {result.label} ({(result.confidence * 100).toFixed(1)}%)
              </div>
              <div style={{ marginTop: 14 }}>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>Confidence bars</div>
                <div>
                  {classes.map((c) => {
                    const v = result.probabilities?.[c] ?? 0;
                    const pct = `${(v * 100).toFixed(1)}%`;
                    const isPrimary = c === result.label;
                    return (
                      <div key={c} style={{ marginBottom: 6 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                          <span style={{ color: "var(--ink-mute)", fontSize: 12 }}>{c}</span>
                          <span style={{ fontWeight: 600, fontSize: 12 }}>{pct}</span>
                        </div>
                        <div
                          style={{
                            position: "relative",
                            height: 8,
                            borderRadius: 999,
                            background: "rgba(148, 163, 184, 0.25)",
                            overflow: "hidden",
                          }}
                        >
                          <div
                            style={{
                              position: "absolute",
                              inset: 0,
                              width: `${Math.max(2, v * 100)}%`,
                              background: isPrimary ? "var(--green-600)" : "rgba(148, 163, 184, 0.8)",
                              transition: "width 0.3s ease",
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {previewUrl && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontWeight: 700, marginBottom: 6 }}>Saliency viewer (shell)</div>
                  <div
                    style={{
                      position: "relative",
                      borderRadius: 16,
                      overflow: "hidden",
                      border: "1px solid rgba(15, 23, 42, 0.06)",
                    }}
                  >
                    <img src={previewUrl} alt="Uploaded scan" style={{ width: "100%", display: "block" }} />
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
                    Web saliency overlay shell. For full interpretability (pinch-to-zoom, model-specific maps), use the
                    Python viewer; this screen will be wired to a saliency endpoint next.
                  </p>
                </div>
              )}

              <div style={{ marginTop: 18 }}>
                <button className="btn btnOutline" onClick={() => navigate("/clinical-feedback")}>
                  Go to feedback
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

