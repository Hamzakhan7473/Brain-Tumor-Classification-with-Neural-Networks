/**
 * Upload page surfaces: --surface page bg, --green-600 interactive emphasis, disclaimers mixed from --green-*,
 * text --ink-* / muted; borders --line / green-600 translucency.
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { formatApiConnectionHint, predictScan, PredictResponse } from "../api/client";
import ClinicalContextForm, {
  clinicalContextToApiJson,
  emptyClinicalContext,
  isClinicalContextComplete,
} from "../components/scan/ClinicalContextForm";
import FindingsCard from "../components/scan/FindingsCard";
import MilestoneStepper from "../components/scan/MilestoneStepper";
import ModelSelector from "../components/scan/ModelSelector";
import ScanViewport from "../components/scan/ScanViewport";
import { IosButton } from "../components/ui/IosButton";
import { useScanSimulation, type ScanStartOptions } from "../hooks/useScanSimulation";
import type { ClinicalContextPayload } from "../types/scan";
import { predictApiDisplayBase } from "../lib/api";

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
  const inputRef = useRef<HTMLInputElement>(null);

  const apiKey =
    (import.meta.env.VITE_API_KEY as string | undefined)?.trim() ||
    (typeof window !== "undefined" ? window.localStorage.getItem("api_key") ?? undefined : undefined);

  const { state: scanState, startScan, reset } = useScanSimulation(apiKey);

  const [file, setFile] = useState<File | null>(null);
  const [filename, setFilename] = useState<string>("");

  const [model, setModel] = useState<string>("custom_cnn");
  const [siteId, setSiteId] = useState<string>("");
  const [studyUid, setStudyUid] = useState<string>(() =>
    crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
  );
  const [shadowMode, setShadowMode] = useState<boolean>(false);
  const [clinical, setClinical] = useState<ClinicalContextPayload>(() => emptyClinicalContext());
  const [uploadGateHint, setUploadGateHint] = useState<string>("");

  const [loading, setLoading] = useState(false);
  const [runError, setRunError] = useState<string>("");
  const [result, setResult] = useState<PredictResponse | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");

  const classes = useMemo(() => ["glioma", "meningioma", "pituitary", "notumor"], []);

  const is3dPipeline = model === "unet_3d_wmh";

  const acceptAttr = useMemo(
    () =>
      is3dPipeline
        ? ".nii,.nii.gz,application/octet-stream,application/gzip"
        : ".jpg,.jpeg,.png,.dcm,.dicom,image/*",
    [is3dPipeline],
  );

  const clinicalComplete = useMemo(() => isClinicalContextComplete(clinical), [clinical]);

  const scanOpts = useMemo(
    (): ScanStartOptions => ({
      study_instance_uid: studyUid || undefined,
      site_id: siteId || undefined,
      shadow_mode: shadowMode,
      clinicalContext: clinicalComplete ? clinicalContextToApiJson(clinical) : undefined,
    }),
    [studyUid, siteId, shadowMode, clinical, clinicalComplete],
  );

  const findingsVisible =
    scanState.phase === "complete" &&
    scanState.findings !== null &&
    scanState.error === null;

  const displayPreview = previewUrl || "";

  useEffect(() => {
    document.body.style.overscrollBehavior = "none";
    return () => {
      document.body.style.overscrollBehavior = "";
    };
  }, []);

  async function onRun() {
    if (!file) return;
    setLoading(true);
    setRunError("");
    setResult(null);

    try {
      const raw = sessionStorage.getItem("lastPrediction");
      if (raw && scanState.phase === "complete" && scanState.findings && !scanState.findings.isSimulated) {
        try {
          type Stored = {
            scanBase64?: string;
            filename?: string;
            prediction?: PredictResponse;
          };
          const stored = JSON.parse(raw) as Stored;
          if (stored.filename === filename && stored.prediction && stored.scanBase64) {
            setResult(stored.prediction);
            setPreviewUrl(stored.scanBase64);
            navigate("/report");
            return;
          }
        } catch {
          /* predict fresh */
        }
      }

      const r = await predictScan({
        file,
        model,
        site_id: siteId || undefined,
        study_instance_uid: studyUid || undefined,
        shadow_mode: shadowMode,
        context: clinicalComplete ? clinicalContextToApiJson(clinical) : undefined,
      });
      setResult(r);

      const b64 = await fileToBase64(file);
      const stored = {
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
      setRunError(formatApiConnectionHint(e instanceof Error ? e.message : String(e)));
    } finally {
      setLoading(false);
    }
  }

  function handleTryAgain() {
    reset();
    setFile(null);
    setFilename("");
    setRunError("");
    setResult(null);
    setPreviewUrl("");
    setUploadGateHint("");
    if (inputRef.current) inputRef.current.value = "";
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!clinicalComplete) {
      setUploadGateHint("Complete clinical context before attaching imaging.");
      e.target.value = "";
      return;
    }
    setUploadGateHint("");
    reset();
    setFile(f);
    setFilename(f.name || "");
    setPreviewUrl("");
    setResult(null);
    setRunError("");
    void startScan(f, model, scanOpts);
  }

  function handleScanAnother() {
    reset();
    setFile(null);
    setFilename("");
    setRunError("");
    setResult(null);
    setPreviewUrl("");
    setUploadGateHint("");
    if (inputRef.current) inputRef.current.value = "";
  }

  function handleSelectModel(next: string) {
    if (next === model) return;
    setModel(next);
    if (!file) return;
    if (!clinicalComplete) return;
    reset();
    void startScan(file, next, scanOpts);
  }

  function focusFileInput() {
    if (!clinicalComplete) {
      setUploadGateHint("Complete clinical context before attaching imaging.");
      return;
    }
    setUploadGateHint("");
    inputRef.current?.click();
  }

  const showAuxReset = scanState.phase === "complete" || scanState.phase === "error";

  const studyBannerLine = useMemo(() => {
    const now = new Date();
    const y = now.getFullYear();
    const compact = studyUid.replace(/-/g, "").slice(0, 5).toUpperCase().padEnd(5, "0");
    const acq = now.toLocaleString(undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    return `Study NS-${y}-${compact} · acquired ${acq} · model ${model} v1`;
  }, [studyUid, model]);

  return (
    <div className="upload-ios-shell upload-ios-shell-bg font-ios pb-safe">
      <div className="upload-ios-inline-pad-x" style={{ paddingTop: 16, paddingBottom: 8 }}>
        <h2 className="text-ios-title3 font-semibold font-ios text-ns-val-strong" style={{ marginTop: 0 }}>
          Upload &amp; Predict
        </h2>
        <p className="text-ios-footnote font-ios text-ns-muted" style={{ marginTop: 4, marginBottom: 8 }}>
          1. Capture clinical context · 2. Choose modality &amp; imaging · 3. Operational metadata · 4. Inference &amp; review.
        </p>

        <p
          className="text-ios-caption1 font-ios"
          style={{
            marginTop: 0,
            marginBottom: 12,
            fontFamily: "Menlo, ui-monospace, SFMono-Regular, monospace",
            color: "var(--ink-soft)",
          }}
        >
          {studyBannerLine}
        </p>

        <div
          className="ns-card-frame ns-bg-card-solid rounded-ios-lg ios-soft-shadow ios-pad-card text-ios-caption1 font-ios"
          style={{ marginBottom: 14, borderColor: "color-mix(in srgb, var(--green-600) 15%, transparent)" }}
          role="note"
          aria-label="NeuroSight intended use"
        >
          <div className="text-ios-footnote font-semibold font-ios text-ns-heading" style={{ marginBottom: 6 }}>
            Intended use · regulatory honesty
          </div>
          <p className="text-ios-caption2 font-ios text-ns-muted" style={{ margin: 0, lineHeight: 1.46 }}>
            NeuroSight assists radiologists in research and teaching workflows — it{" "}
            <strong style={{ fontWeight: 650 }}>does not replace</strong> attending interpretation. Structured output
            needs explicit physician sign-off. <strong style={{ fontWeight: 650 }}>Not FDA-cleared.</strong>
          </p>
          <p className="text-ios-caption2 font-ios text-ns-muted" style={{ margin: "10px 0 0", lineHeight: 1.46 }}>
            Performance for this deployment is <strong style={{ fontWeight: 650 }}>not characterized</strong> for
            regulatory labeling; retrospective metrics (tumor model sensitivity/specificity, WMH Dice) are withheld until
            the evaluation packet is finalized. Do not utilize for bedside triage decisions.
          </p>
        </div>

        <ClinicalContextForm value={clinical} onChange={setClinical} />

        <div className="ios-disclaimer" role="note" aria-live="polite">
          <div
            aria-hidden
            style={{
              width: 22,
              height: 22,
              borderRadius: 6,
              flexShrink: 0,
              background: "color-mix(in srgb, var(--green-600) 12%, transparent)",
              display: "grid",
              placeItems: "center",
              marginTop: 2,
              color: "var(--green-700)",
              fontWeight: 800,
              fontSize: 12,
              fontFamily: "system-ui, sans-serif",
            }}
          >
            !
          </div>
          <p className="text-ios-caption2 font-ios text-ns-muted" style={{ margin: 0, lineHeight: 1.45 }}>
            <span className="text-ns-warning-em">Research tool only.</span> This interface does not diagnose or treat disease.
            Outputs are illustrative and must not substitute clinical judgment.
          </p>
        </div>

        {scanState.phase === "error" && scanState.error ? (
          <div
            className="ns-card-frame ns-bg-card-solid rounded-ios-lg ios-pad-card"
            style={{
              marginBottom: 12,
              borderColor: "color-mix(in srgb, var(--green-900) 18%, transparent)",
            }}
          >
            <div className="text-ios-footnote font-semibold font-ios text-ns-val-danger" style={{ marginBottom: 10 }}>
              {scanState.error}
            </div>
            <IosButton variant="secondary" size="md" onClick={handleTryAgain}>
              Try again
            </IosButton>
          </div>
        ) : null}

        <div className="upload-ios-grid">
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <ModelSelector value={model} onChange={handleSelectModel} apiKey={apiKey} />

            {uploadGateHint ? (
              <div className="text-ios-caption2 font-ios text-ns-val-danger" style={{ marginTop: -4 }}>
                {uploadGateHint}
              </div>
            ) : null}

            <div className="ns-card-frame ns-bg-card-solid rounded-ios-lg ios-soft-shadow ios-pad-card">
              <div className="text-ios-footnote font-semibold font-ios text-ns-heading" style={{ marginBottom: 8 }}>
                Step 2 · Source
              </div>
              <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
                <IosButton variant="secondary" size="sm" onClick={focusFileInput}>
                  Camera / Photos
                </IosButton>
                <IosButton variant="secondary" size="sm" onClick={focusFileInput}>
                  Files app / Finder
                </IosButton>
                <IosButton variant="secondary" size="sm" onClick={focusFileInput}>
                  {is3dPipeline ? "NIfTI volume" : "DICOM slice"}
                </IosButton>
              </div>

              <input
                ref={inputRef}
                type="file"
                accept={acceptAttr}
                capture={is3dPipeline ? undefined : "environment"}
                className="visually-hidden-ios"
                aria-label="MRI file upload"
                onChange={handleFileChange}
              />

              <div
                className="upload-zone-ios"
                role="button"
                tabIndex={0}
                aria-label="Choose MRI file from device"
                onClick={() => focusFileInput()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    focusFileInput();
                  }
                }}
              >
                <div className="upload-zone-icon-wrap" aria-hidden>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M12 5v14M5 12h14"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                  </svg>
                </div>
                <div className="text-ios-subhead font-semibold font-ios text-ns-val-strong" style={{ marginBottom: 4 }}>
                  Add scan
                </div>
                <div className="text-ios-caption1 font-ios text-ns-muted" style={{ marginBottom: 10 }}>
                  {file ? filename : "Tap to browse or use the shortcuts above."}
                </div>
                {is3dPipeline ? (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, justifyContent: "center" }}>
                    <span className="ios-format-badge font-ios">NIfTI .nii</span>
                    <span className="ios-format-badge font-ios">gzip .gz</span>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, justifyContent: "center" }}>
                    <span className="ios-format-badge font-ios">JPG PNG</span>
                    <span className="ios-format-badge font-ios">DCM single slice</span>
                  </div>
                )}
              </div>

              <p className="text-ios-caption2 font-ios text-ns-muted" style={{ marginTop: 12 }}>
                {is3dPipeline
                  ? "WMH segmentation expects a FLAIR-space NIfTI volume (.nii / .nii.gz)."
                  : "Works with camera photos, Files app uploads, and DICOM slices (single-frame)."}
              </p>

              <div style={{ height: 4 }} />

              <div className="text-ios-footnote font-semibold font-ios text-ns-heading" style={{ marginBottom: 8 }}>
                Step 3 · Operational metadata
              </div>

              <label htmlFor="site-id-input" className="text-ios-footnote font-semibold font-ios text-ns-heading" style={{ display: "block", marginBottom: 6 }}>
                Site ID (optional)
              </label>
              <input
                id="site-id-input"
                className="ios-input-row font-ios"
                value={siteId}
                onChange={(e) => setSiteId(e.target.value)}
                placeholder="e.g. site-001"
              />

              <div style={{ height: 10 }} />

              <label htmlFor="study-uid-input" className="text-ios-footnote font-semibold font-ios text-ns-heading" style={{ display: "block", marginBottom: 6 }}>
                Study / case UID
              </label>
              <input
                id="study-uid-input"
                className="ios-input-row font-ios"
                value={studyUid}
                onChange={(e) => setStudyUid(e.target.value)}
              />

              <div style={{ height: 10 }} />

              <label className="font-ios text-ios-footnote font-semibold" style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", minHeight: 44 }}>
                <input type="checkbox" checked={shadowMode} onChange={(e) => setShadowMode(e.target.checked)} />
                <span style={{ fontWeight: 600, color: "var(--ink-mid)" }}>Shadow mode</span>
              </label>

              <div style={{ height: 14 }} />

              <div className="text-ios-footnote font-semibold font-ios text-ns-heading" style={{ marginBottom: 6 }}>
                Step 4 · Review &amp; run
              </div>
              <IosButton size="lg" variant="primary" fullWidth loading={loading} disabled={!file} onClick={() => void onRun()}>
                {loading ? "Running…" : "Run inference"}
              </IosButton>

              {showAuxReset ? (
                <div style={{ marginTop: 10 }}>
                  <IosButton variant="secondary" fullWidth size="md" onClick={handleScanAnother}>
                    Scan another file
                  </IosButton>
                </div>
              ) : null}

              {runError ? (
                <div className="text-ios-footnote font-semibold font-ios text-ns-val-danger" style={{ marginTop: 12, whiteSpace: "pre-wrap" }}>
                  {runError}
                </div>
              ) : null}
            </div>

            <ScanViewport
              phase={scanState.phase}
              file={file}
              sliceIndex={scanState.sliceIndex}
              snrValue={scanState.snrValue}
              progressPct={scanState.progressPct}
              findings={scanState.findings}
              isSegmentationModel={model === "unet_3d_wmh"}
            />
          </div>

          <aside className="upload-ios-sidebar" aria-label="Scan pipeline">
            <MilestoneStepper steps={scanState.steps} is3D={is3dPipeline} />
            <FindingsCard
              findings={scanState.findings}
              visible={findingsVisible}
              phase={scanState.phase}
              apiError={scanState.apiError ?? scanState.error}
              apiBaseDisplay={predictApiDisplayBase()}
              onInferenceRetry={handleScanAnother}
              file={file}
              model={model}
              studyUid={studyUid}
              siteId={siteId}
              shadowMode={shadowMode}
              apiKey={apiKey}
            />
          </aside>
        </div>

        <div className="ns-card-frame ns-bg-card-solid ios-soft-shadow rounded-ios-lg ios-pad-card font-ios" style={{ marginTop: 16 }}>
          <div className="text-ios-subhead font-semibold font-ios text-ns-val-strong" style={{ marginBottom: 4 }}>
            Result view
          </div>
          {!result ? (
            <div className="text-ios-footnote font-ios text-ns-muted">
              Upload a file to run inference, or finish a scan above to hydrate this panel after “Run inference”.
            </div>
          ) : (
            <>
              <div className="text-ios-title3 font-bold font-ios text-ns-val-strong" style={{ marginTop: 4 }}>
                {result.label}{" "}
                <span className="text-ios-subhead font-semibold font-ios text-ns-muted">
                  ({(result.confidence * 100).toFixed(1)}%)
                </span>
              </div>
              <div style={{ marginTop: 14 }}>
                <div className="text-ios-footnote font-semibold font-ios text-ns-heading" style={{ marginBottom: 8 }}>
                  Confidence bars
                </div>
                <div>
                  {classes.map((c) => {
                    const v = result.probabilities?.[c] ?? 0;
                    const pct = `${(v * 100).toFixed(1)}%`;
                    const isPrimary = c === result.label;
                    const track = "color-mix(in srgb, var(--line) 88%, transparent)";
                    const inactiveFill = "color-mix(in srgb, var(--ink-mute) 42%, var(--line))";
                    return (
                      <div key={c} style={{ marginBottom: 8 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                          <span className="text-ios-caption2 font-ios text-ns-muted">{c}</span>
                          <span className={`text-ios-footnote font-semibold font-ios ${isPrimary ? "text-ns-val-ok" : "text-ns-val-strong"}`}>
                            {pct}
                          </span>
                        </div>
                        <div
                          style={{
                            position: "relative",
                            height: 8,
                            borderRadius: 999,
                            background: track,
                            overflow: "hidden",
                          }}
                        >
                          <div
                            style={{
                              position: "absolute",
                              inset: 0,
                              width: `${Math.max(2, v * 100)}%`,
                              background: isPrimary ? "var(--green-600)" : inactiveFill,
                              transition: "width 0.3s var(--ease-ios-ease)",
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {displayPreview ? (
                <div style={{ marginTop: 16 }}>
                  <div className="text-ios-footnote font-semibold font-ios text-ns-heading" style={{ marginBottom: 6 }}>
                    Uploaded preview
                  </div>
                  <div
                    style={{
                      position: "relative",
                      width: "100%",
                      paddingBottom: "56.25%",
                      borderRadius: "var(--radius-ios-lg)",
                      overflow: "hidden",
                      border: "1px solid var(--line)",
                    }}
                  >
                    <img
                      src={displayPreview}
                      alt="Uploaded scan"
                      style={{
                        position: "absolute",
                        inset: 0,
                        width: "100%",
                        height: "100%",
                        objectFit: "contain",
                        background: "var(--surface)",
                      }}
                    />
                  </div>
                </div>
              ) : null}

              <div style={{ marginTop: 18 }}>
                <IosButton variant="ghost" size="md" onClick={() => navigate("/clinical-feedback")}>
                  Go to feedback
                </IosButton>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
