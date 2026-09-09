export type PredictResponse = {
  label: string;
  confidence: number;
  probabilities: Record<string, number>;
  /** Alias of label */
  prediction?: string;
  /** Alias of probabilities */
  class_probabilities?: Record<string, number>;
  model: string;
  dicom_meta?: Record<string, unknown> | null;
  study_instance_uid?: string | null;
  site_id?: string | null;
  shadow_mode: boolean;
  model_version?: string | null;
  input_shape?: number[] | null;
  preprocessing_applied?: string[] | null;
  saliency_url?: string | null;
  saliency_map_b64?: string | null;
  inference_time_s?: number | null;
};

export type ClinicalValidation = {
  passed: boolean;
  invented_numbers: string[];
  invented_entities: string[];
  omitted_findings: string[];
  contradicted_claims?: string[];
  unaddressed_claims?: string[];
  independent_visual_claims?: string[];
  used_fallback: boolean;
  regenerated: boolean;
  violations?: Array<{ type: string; value: string; severity: string; tier?: string }>;
  chain_of_verification?: {
    passed: boolean;
    human_review_required: boolean;
    tier_0_failure: boolean;
    claims: Array<{ claim: string; status: string; rationale: string }>;
    contradicted_claims: string[];
    not_addressed_claims: string[];
  } | null;
};

export type ContentProvenance = {
  generated_by: string;
  prompt_template_version: string;
  grounding_score?: number | null;
  validator_status: "passed" | "warnings" | "failed" | string;
  validator_warnings?: string[];
};

export type ReportResponse = {
  prediction: string;
  confidence: number;
  report_text: string;
  study_instance_uid?: string | null;
  site_id?: string | null;
  shadow_mode: boolean;
  validation?: ClinicalValidation | null;
  provenance?: ContentProvenance | null;
};

export type CaseSummary = {
  study_instance_uid: string;
  site_id?: string | null;
  model?: string | null;
  label?: string | null;
  confidence?: number | null;
  shadow_mode: boolean;
  timestamp?: string | null;
  feedback_status: string;
  feedback_timestamp?: string | null;
};

export type MetricsResponse = {
  mongo_enabled: boolean;
  total_cases?: number;
  total_feedback?: number;
  agree?: number;
  corrected?: number;
  unclear?: number;
};

export type { DocsAssistantAnswer as DocsAnswer, DocsAssistantCitation } from "../lib/docsApi";
export { askDocs, listIndexedDocs } from "../lib/docsApi";

const API_KEY = (import.meta.env.VITE_API_KEY || "").trim();

/**
 * Base URL for the FastAPI backend.
 * - Dev default: `/api` (Vite proxies to http://127.0.0.1:8000).
 * - Production: set `VITE_API_BASE_URL` (e.g. `https://api.example.com` or `/api` behind nginx).
 */
export function getApiRoot(): string {
  const env = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
  if (env) return env.replace(/\/$/, "");
  if (import.meta.env.DEV) return "/api";
  return "http://localhost:8000";
}

function apiUrl(path: string): string {
  const root = getApiRoot();
  const p = path.startsWith("/") ? path : `/${path}`;
  if (root.startsWith("http://") || root.startsWith("https://")) {
    return `${root}${p}`;
  }
  return `${root}${p}`;
}

/** Parseable URL for query params (handles relative `/api/...` in the browser). */
function apiURL(path: string): URL {
  const s = apiUrl(path);
  if (s.startsWith("http://") || s.startsWith("https://")) {
    return new URL(s);
  }
  const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost";
  return new URL(s, origin);
}

export function isFrontendApiKeyConfigured(): boolean {
  return Boolean(API_KEY);
}

function buildAuthHeaders(): Record<string, string> {
  if (!API_KEY) return {};
  return { "X-API-Key": API_KEY };
}

export type ApiHealthResult =
  | { ok: true; auth_required: boolean }
  | { ok: false; reason: string };

export async function checkApiHealth(): Promise<ApiHealthResult> {
  try {
    const res = await fetch(apiUrl("/health"), { method: "GET" });
    if (!res.ok) {
      return { ok: false, reason: `HTTP ${res.status}` };
    }
    const data = (await res.json()) as { auth_required?: boolean };
    return { ok: true, auth_required: Boolean(data.auth_required) };
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Network error";
    return { ok: false, reason: msg };
  }
}

/** User-facing hint when predict/report fail due to connectivity or auth mismatch. */
export function formatApiConnectionHint(baseMessage: string): string {
  if (/fetch|network|failed to fetch|load failed|networkerror/i.test(baseMessage)) {
    return `${baseMessage}\n\nStart the API from the project root: ./scripts/run_api.sh\nOr run API + UI together: ./scripts/demo_local.sh`;
  }
  if (/401|403|invalid or missing api key|api key/i.test(baseMessage)) {
    return `${baseMessage}\n\nSet VITE_API_KEY in frontend/.env to the same value as backend API_KEY, then restart npm run dev.`;
  }
  if (/503|model not available|load failed|document index not built/i.test(baseMessage)) {
    return `${baseMessage}\n\nIf this is the Docs Assistant: run \`python scripts/index_clinical_docs.py\` with PAGEINDEX_API_KEY set, or place trained weights in models/saved/ for inference.`;
  }
  return baseMessage;
}

async function readErrorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return data?.detail || data?.message || res.statusText;
  } catch {
    return res.statusText;
  }
}

export type RegistryModelRow = {
  name: string;
  description: string;
  input_shape: number[];
  dims: number;
  classes: string[];
  task: string;
  normalization?: string | null;
  loaded?: boolean;
  weights_file?: string;
};

export async function listRegistryModels(apiKeyOverride?: string): Promise<RegistryModelRow[]> {
  const headers: Record<string, string> = { ...buildAuthHeaders() };
  const k = (apiKeyOverride ?? "").trim();
  if (k) headers["X-API-Key"] = k;
  const res = await fetch(apiUrl("/models"), { method: "GET", headers });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as RegistryModelRow[];
}

export async function predictScan(input: {
  file: File;
  model: string;
  study_instance_uid?: string;
  site_id?: string;
  shadow_mode: boolean;
  /** Clinical context JSON (same guardrails as lib/api predict). */
  context?: Record<string, unknown>;
}): Promise<PredictResponse> {
  const url = apiURL("/predict");
  url.searchParams.set("model_name", input.model);

  const fd = new FormData();
  fd.append("file", input.file, input.file.name);
  fd.append("model", input.model);
  if (input.study_instance_uid) fd.append("study_instance_uid", input.study_instance_uid);
  if (input.site_id) fd.append("site_id", input.site_id);
  fd.append("shadow_mode", input.shadow_mode ? "true" : "false");
  if (input.context && Object.keys(input.context).length > 0) {
    fd.append("context", JSON.stringify(input.context));
  }

  const res = await fetch(url.toString(), {
    method: "POST",
    headers: buildAuthHeaders(),
    body: fd,
  });

  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as PredictResponse;
}

export async function generateReport(input: {
  file: File;
  model: string;
  study_instance_uid?: string;
  site_id?: string;
  shadow_mode: boolean;
}): Promise<ReportResponse> {
  const url = apiURL("/report");
  url.searchParams.set("model", input.model);

  const fd = new FormData();
  fd.append("file", input.file, input.file.name);
  if (input.study_instance_uid) fd.append("study_instance_uid", input.study_instance_uid);
  if (input.site_id) fd.append("site_id", input.site_id);
  fd.append("shadow_mode", input.shadow_mode ? "true" : "false");

  const res = await fetch(url.toString(), {
    method: "POST",
    headers: buildAuthHeaders(),
    body: fd,
  });

  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as ReportResponse;
}

export type ExplanationResponse = {
  prediction: string;
  confidence: number;
  explanation: string;
  study_instance_uid?: string | null;
  site_id?: string | null;
  shadow_mode: boolean;
  validation?: ClinicalValidation | null;
  provenance?: ContentProvenance | null;
};

export async function explainScan(input: {
  file: File;
  model: string;
  study_instance_uid?: string;
  site_id?: string;
  shadow_mode: boolean;
}): Promise<ExplanationResponse> {
  const url = apiURL("/explain");
  url.searchParams.set("model", input.model);

  const fd = new FormData();
  fd.append("file", input.file, input.file.name);
  if (input.study_instance_uid) fd.append("study_instance_uid", input.study_instance_uid);
  if (input.site_id) fd.append("site_id", input.site_id);
  fd.append("shadow_mode", input.shadow_mode ? "true" : "false");

  const res = await fetch(url.toString(), {
    method: "POST",
    headers: buildAuthHeaders(),
    body: fd,
  });

  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as ExplanationResponse;
}

export type ClinicalVerdict =
  | "agree"
  | "overcall"
  | "undercall"
  | "wrong_anatomy"
  | "wrong_delta"
  | "useless"
  | "partial"
  | "disagree";

export async function submitStructuredClinicalFeedback(input: {
  case_id: string;
  audit_id: string;
  verdict: ClinicalVerdict;
  codes?: ClinicalVerdict[];
  ground_truth?: Record<string, unknown> | null;
  error_categories?: string[];
  clinical_notes?: string | null;
  time_spent_s: number;
  measurements_unedited?: boolean;
  ingest_at?: string | null;
  draft_ready_at?: string | null;
  reviewer_display_name?: string | null;
  reviewer_role?: string | null;
  credentials?: string | null;
}): Promise<{ ok: boolean; feedback_id: string; audit_id: string }> {
  const res = await fetch(apiUrl("/clinical/feedback"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildAuthHeaders(),
    },
    body: JSON.stringify({
      case_id: input.case_id,
      audit_id: input.audit_id,
      verdict: input.verdict,
      codes: input.codes ?? [input.verdict],
      ground_truth: input.ground_truth ?? null,
      error_categories: input.error_categories ?? [],
      clinical_notes: input.clinical_notes ?? null,
      time_spent_s: input.time_spent_s,
      measurements_unedited: input.measurements_unedited ?? true,
      ingest_at: input.ingest_at ?? null,
      draft_ready_at: input.draft_ready_at ?? null,
      reviewer_display_name: input.reviewer_display_name ?? null,
      reviewer_role: input.reviewer_role ?? null,
      credentials: input.credentials ?? null,
    }),
  });

  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as { ok: boolean; feedback_id: string; audit_id: string };
}

export async function getClinicalFeedbackStats(): Promise<{
  reviewed_this_month: number;
  agreement_rate: number;
  avg_time_s: number;
}> {
  const res = await fetch(apiUrl("/clinical/feedback/stats"), { headers: buildAuthHeaders() });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as {
    reviewed_this_month: number;
    agreement_rate: number;
    avg_time_s: number;
  };
}

export async function getClinicalFeedbackRecent(limit = 10): Promise<{ items: Array<Record<string, unknown>> }> {
  const u = apiURL("/clinical/feedback/recent");
  u.searchParams.set("limit", String(limit));
  const res = await fetch(u.toString(), { headers: buildAuthHeaders() });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as { items: Array<Record<string, unknown>> };
}

export async function listCases(input?: { limit?: number; site_id?: string }): Promise<CaseSummary[]> {
  const url = apiURL("/cases");
  if (input?.limit) url.searchParams.set("limit", String(input.limit));
  if (input?.site_id) url.searchParams.set("site_id", input.site_id);

  const res = await fetch(url.toString(), {
    method: "GET",
    headers: buildAuthHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as CaseSummary[];
}

export async function getCase(study_instance_uid: string): Promise<any> {
  const url = apiUrl(`/cases/${encodeURIComponent(study_instance_uid)}`);
  const res = await fetch(url, { method: "GET", headers: buildAuthHeaders() });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return await res.json();
}

export async function getMetrics(): Promise<MetricsResponse> {
  const url = apiUrl("/metrics");
  const res = await fetch(url, { method: "GET", headers: buildAuthHeaders() });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as MetricsResponse;
}

export type PublicFeature = {
  id: string;
  title: string;
  description: string;
  available: boolean;
};

export type PublicCapabilities = {
  models_2d: string[];
  models_3d: string[];
  mongo_configured: boolean;
  llm_configured: boolean;
  /** Active LLM provider ("bedrock" | "gemini"), empty string when none configured. */
  llm_provider: "bedrock" | "gemini" | "";
    bedrock_configured: boolean;
    /** Second-pass claim verification (ENABLE_CHAIN_OF_VERIFICATION). */
    chain_of_verification?: boolean;
    auth_required_globally: boolean;
};

export type FeaturesCatalogResponse = {
  service: string;
  version: string;
  features: PublicFeature[];
  capabilities: PublicCapabilities;
};

/**
 * Public catalog from GET /features (no API key). Returns null if the backend is unreachable.
 */
export async function fetchPublicFeatures(): Promise<FeaturesCatalogResponse | null> {
  const url = apiUrl("/features");
  try {
    const res = await fetch(url, { method: "GET" });
    if (!res.ok) return null;
    return (await res.json()) as FeaturesCatalogResponse;
  } catch {
    return null;
  }
}

export type ReportDraftDoc = Record<string, unknown>;

export type BicrRole = "reader1" | "reader2" | "adjudicator";

export async function enrollBicrCase(body: {
  case_id: string;
  subject_id?: string;
  visit?: string;
  timepoint?: string;
  blind_model?: boolean;
}): Promise<Record<string, unknown>> {
  const res = await fetch(apiUrl("/bicr/cases/enroll"), {
    method: "POST",
    headers: { ...buildAuthHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as Record<string, unknown>;
}

export async function getBicrCase(caseId: string, role: BicrRole): Promise<Record<string, unknown>> {
  const q = new URLSearchParams({ role });
  const res = await fetch(apiUrl(`/bicr/cases/${encodeURIComponent(caseId)}?${q}`), {
    headers: buildAuthHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as Record<string, unknown>;
}

export async function submitBicrRead(
  caseId: string,
  body: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const res = await fetch(apiUrl(`/bicr/cases/${encodeURIComponent(caseId)}/reads`), {
    method: "POST",
    headers: { ...buildAuthHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as Record<string, unknown>;
}

export async function submitBicrAdjudication(
  caseId: string,
  body: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const res = await fetch(apiUrl(`/bicr/cases/${encodeURIComponent(caseId)}/adjudicate`), {
    method: "POST",
    headers: { ...buildAuthHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as Record<string, unknown>;
}

export async function fetchBicrQueue(role: BicrRole, limit = 50): Promise<Record<string, unknown>> {
  const q = new URLSearchParams({ role, limit: String(limit) });
  const res = await fetch(apiUrl(`/bicr/queue?${q}`), { headers: buildAuthHeaders() });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as Record<string, unknown>;
}

export async function createReportDraft(body: {
  case_id: string;
  template_id: string;
  model_run?: Record<string, unknown>;
  clinical_context?: Record<string, unknown>;
  scanner_field_strength?: string;
  prior_studies?: string;
  prior_model_run?: Record<string, unknown>;
}): Promise<ReportDraftDoc> {
  const res = await fetch(apiUrl("/report/draft"), {
    method: "POST",
    headers: { ...buildAuthHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as ReportDraftDoc;
}

export async function getReportDraft(reportId: string): Promise<ReportDraftDoc> {
  const res = await fetch(apiUrl(`/report/${encodeURIComponent(reportId)}`), {
    method: "GET",
    headers: buildAuthHeaders(),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as ReportDraftDoc;
}

export async function patchReportDraftSection(
  reportId: string,
  sectionName: string,
  body: Record<string, unknown>,
): Promise<{ ok: boolean; version: number }> {
  const res = await fetch(
    apiUrl(`/report/${encodeURIComponent(reportId)}/section/${encodeURIComponent(sectionName)}`),
    {
      method: "PATCH",
      headers: { ...buildAuthHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as { ok: boolean; version: number };
}

export async function regenerateReportDraftSection(
  reportId: string,
  sectionName: string,
): Promise<{ ok: boolean; version: number }> {
  const res = await fetch(
    apiUrl(`/report/${encodeURIComponent(reportId)}/section/${encodeURIComponent(sectionName)}/regenerate`),
    { method: "POST", headers: buildAuthHeaders() },
  );
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as { ok: boolean; version: number };
}

export async function attestReportDraft(
  reportId: string,
  body: { attested_by: string; attestation_text: string },
): Promise<{ ok: boolean; attested_by: string; attested_at: string; audit_id: string; already_attested?: boolean }> {
  const res = await fetch(apiUrl(`/report/${encodeURIComponent(reportId)}/attest`), {
    method: "POST",
    headers: { ...buildAuthHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as {
    ok: boolean;
    attested_by: string;
    attested_at: string;
    audit_id: string;
    already_attested?: boolean;
  };
}

export async function attestGeneratedContent(body: {
  attested_by: string;
  attestation_text: string;
  content_kind?: "report" | "explanation";
  content_sha256?: string;
}): Promise<{ ok: boolean; audit_id: string; attested_at: string }> {
  const res = await fetch(apiUrl("/report/attest-content"), {
    method: "POST",
    headers: { ...buildAuthHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as { ok: boolean; audit_id: string; attested_at: string };
}

export async function signReportDraft(
  reportId: string,
  body: {
    signer_name: string;
    signer_role: string;
    npi_or_license?: string;
    acknowledged_disclaimer: boolean;
  },
): Promise<{ ok: boolean; audit_id: string; text_hash: string; fhir_url: string; pdf_url: string }> {
  const res = await fetch(apiUrl(`/report/${encodeURIComponent(reportId)}/sign`), {
    method: "POST",
    headers: { ...buildAuthHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as {
    ok: boolean;
    audit_id: string;
    text_hash: string;
    fhir_url: string;
    pdf_url: string;
  };
}

export function reportDraftPdfUrl(reportId: string): string {
  return apiUrl(`/report/${encodeURIComponent(reportId)}/pdf`);
}

export async function fetchReportDraftPdfBlob(reportId: string): Promise<Blob> {
  const res = await fetch(reportDraftPdfUrl(reportId), { method: "GET", headers: buildAuthHeaders() });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return res.blob();
}

