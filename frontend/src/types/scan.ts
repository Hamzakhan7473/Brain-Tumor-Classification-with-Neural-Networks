/** Shared scan simulation & findings types (NeuroSight upload flow). */

export type ClinicalContextPayload = {
  age: string;
  sex: string;
  indication: string;
  prior_stroke: string;
  hypertension: string;
  /** optional: yes | no | unknown */
  prior_imaging: string;
};

export type ScanGuardrailsMeta = {
  warnings: string[];
  auditId: string | null;
  auditTimestamp: string | null;
  disposition?: string;
  radiologistActionRequired?: string | null;
  validation?: Record<string, unknown>;
  uncertainty?: Record<string, unknown>;
};

export type ScanPhase =
  | "idle"
  | "uploading"
  | "preprocessing"
  | "inferring"
  | "gradcam"
  | "grading"
  | "reporting"
  | "complete"
  | "error";

export interface ScanStep {
  id: number;
  name: string;
  subtitle: string;
  state: "pending" | "active" | "done";
  elapsedMs?: number;
}

export interface ClassProb {
  label: string;
  probability: number;
}

export type WMHSeverity = "Normal" | "Mild" | "Moderate" | "Severe";
export type WMHRisk = "Low" | "Moderate" | "High" | "Very High";

export interface WMHResult {
  volume_cc: number;
  volume_cc_ci_95?: [number, number];
  volume_uncertainty_cc?: number;
  age_matched_percentile?: number;
  percentile_note?: string;
  lesion_voxels: number;
  lesion_fraction: number;
  mean_lesion_prob: number;
  peak_lesion_prob: number;
  severity_grade: WMHSeverity;
  risk_level: WMHRisk;
  threshold_used: number;
  note: string;
}

export interface ScanFindings {
  prediction: string;
  confidence: number;
  classProbs: ClassProb[];
  wmh?: WMHResult;
  salMapB64?: string | null;
  inferenceMs: number;
  modelName: string;
  inputShape: number[];
  isSimulated: boolean;
  isSegmentation: boolean;
  guardrails?: ScanGuardrailsMeta;
}

export interface ScanState {
  phase: ScanPhase;
  steps: ScanStep[];
  progressPct: number;
  sliceIndex: number;
  snrValue: number;
  findings: ScanFindings | null;
  /** User-facing inference failure message (shown in findings panel). */
  error: string | null;
  /** True while awaiting /predict | /predict-3d response. */
  apiInProgress: boolean;
  /** Same as ``error`` for scan hook; surfaced for Inference failed panel. */
  apiError: string | null;
}

/** Alias used by scan UI components */
export type Phase = ScanPhase;
