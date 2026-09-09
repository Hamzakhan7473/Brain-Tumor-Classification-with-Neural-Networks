import { useEffect, useState } from "react";
import { fetchPublicFeatures, type FeaturesCatalogResponse, type PublicCapabilities } from "../api/client";

/**
 * Module-level cache so every consumer shares a single GET /features call
 * per page load. `null` means the backend was unreachable (render nothing).
 */
let cached: FeaturesCatalogResponse | null | undefined;
let inflight: Promise<FeaturesCatalogResponse | null> | null = null;

function loadOnce(): Promise<FeaturesCatalogResponse | null> {
  if (cached !== undefined) return Promise.resolve(cached);
  if (!inflight) {
    inflight = fetchPublicFeatures().then((res) => {
      cached = res;
      inflight = null;
      return res;
    });
  }
  return inflight;
}

export type UseFeaturesResult = {
  loading: boolean;
  catalog: FeaturesCatalogResponse | null;
  capabilities: PublicCapabilities | null;
  /** Active LLM provider; "" while loading or when the backend is unreachable/unconfigured. */
  llmProvider: "bedrock" | "gemini" | "";
};

export function useFeatures(): UseFeaturesResult {
  const [catalog, setCatalog] = useState<FeaturesCatalogResponse | null>(cached ?? null);
  const [loading, setLoading] = useState(cached === undefined);

  useEffect(() => {
    let alive = true;
    void loadOnce().then((res) => {
      if (!alive) return;
      setCatalog(res);
      setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, []);

  return {
    loading,
    catalog,
    capabilities: catalog?.capabilities ?? null,
    llmProvider: catalog?.capabilities.llm_provider ?? "",
  };
}
