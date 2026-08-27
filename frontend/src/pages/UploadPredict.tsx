/**
 * Upload & Predict — clinical context → model → imaging → inference pipeline.
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
import { GlassTilePanel } from "../components/ui/GlassTilePanel";
import { IosButton } from "../components/ui/IosButton";
import { IosSymbol } from "../components/ui/IosSymbol";
import { useScanSimulation, type ScanStartOptions } from "../hooks/useScanSimulation";
import type { ClinicalContextPayload } from "../types/scan";
import { predictApiDisplayBase } from "../lib/api";
import "./UploadPredict.css";

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.onload = () => resolve(String(reader.result || ""));
    reader.readAsDataURL(file);
  });
}

type ConfidenceBarsProps = {
  result: PredictResponse;
  classes: string[];
};

function ConfidenceBars({ result, classes }: ConfidenceBarsProps) {
  return (
    <div className="upload-confidence">
      <div className="upload-confidence__heading">Confidence bars</div>
      <div>
        {classes.map((c) => {
          const v = result.probabilities?.[c] ?? 0;
          const pct = `${(v * 100).toFixed(1)}%`;
          const isPrimary = c === result.label;
          return (
            <div key={c} className="upload-confidence-row">
              <div className="upload-confidence-row__head">
                <span className="upload-confidence-row__label">{c}</span>
                <span
                  className={`upload-confidence-row__value ${isPrimary ? "upload-confidence-row__value--primary" : ""}`}
                >
                  {pct}
                </span>
              </div>
              <div className="upload-confidence-track">
                <div
                  className={`upload-confidence-fill ${isPrimary ? "upload-confidence-fill--primary" : ""}`}
                  style={{ width: `${Math.max(2, v * 100)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
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

  const sourceTiles = useMemo(
    () => [
      { label: "Camera", symbol: "camera" as const, onClick: focusFileInput, tint: "cyan" as const },
      { label: "Files", symbol: "folder" as const, onClick: focusFileInput, tint: "teal" as const },
      {
        label: is3dPipeline ? "NIfTI" : "DICOM",
        symbol: "cube" as const,
        onClick: focusFileInput,
        tint: "indigo" as const,
      },
    ],
    [is3dPipeline],
  );

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
    <div className="upload-page pb-safe">
      <div className="upload-inner">
        <header className="upload-header">
          <h1>Upload &amp; Predict</h1>
          <p>
            Capture clinical context, choose a model, attach imaging, then run inference and review findings.
          </p>
          <p className="upload-study-banner">{studyBannerLine}</p>
        </header>

        <div
          className="upload-card upload-notice ios-pad-card"
          role="note"
          aria-label="NeuroSight intended use"
        >
          <div className="upload-notice__title">Intended use · regulatory honesty</div>
          <p className="upload-notice__body">
            NeuroSight assists radiologists in research and teaching workflows — it{" "}
            <strong>does not replace</strong> attending interpretation. Structured output needs explicit
            physician sign-off. <strong>Not FDA-cleared.</strong>
          </p>
          <p className="upload-notice__body">
            Performance for this deployment is <strong>not characterized</strong> for regulatory labeling;
            retrospective metrics (tumor model sensitivity/specificity, WMH Dice) are withheld until the
            evaluation packet is finalized. Do not utilize for bedside triage decisions.
          </p>
        </div>

        <ClinicalContextForm value={clinical} onChange={setClinical} />

        <div className="upload-disclaimer" role="note" aria-live="polite">
          <div className="upload-disclaimer__icon" aria-hidden>
            !
          </div>
          <p>
            <span className="upload-disclaimer__warn">Research tool only.</span> This interface does not
            diagnose or treat disease. Outputs are illustrative and must not substitute clinical judgment.
          </p>
        </div>

        {scanState.phase === "error" && scanState.error ? (
          <div className="upload-card upload-error-banner ios-pad-card">
            <div className="upload-error-banner__title">{scanState.error}</div>
            <IosButton variant="secondary" size="md" onClick={handleTryAgain}>
              Try again
            </IosButton>
          </div>
        ) : null}

        <div className="upload-grid">
          <div className="upload-main">
            <ModelSelector value={model} onChange={handleSelectModel} apiKey={apiKey} />

            {uploadGateHint ? <div className="upload-gate-hint">{uploadGateHint}</div> : null}

            <div className="upload-card ios-pad-card">
              <div className="upload-section-title">Step 2 · Source</div>
              <GlassTilePanel variant="inline" aria-label="Source shortcuts" tiles={sourceTiles} />

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
                  <IosSymbol name="arrow.up.doc" size={20} strokeWidth={2} />
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

              <div className="upload-meta-block" style={{ marginTop: 16 }}>
                <div className="upload-section-title">Step 3 · Operational metadata</div>

                <label htmlFor="site-id-input">Site ID (optional)</label>
                <input
                  id="site-id-input"
                  className="ios-input-row font-ios"
                  value={siteId}
                  onChange={(e) => setSiteId(e.target.value)}
                  placeholder="e.g. site-001"
                />
              </div>

              <div className="upload-meta-block">
                <label htmlFor="study-uid-input">Study / case UID</label>
                <input
                  id="study-uid-input"
                  className="ios-input-row font-ios"
                  value={studyUid}
                  onChange={(e) => setStudyUid(e.target.value)}
                />
              </div>

              <label className="upload-checkbox-row">
                <input type="checkbox" checked={shadowMode} onChange={(e) => setShadowMode(e.target.checked)} />
                <span>Shadow mode</span>
              </label>

              <div className="upload-run-block">
                <div className="upload-section-title">Step 4 · Review &amp; run</div>
                <IosButton
                  size="lg"
                  variant="primary"
                  fullWidth
                  loading={loading}
                  disabled={!file}
                  onClick={() => void onRun()}
                >
                  {loading ? "Running…" : "Run inference"}
                </IosButton>

                {showAuxReset ? (
                  <div style={{ marginTop: 10 }}>
                    <IosButton variant="secondary" fullWidth size="md" onClick={handleScanAnother}>
                      Scan another file
                    </IosButton>
                  </div>
                ) : null}

                {runError ? <div className="upload-run-error">{runError}</div> : null}
              </div>
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

          <aside className="upload-sidebar" aria-label="Scan pipeline">
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

        <div className="upload-card upload-result ios-pad-card">
          <div className="upload-result__title">Result view</div>
          {!result ? (
            <div className="upload-result__empty">
              Upload a file to run inference, or finish a scan above to hydrate this panel after “Run inference”.
            </div>
          ) : (
            <>
              <div className="upload-result__label">
                {result.label}{" "}
                <span className="upload-result__confidence">({(result.confidence * 100).toFixed(1)}%)</span>
              </div>

              <ConfidenceBars result={result} classes={classes} />

              {displayPreview ? (
                <div className="upload-preview">
                  <div className="upload-preview__heading">Uploaded preview</div>
                  <div className="upload-preview__frame">
                    <img src={displayPreview} alt="Uploaded scan" />
                  </div>
                </div>
              ) : null}

              <div className="upload-result__actions">
                <IosButton
                  variant="ghost"
                  size="md"
                  onClick={() => navigate(`/clinical-feedback?caseId=${encodeURIComponent(studyUid)}`)}
                >
                  Submit feedback
                </IosButton>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
