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

export type ReportResponse = {
  prediction: string;
  confidence: number;
  report_text: string;
  study_instance_uid?: string | null;
  site_id?: string | null;
  shadow_mode: boolean;
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

export type DocsAnswer = {
  answer: string;
  citations: Array<{
    id: string;
    title?: string;
    source?: string;
    snippet: string;
    score?: number;
  }>;
};

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
  if (/503|model not available|load failed/i.test(baseMessage)) {
    return `${baseMessage}\n\nPlace trained weights in models/saved/ for the selected model name, or run training scripts from the README.`;
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

export async function submitClinicalFeedback(input: {
  study_instance_uid: string;
  site_id?: string;
  feedback: "agree" | "wrong_class" | "unclear";
  corrected_class?: string | null;
  notes?: string | null;
  model?: string | null;
}): Promise<{ status: string; received?: boolean }> {
  const url = apiUrl("/clinical/feedback");

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildAuthHeaders(),
    },
    body: JSON.stringify({
      study_instance_uid: input.study_instance_uid,
      site_id: input.site_id || null,
      feedback: input.feedback,
      corrected_class: input.feedback === "wrong_class" ? input.corrected_class : null,
      notes: input.notes || null,
      model: input.model || null,
    }),
  });

  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as { status: string; received?: boolean };
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

export async function askDocs(question: string): Promise<DocsAnswer> {
  const url = apiUrl("/docs/ask");
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildAuthHeaders(),
    },
    body: JSON.stringify({ question }),
  });

  // If backend endpoint isn't available yet, return a graceful mocked response.
  if (!res.ok) {
    return {
      answer:
        "Docs assistant is not connected yet. Next step: add a `/docs/ask` endpoint that uses PageIndex (tree-search) or Mongo RAG.\n\nFor now, this is a UI-only workflow with traceable citations.",
      citations: [
        {
          id: "local-placeholder-1",
          title: "Clinical workflow (placeholder)",
          source: "docs/clinical-workflow.md",
          snippet:
            "Phase B (Shadow Mode): run silently alongside clinicians, log results with study_instance_uid/site_id, and collect feedback for retrospective validation.",
          score: 0.91,
        },
      ],
    };
  }

  return (await res.json()) as DocsAnswer;
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

