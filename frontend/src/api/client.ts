export type PredictResponse = {
  label: string;
  confidence: number;
  probabilities: Record<string, number>;
  model: string;
  dicom_meta?: Record<string, unknown> | null;
  study_instance_uid?: string | null;
  site_id?: string | null;
  shadow_mode: boolean;
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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const API_KEY = import.meta.env.VITE_API_KEY || "";

function buildAuthHeaders(): Record<string, string> {
  if (!API_KEY) return {};
  return { "X-API-Key": API_KEY };
}

async function readErrorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return data?.detail || data?.message || res.statusText;
  } catch {
    return res.statusText;
  }
}

export async function predictScan(input: {
  file: File;
  model: string;
  study_instance_uid?: string;
  site_id?: string;
  shadow_mode: boolean;
}): Promise<PredictResponse> {
  const url = new URL("/predict", API_BASE_URL);
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
  return (await res.json()) as PredictResponse;
}

export async function generateReport(input: {
  file: File;
  model: string;
  study_instance_uid?: string;
  site_id?: string;
  shadow_mode: boolean;
}): Promise<ReportResponse> {
  const url = new URL("/report", API_BASE_URL);
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
  const url = new URL("/clinical/feedback", API_BASE_URL);

  const res = await fetch(url.toString(), {
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
  const url = new URL("/cases", API_BASE_URL);
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
  const url = new URL(`/cases/${encodeURIComponent(study_instance_uid)}`, API_BASE_URL);
  const res = await fetch(url.toString(), { method: "GET", headers: buildAuthHeaders() });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return await res.json();
}

export async function getMetrics(): Promise<MetricsResponse> {
  const url = new URL("/metrics", API_BASE_URL);
  const res = await fetch(url.toString(), { method: "GET", headers: buildAuthHeaders() });
  if (!res.ok) throw new Error(await readErrorMessage(res));
  return (await res.json()) as MetricsResponse;
}

export async function askDocs(question: string): Promise<DocsAnswer> {
  const url = new URL("/docs/ask", API_BASE_URL);
  const res = await fetch(url.toString(), {
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

