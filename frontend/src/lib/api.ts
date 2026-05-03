/**
 * Direct predict client for scan workflow (console logging + typed errors).
 * Base URL mirrors src/api/client.ts: VITE_API_BASE_URL, dev default `/api`.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public endpoint: string,
  ) {
    super(`${endpoint} → ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

function apiBase(): string {
  const env = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
  if (env) return env.replace(/\/$/, "");
  if (import.meta.env.DEV) return "/api";
  return "http://localhost:8000";
}

function resolveUrl(endpoint: string, modelName: string): string {
  const root = apiBase().replace(/\/$/, "");
  const path = `${endpoint}?model_name=${encodeURIComponent(modelName)}`;
  const merged = `${root}${path}`;
  if (merged.startsWith("http://") || merged.startsWith("https://")) {
    return merged;
  }
  const origin =
    typeof window !== "undefined" ? window.location.origin : "http://localhost";
  const pathOnly = merged.startsWith("/") ? merged : `/${merged}`;
  return new URL(pathOnly, origin).href;
}

export interface PredictRequest {
  file: File;
  modelName: string;
  is3D: boolean;
  study_instance_uid?: string;
  site_id?: string;
  shadow_mode?: boolean;
  /** Serialized clinical context JSON (logged server-side). */
  context?: Record<string, unknown>;
}

export interface PredictBackendResponse {
  prediction: string;
  confidence: number;
  label?: string;
  probabilities?: Record<string, number>;
  class_probabilities?: Record<string, number>;
  model: string;
  input_shape?: number[] | null;
  inference_time_s?: number | null;
  saliency_map_b64?: string | null;
  wmh?: Record<string, unknown> | null;
  warnings?: string[];
  disposition?: string;
  audit_id?: string | null;
  audit_timestamp?: string | null;
  radiologist_action_required?: string | null;
  uncertainty?: Record<string, unknown>;
  validation?: Record<string, unknown>;
  display_prediction?: string | null;
}

export async function predict(
  req: PredictRequest,
  signal: AbortSignal,
  apiKeyOverride?: string,
): Promise<PredictBackendResponse> {
  const endpoint = req.is3D ? "/predict-3d" : "/predict";
  const url = resolveUrl(endpoint, req.modelName);

  const form = new FormData();
  form.append("file", req.file, req.file.name);
  form.append("model", req.modelName);
  if (req.context && Object.keys(req.context).length > 0) {
    form.append("context", JSON.stringify(req.context));
  }
  if (!req.is3D) {
    if (req.study_instance_uid) form.append("study_instance_uid", req.study_instance_uid);
    if (req.site_id) form.append("site_id", req.site_id);
    form.append("shadow_mode", req.shadow_mode ? "true" : "false");
  }

  const fromEnv = ((import.meta.env.VITE_API_KEY as string | undefined) ?? "").trim();
  const fromStore =
    typeof window !== "undefined" ? (window.localStorage.getItem("api_key") ?? "").trim() : "";
  const key = ((apiKeyOverride ?? "").trim() || fromEnv || fromStore).trim();

  const headers: Record<string, string> = {};
  if (key) headers["X-API-Key"] = key;

  console.info(
    `[API] POST ${endpoint} (${url}) file: ${req.file.name}, ${(req.file.size / 1024).toFixed(1)} KB`,
  );

  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers,
      body: form,
      signal,
    });
  } catch (e) {
    console.error("[API] Network error:", e);
    throw new ApiError(0, "Network error — is the backend running?", endpoint);
  }

  let data: unknown;
  try {
    data = await res.json();
  } catch {
    throw new ApiError(res.status, "Invalid JSON response", endpoint);
  }

  if (!res.ok) {
    const detail =
      (data as { detail?: string })?.detail ??
      (data as { message?: string })?.message ??
      (data as { error?: string })?.error ??
      `HTTP ${res.status}`;
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
    console.error(`[API] ${endpoint} failed:`, msg, data);
    throw new ApiError(res.status, msg, endpoint);
  }

  console.info(`[API] ${endpoint} success:`, data);
  return data as PredictBackendResponse;
}

export async function listModels(apiKeyOverride?: string): Promise<
  Array<{
    name: string;
    description: string;
    input_shape: number[];
    dims: number;
    classes: string[];
    task?: string;
  }>
> {
  const root = apiBase().replace(/\/$/, "");
  const merged = `${root}/models`;
  let urlStr: string;
  if (merged.startsWith("http://") || merged.startsWith("https://")) {
    urlStr = merged;
  } else {
    const origin =
      typeof window !== "undefined" ? window.location.origin : "http://localhost";
    const pathOnly = merged.startsWith("/") ? merged : `/${merged}`;
    urlStr = new URL(pathOnly, origin).href;
  }

  const fromEnv = ((import.meta.env.VITE_API_KEY as string | undefined) ?? "").trim();
  const fromStore =
    typeof window !== "undefined" ? (window.localStorage.getItem("api_key") ?? "").trim() : "";
  const key = ((apiKeyOverride ?? "").trim() || fromEnv || fromStore).trim();
  const headers: Record<string, string> = {};
  if (key) headers["X-API-Key"] = key;

  const res = await fetch(urlStr, { headers });
  if (!res.ok) throw new ApiError(res.status, "Failed to load models", "/models");
  return res.json();
}

function resolvePostUrl(endpoint: string): string {
  const root = apiBase().replace(/\/$/, "");
  const merged = `${root}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  if (merged.startsWith("http://") || merged.startsWith("https://")) {
    return merged;
  }
  const origin =
    typeof window !== "undefined" ? window.location.origin : "http://localhost";
  const pathOnly = merged.startsWith("/") ? merged : `/${merged}`;
  return new URL(pathOnly, origin).href;
}

function mergedApiKey(extra?: string): string {
  const fromEnv = ((import.meta.env.VITE_API_KEY as string | undefined) ?? "").trim();
  const fromStore =
    typeof window !== "undefined" ? (window.localStorage.getItem("api_key") ?? "").trim() : "";
  return ((extra ?? "").trim() || fromEnv || fromStore).trim();
}

export async function reportSign(input: {
  audit_id: string;
  agreed: boolean;
  override?: string;
  radiologist_id?: string;
  apiKeyOverride?: string;
}): Promise<{ ok: boolean; signoff_id?: string }> {
  const urlStr = resolvePostUrl("/report/sign");
  const key = mergedApiKey(input.apiKeyOverride);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(urlStr, {
    method: "POST",
    headers,
    body: JSON.stringify({
      audit_id: input.audit_id,
      agreed: input.agreed,
      override: input.override,
      radiologist_id: input.radiologist_id,
    }),
  });
  if (!res.ok) throw new ApiError(res.status, await res.text(), "/report/sign");
  return res.json() as Promise<{ ok: boolean; signoff_id?: string }>;
}

export async function reportDefer(input: {
  audit_id: string;
  reason: string;
  apiKeyOverride?: string;
}): Promise<{ ok: boolean; defer_id?: string }> {
  const urlStr = resolvePostUrl("/report/defer");
  const key = mergedApiKey(input.apiKeyOverride);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(urlStr, {
    method: "POST",
    headers,
    body: JSON.stringify({ audit_id: input.audit_id, reason: input.reason }),
  });
  if (!res.ok) throw new ApiError(res.status, await res.text(), "/report/defer");
  return res.json() as Promise<{ ok: boolean; defer_id?: string }>;
}

export async function findingsDisagreeApi(input: {
  audit_id: string;
  notes: string;
  radiologist_id?: string;
  apiKeyOverride?: string;
}): Promise<{ ok: boolean; feedback_id?: string }> {
  const urlStr = resolvePostUrl("/clinical/findings-disagree");
  const key = mergedApiKey(input.apiKeyOverride);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(urlStr, {
    method: "POST",
    headers,
    body: JSON.stringify({
      audit_id: input.audit_id,
      notes: input.notes,
      radiologist_id: input.radiologist_id,
    }),
  });
  if (!res.ok) throw new ApiError(res.status, await res.text(), "/clinical/findings-disagree");
  return res.json() as Promise<{ ok: boolean; feedback_id?: string }>;
}

export function predictApiDisplayBase(): string {
  const b = apiBase().replace(/\/$/, "");
  if (/^https?:\/\//i.test(b)) return b;
  const origin =
    typeof window !== "undefined" ? window.location.origin : "http://localhost";
  const px = b.startsWith("/") ? b : `/${b}`;
  return `${origin}${px}`;
}

// --- Shadow queue (Phase B) -------------------------------------------------

export type ShadowQueueResponse = {
  items: Array<Record<string, unknown>>;
  total: number;
  kpis: Record<string, unknown>;
};

export async function fetchShadowQueue(
  params: URLSearchParams,
  apiKeyOverride?: string,
): Promise<ShadowQueueResponse> {
  const urlStr = `${resolvePostUrl("/shadow/queue")}?${params.toString()}`;
  const key = mergedApiKey(apiKeyOverride);
  const headers: Record<string, string> = {};
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(urlStr, { headers });
  if (!res.ok) throw new ApiError(res.status, await res.text(), "/shadow/queue");
  return (await res.json()) as ShadowQueueResponse;
}

export async function fetchShadowConfig(apiKeyOverride?: string): Promise<{
  classes: string[];
  shadow_mode_disclaimer: string;
}> {
  const urlStr = resolvePostUrl("/shadow/config");
  const key = mergedApiKey(apiKeyOverride);
  const headers: Record<string, string> = {};
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(urlStr, { headers });
  if (!res.ok) throw new ApiError(res.status, await res.text(), "/shadow/config");
  return res.json();
}

export async function submitShadowFeedback(
  studyUid: string,
  input: { verdict: "agree" | "disagree" | "partial"; ground_truth?: Record<string, unknown>; notes?: string },
  apiKeyOverride?: string,
): Promise<{ ok: boolean; audit_id?: string }> {
  const urlStr = resolvePostUrl(`/shadow/cases/${encodeURIComponent(studyUid)}/feedback`);
  const key = mergedApiKey(apiKeyOverride);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(urlStr, {
    method: "POST",
    headers,
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new ApiError(res.status, await res.text(), "/shadow/feedback");
  return res.json();
}

export async function assignShadowCase(
  studyUid: string,
  input: { radiologist_id: string; radiologist_name: string },
  apiKeyOverride?: string,
): Promise<{ ok: boolean }> {
  const urlStr = resolvePostUrl(`/shadow/cases/${encodeURIComponent(studyUid)}/assign`);
  const key = mergedApiKey(apiKeyOverride);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(urlStr, { method: "POST", headers, body: JSON.stringify(input) });
  if (!res.ok) throw new ApiError(res.status, await res.text(), "/shadow/assign");
  return res.json();
}

export function shadowExportUrl(startIso: string, endIso: string, format: "csv" | "json" = "csv"): string {
  const root = apiBase().replace(/\/$/, "");
  const q = `start=${encodeURIComponent(startIso)}&end=${encodeURIComponent(endIso)}&format=${format}`;
  const path = `/shadow/export?${q}`;
  if (root.startsWith("http://") || root.startsWith("https://")) {
    return `${root}${path}`;
  }
  return `${root}${path}`;
}

export async function retryShadowCase(studyUid: string, apiKeyOverride?: string): Promise<{ ok: boolean }> {
  const urlStr = resolvePostUrl(`/shadow/cases/${encodeURIComponent(studyUid)}/retry`);
  const key = mergedApiKey(apiKeyOverride);
  const headers: Record<string, string> = {};
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(urlStr, { method: "POST", headers });
  if (!res.ok) throw new ApiError(res.status, await res.text(), "/shadow/retry");
  return res.json();
}
