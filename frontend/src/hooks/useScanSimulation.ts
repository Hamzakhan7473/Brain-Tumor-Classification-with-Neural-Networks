import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, predict, type PredictBackendResponse } from "../lib/api";
import type { PredictResponse } from "../api/client";
import type {
  ClassProb,
  ScanFindings,
  ScanGuardrailsMeta,
  ScanPhase,
  ScanState,
  ScanStep,
  WMHResult,
} from "../types/scan";

export type { ScanFindings, ScanStep, ScanPhase };
/** Alias used by scan UI components */
export type Phase = ScanPhase;

const STEPS_2D = [
  { id: 0, name: "File validation", subtitle: "Parsing format and headers", dur: 800, endPct: 14 },
  { id: 1, name: "Preprocessing", subtitle: "Resize to match model, div255", dur: 1200, endPct: 30 },
  { id: 2, name: "AI inference", subtitle: "Keras model forward pass", dur: 2500, endPct: 55 },
  { id: 3, name: "Grad-CAM", subtitle: "Saliency map generation", dur: 1400, endPct: 72 },
  { id: 4, name: "Risk grading", subtitle: "Class probability analysis", dur: 900, endPct: 88 },
  { id: 5, name: "Report", subtitle: "Structured output finalize", dur: 1200, endPct: 100 },
];

const STEPS_3D = [
  { id: 0, name: "File validation", subtitle: "Parsing NIfTI volume", dur: 800, endPct: 12 },
  { id: 1, name: "Preprocessing", subtitle: "Resize to 96³, z-score norm", dur: 2000, endPct: 28 },
  { id: 2, name: "3D U-Net inference", subtitle: "Volumetric segmentation", dur: 4000, endPct: 58 },
  { id: 3, name: "WMH quantification", subtitle: "Volume, location, grading", dur: 1800, endPct: 76 },
  { id: 4, name: "Risk stratification", subtitle: "Age-matched percentile", dur: 1000, endPct: 90 },
  { id: 5, name: "Report", subtitle: "Structured output finalize", dur: 1200, endPct: 100 },
];

export type ScanStartOptions = {
  study_instance_uid?: string;
  site_id?: string;
  shadow_mode?: boolean;
  clinicalContext?: Record<string, unknown>;
};

function phaseForStepIndex(i: number, is3d: boolean): ScanPhase {
  if (is3d) {
    const m: ScanPhase[] = [
      "uploading",
      "preprocessing",
      "inferring",
      "grading",
      "grading",
      "reporting",
    ];
    return m[i] ?? "uploading";
  }
  const m2: ScanPhase[] = [
    "uploading",
    "preprocessing",
    "inferring",
    "gradcam",
    "grading",
    "reporting",
  ];
  return m2[i] ?? "uploading";
}

function coerceWmh(raw: unknown): WMHResult | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  const num = (k: string, d: number) => (typeof o[k] === "number" ? o[k] : d);
  const str = (k: string, d: string) => (typeof o[k] === "string" ? o[k] : d);
  const sev = str("severity_grade", "Normal");
  const risk = str("risk_level", "Low");
  const sg: WMHResult["severity_grade"] =
    sev === "Normal" || sev === "Mild" || sev === "Moderate" || sev === "Severe" ? sev : "Normal";
  const rk: WMHResult["risk_level"] =
    risk === "Low" || risk === "Moderate" || risk === "High" || risk === "Very High"
      ? risk
      : "Low";
  const ciRaw = o["volume_cc_ci_95"];
  let volume_cc_ci_95: [number, number] | undefined;
  if (Array.isArray(ciRaw) && ciRaw.length >= 2) {
    const a = Number(ciRaw[0]);
    const b = Number(ciRaw[1]);
    if (!Number.isNaN(a) && !Number.isNaN(b)) volume_cc_ci_95 = [a, b];
  }
  return {
    volume_cc: num("volume_cc", 0),
    volume_cc_ci_95,
    volume_uncertainty_cc:
      typeof o["volume_uncertainty_cc"] === "number" ? (o["volume_uncertainty_cc"] as number) : undefined,
    age_matched_percentile:
      typeof o["age_matched_percentile"] === "number" ? (o["age_matched_percentile"] as number) : undefined,
    percentile_note: typeof o["percentile_note"] === "string" ? (o["percentile_note"] as string) : undefined,
    lesion_voxels: Math.round(num("lesion_voxels", 0)),
    lesion_fraction: num("lesion_fraction", 0),
    mean_lesion_prob: num("mean_lesion_prob", 0),
    peak_lesion_prob: num("peak_lesion_prob", 0),
    severity_grade: sg,
    risk_level: rk,
    threshold_used: num("threshold_used", 0.5),
    note: str("note", ""),
    volume_cc_periventricular:
      typeof o["volume_cc_periventricular"] === "number" ? (o["volume_cc_periventricular"] as number) : undefined,
    volume_cc_deep_subcortical:
      typeof o["volume_cc_deep_subcortical"] === "number" ? (o["volume_cc_deep_subcortical"] as number) : undefined,
    volume_cc_infratentorial:
      typeof o["volume_cc_infratentorial"] === "number" ? (o["volume_cc_infratentorial"] as number) : undefined,
  };
}

function buildGuardrails(r: PredictBackendResponse): ScanGuardrailsMeta | undefined {
  const warns = r.warnings ?? [];
  const hasAudit = Boolean(r.audit_id && String(r.audit_id).length > 0);
  if (!warns.length && !hasAudit && !r.validation && !r.uncertainty) {
    return undefined;
  }
  return {
    warnings: warns,
    auditId: r.audit_id ?? null,
    auditTimestamp: r.audit_timestamp ?? null,
    disposition: r.disposition,
    radiologistActionRequired: r.radiologist_action_required ?? null,
    validation: r.validation,
    uncertainty: r.uncertainty,
  };
}

async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.onload = () => resolve(String(reader.result || ""));
    reader.readAsDataURL(file);
  });
}

function mapClassifierResponse(r: PredictBackendResponse, fallbackModelName: string): ScanFindings {
  const raw = r.class_probabilities ?? r.probabilities ?? {};
  const classProbs: ClassProb[] = Object.entries(raw)
    .map(([label, probability]) => ({ label, probability: Number(probability) }))
    .filter((row) => !Number.isNaN(row.probability))
    .sort((a, b) => b.probability - a.probability);

  const pred =
    typeof r.prediction === "string" && r.prediction
      ? r.prediction
      : typeof r.label === "string"
        ? r.label
        : "";

  return {
    prediction: pred,
    confidence: typeof r.confidence === "number" ? r.confidence : 0,
    classProbs,
    salMapB64: r.saliency_map_b64 ?? null,
    inferenceMs: Math.round(Number(r.inference_time_s ?? 0) * 1000),
    modelName: (typeof r.model === "string" && r.model) || fallbackModelName,
    inputShape: Array.isArray(r.input_shape) ? (r.input_shape as number[]) : [],
    isSimulated: false,
    isSegmentation: false,
    guardrails: buildGuardrails(r),
  };
}

function mapWMHResponse(r: PredictBackendResponse, fallbackModelName: string): ScanFindings {
  const wmh = coerceWmh(r.wmh ?? null);
  if (!wmh || r.wmh == null) {
    throw new Error("3D response missing WMH metrics");
  }

  const pred =
    typeof r.prediction === "string" && r.prediction
      ? r.prediction
      : typeof r.label === "string"
        ? r.label
        : "wmh_segmentation";

  return {
    prediction: pred,
    confidence: typeof r.confidence === "number" ? r.confidence : 0,
    classProbs: [],
    wmh,
    salMapB64: r.saliency_map_b64 ?? null,
    inferenceMs: Math.round(Number(r.inference_time_s ?? 0) * 1000),
    modelName: (typeof r.model === "string" && r.model) || fallbackModelName,
    inputShape: Array.isArray(r.input_shape) ? (r.input_shape as number[]) : [],
    isSimulated: false,
    isSegmentation: true,
    guardrails: buildGuardrails(r),
  };
}

async function persistLastPrediction(
  file: File,
  filename: string,
  findings: ScanFindings,
  opts: ScanStartOptions,
) {
  try {
    if (findings.isSegmentation) return;
    const probs = Object.fromEntries(findings.classProbs.map((c) => [c.label, c.probability]));
    const prediction: PredictResponse = {
      label: findings.prediction,
      prediction: findings.prediction,
      confidence: findings.confidence,
      probabilities: probs,
      class_probabilities: probs,
      model: findings.modelName,
      shadow_mode: Boolean(opts.shadow_mode),
      study_instance_uid: opts.study_instance_uid ?? undefined,
      site_id: opts.site_id ?? undefined,
      inference_time_s: findings.inferenceMs > 0 ? findings.inferenceMs / 1000 : null,
      saliency_map_b64: findings.salMapB64 ?? null,
      input_shape: findings.inputShape,
    };
    const b64 = await fileToBase64(file);
    sessionStorage.setItem(
      "lastPrediction",
      JSON.stringify({
        scanBase64: b64,
        filename,
        model: findings.modelName,
        study_instance_uid: opts.study_instance_uid ?? "",
        site_id: opts.site_id,
        shadow_mode: Boolean(opts.shadow_mode),
        prediction,
      }),
    );
  } catch {
    /* ignore */
  }
}

export function useScanSimulation(apiKey?: string) {
  const [state, setState] = useState<ScanState>({
    phase: "idle",
    steps: [],
    progressPct: 0,
    sliceIndex: 1,
    snrValue: 0.8,
    findings: null,
    error: null,
    apiInProgress: false,
    apiError: null,
  });

  const sliceRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const snrRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const rafRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const isMounted = useRef(true);
  const startOptsRef = useRef<ScanStartOptions>({});
  const lastFileRef = useRef<File | null>(null);
  const lastFilenameRef = useRef<string>("");
  const sliceMaxRef = useRef(48);

  const clearAllTimers = useCallback(() => {
    if (sliceRef.current) clearInterval(sliceRef.current);
    if (snrRef.current) clearInterval(snrRef.current);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    sliceRef.current = null;
    snrRef.current = null;
    rafRef.current = null;
  }, []);

  const abortInFlightRequest = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
      clearAllTimers();
      abortInFlightRequest();
    };
  }, [clearAllTimers, abortInFlightRequest]);

  function startCounters() {
    sliceRef.current = setInterval(() => {
      if (!isMounted.current) return;
      setState((s) => ({
        ...s,
        sliceIndex: s.sliceIndex >= sliceMaxRef.current ? 1 : s.sliceIndex + 1,
      }));
    }, 100);
    snrRef.current = setInterval(() => {
      if (!isMounted.current) return;
      setState((s) => ({ ...s, snrValue: Math.random() * 0.4 + 0.6 }));
    }, 120);
  }

  function stopCounters() {
    if (sliceRef.current) {
      clearInterval(sliceRef.current);
      sliceRef.current = null;
    }
    if (snrRef.current) {
      clearInterval(snrRef.current);
      snrRef.current = null;
    }
  }

  function smoothProgress(from: number, to: number, duration: number): Promise<void> {
    return new Promise((resolve) => {
      const start = performance.now();
      function frame(now: number) {
        if (!isMounted.current) {
          resolve();
          return;
        }
        const t = Math.min((now - start) / duration, 1);
        const eased = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
        const pct = from + (to - from) * eased;
        setState((s) => ({ ...s, progressPct: pct }));
        if (t < 1) {
          rafRef.current = requestAnimationFrame(frame);
        } else {
          resolve();
        }
      }
      rafRef.current = requestAnimationFrame(frame);
    });
  }

  async function runSimulation(is3d: boolean, apiPromise: Promise<PredictBackendResponse>): Promise<void> {
    const STEPS = is3d ? STEPS_3D : STEPS_2D;
    const steps: ScanStep[] = STEPS.map((s) => ({
      id: s.id,
      name: s.name,
      subtitle: s.subtitle,
      state: "pending",
    }));

    setState((s) => ({ ...s, steps, progressPct: 0 }));

    const lastIdx = STEPS.length - 1;

    for (let i = 0; i < lastIdx; i++) {
      if (!isMounted.current) return;
      const step = STEPS[i]!;
      const prevPct = i > 0 ? STEPS[i - 1]!.endPct : 0;
      const ph = phaseForStepIndex(i, is3d);

      setState((s) => ({
        ...s,
        steps: s.steps.map((st, idx) => (idx === i ? { ...st, state: "active" } : st)),
        phase: ph,
      }));

      const stepStart = performance.now();
      await smoothProgress(prevPct, step.endPct, step.dur);

      const elapsed = Math.round(performance.now() - stepStart);
      setState((s) => ({
        ...s,
        steps: s.steps.map((st, idx) =>
          idx === i ? { ...st, state: "done", elapsedMs: elapsed } : st,
        ),
      }));
    }

    const finalIdx = lastIdx;
    const finalStep = STEPS[finalIdx]!;
    const prevPct = STEPS[finalIdx - 1]!.endPct;

    if (!isMounted.current) return;

    setState((s) => ({
      ...s,
      steps: s.steps.map((st, idx) =>
        idx === finalIdx ? { ...st, state: "active" } : st,
      ),
      phase: phaseForStepIndex(finalIdx, is3d),
    }));

    const stepStartFinal = performance.now();
    const durA = Math.max(400, finalStep.dur * 0.7);
    const durB = Math.min(500, finalStep.dur * 0.35);

    try {
      await Promise.all([smoothProgress(prevPct, 95, durA), apiPromise]);
    } catch (e) {
      console.error("[scan] Final pipeline step — API or progress failed:", e);
      throw e;
    }

    await smoothProgress(95, 100, durB);

    const elapsedFinal = Math.round(performance.now() - stepStartFinal);

    if (!isMounted.current) return;

    setState((s) => ({
      ...s,
      steps: s.steps.map((st, idx) =>
        idx === finalIdx ? { ...st, state: "done", elapsedMs: elapsedFinal } : st,
      ),
      progressPct: 100,
    }));
  }

  const reset = useCallback(() => {
    clearAllTimers();
    abortInFlightRequest();
    lastFileRef.current = null;
    lastFilenameRef.current = "";
    setState({
      phase: "idle",
      steps: [],
      progressPct: 0,
      sliceIndex: 1,
      snrValue: 0.8,
      findings: null,
      error: null,
      apiInProgress: false,
      apiError: null,
    });
  }, [clearAllTimers, abortInFlightRequest]);

  const startScan = useCallback(
    async (file: File, modelName: string, opts?: ScanStartOptions) => {
      if (!isMounted.current) return;
      clearAllTimers();
      abortInFlightRequest();
      abortRef.current = new AbortController();
      const signal = abortRef.current.signal;
      startOptsRef.current = opts ?? {};
      lastFileRef.current = file;
      lastFilenameRef.current = file.name || "scan";

      const is3d = modelName === "unet_3d_wmh";
      sliceMaxRef.current = is3d ? 96 : 48;

      if (is3d) {
        const name = file.name.toLowerCase();
        const ok = name.endsWith(".nii") || name.endsWith(".nii.gz");
        if (!ok) {
          setState((s) => ({
            ...s,
            phase: "error",
            error: "WMH 3D model requires NIfTI file (.nii or .nii.gz)",
            apiError: "WMH 3D model requires NIfTI file (.nii or .nii.gz)",
            apiInProgress: false,
            findings: null,
            steps: [],
          }));
          return;
        }
      }

      const apiPromise = predict(
        {
          file,
          modelName,
          is3D: is3d,
          study_instance_uid: startOptsRef.current.study_instance_uid,
          site_id: startOptsRef.current.site_id,
          shadow_mode: startOptsRef.current.shadow_mode,
          context: startOptsRef.current.clinicalContext,
        },
        signal,
        apiKey,
      );

      setState({
        phase: "uploading",
        steps: [],
        progressPct: 0,
        sliceIndex: 1,
        snrValue: 0.8,
        findings: null,
        error: null,
        apiInProgress: true,
        apiError: null,
      });

      startCounters();

      try {
        await runSimulation(is3d, apiPromise);
      } catch (e) {
        if (e instanceof Error && e.name === "AbortError") {
          stopCounters();
          return;
        }
        console.error("[scan] Simulation / API merged step failed:", e);
      }

      stopCounters();

      if (!isMounted.current) return;

      let apiResult: PredictBackendResponse | null = null;
      let apiErr: string | null = null;

      try {
        apiResult = await apiPromise;
      } catch (e) {
        if (e instanceof Error && e.name === "AbortError") {
          setState((s) => ({
            ...s,
            apiInProgress: false,
          }));
          return;
        }
        if (e instanceof ApiError) {
          apiErr = e.detail;
        } else {
          apiErr = e instanceof Error ? e.message : String(e);
        }
        console.error("[scan] Predict failed:", e);
      }

      if (!isMounted.current) return;

      if (apiErr) {
        setState((s) => ({
          ...s,
          phase: "error",
          apiInProgress: false,
          apiError: apiErr,
          error: apiErr,
          findings: null,
        }));
        return;
      }

      if (!apiResult) {
        setState((s) => ({
          ...s,
          phase: "error",
          apiInProgress: false,
          apiError: "No result returned from server",
          error: "No result returned from server",
          findings: null,
        }));
        return;
      }

      try {
        const findings: ScanFindings = is3d ? mapWMHResponse(apiResult, modelName) : mapClassifierResponse(apiResult, modelName);

        await persistLastPrediction(file, lastFilenameRef.current, findings, startOptsRef.current);

        setState((s) => ({
          ...s,
          phase: "complete",
          findings,
          error: null,
          apiError: null,
          apiInProgress: false,
        }));
      } catch (mapErr) {
        const msg = mapErr instanceof Error ? mapErr.message : String(mapErr);
        console.error("[scan] Response mapping failed:", mapErr);
        setState((s) => ({
          ...s,
          phase: "error",
          findings: null,
          apiInProgress: false,
          apiError: msg,
          error: msg,
        }));
      }
    },
    [apiKey, clearAllTimers, abortInFlightRequest],
  );

  return { state, startScan, reset };
}
