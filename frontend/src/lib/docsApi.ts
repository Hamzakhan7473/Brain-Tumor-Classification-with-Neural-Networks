const API_KEY = (import.meta.env.VITE_API_KEY || "").trim();

function getApiRoot(): string {
  const env = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
  if (env) return env.replace(/\/$/, "");
  if (import.meta.env.DEV) return "/api";
  return "http://localhost:8000";
}

function apiUrl(path: string): string {
  const root = getApiRoot().replace(/\/$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  if (root.startsWith("http://") || root.startsWith("https://")) {
    return `${root}${p}`;
  }
  return `${root}${p}`;
}

function authHeaders(): Record<string, string> {
  if (!API_KEY) return {};
  return { "X-API-Key": API_KEY };
}

async function readErrorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return String(data?.detail || data?.message || res.statusText);
  } catch {
    return res.statusText;
  }
}

export type DocsAssistantCitation = {
  doc_id: string;
  doc_name: string;
  section: string;
  page: number | string;
  node_id?: string;
  snippet: string;
  relevance: number;
};

export type DocsAssistantAnswer = {
  answer: string;
  citations: DocsAssistantCitation[];
  confidence: "high" | "med" | "low" | string;
  reasoning_trace: string[];
  latency_ms: number;
  tokens_used: number;
  audit_id: string;
  timestamp: string;
};

export type DocsManifestResponse = {
  documents: Array<{ doc_id: string; name: string; sections?: number; pages?: number }>;
  total?: number;
  indexed?: boolean;
  updated_at?: string;
};

export async function listIndexedDocs(): Promise<DocsManifestResponse | null> {
  const res = await fetch(apiUrl("/docs/manifest"), { headers: { ...authHeaders() } });
  if (!res.ok) return null;
  return (await res.json()) as DocsManifestResponse;
}

export async function askDocs(
  question: string,
  opts?: { max_nodes?: number; doc_filter?: string[] }
): Promise<DocsAssistantAnswer> {
  const res = await fetch(apiUrl("/docs/ask"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({
      question,
      max_nodes: opts?.max_nodes ?? 8,
      doc_filter: opts?.doc_filter ?? null,
    }),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
  return (await res.json()) as DocsAssistantAnswer;
}

export async function flagDocsInaccurate(input: {
  audit_id: string;
  reason: string;
  question: string;
}): Promise<void> {
  const res = await fetch(apiUrl("/feedback/docs"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    throw new Error(await readErrorMessage(res));
  }
}
