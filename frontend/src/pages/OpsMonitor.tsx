import React, { useEffect, useState } from "react";
import { getMetrics, MetricsResponse } from "../api/client";
import { AppPage } from "../components/layout/AppPage";

export default function OpsMonitor() {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const data = await getMetrics();
        if (!mounted) return;
        setMetrics(data);
      } catch (e) {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <AppPage
      title="Ops monitor"
      subtitle="High-level view for volume and feedback. Backed by /metrics; latency/drift can be added later."
    >
      {error ? <div className="app-text-error" style={{ marginBottom: 12, fontSize: 13 }}>{error}</div> : null}

      <div className="app-grid-2">
        <div className="card">
          <div className="app-card-title">Latency &amp; volume</div>
          <p className="app-card-sub">
            {loading
              ? "Loading metrics from /metrics…"
              : metrics?.mongo_enabled
                ? "Metrics are coming from Mongo-backed aggregation."
                : "Mongo disabled; numbers below are illustrative placeholders."}
          </p>
          <div className="app-kpi-grid" style={{ marginTop: 12 }}>
            <div className="app-kpi">
              <div className="app-kpi-label">Total cases</div>
              <div className="app-kpi-value">{metrics?.total_cases ?? "—"}</div>
            </div>
            <div className="app-kpi">
              <div className="app-kpi-label">Feedback submitted</div>
              <div className="app-kpi-value">{metrics?.total_feedback ?? "—"}</div>
            </div>
            <div className="app-kpi">
              <div className="app-kpi-label">Corrected / unclear</div>
              <div className="app-kpi-value">{(metrics?.corrected ?? 0) + (metrics?.unclear ?? 0)}</div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="app-card-title">Error &amp; drift watch</div>
          <p className="app-card-sub">
            Future: hook to a model monitoring service (e.g. custom /ops/drift endpoint or external).
          </p>
          <ul className="app-text-muted" style={{ marginTop: 8, paddingLeft: 18, fontSize: 13 }}>
            <li>Inference failures in last 24h: 0</li>
            <li>High-disagreement cases (AI vs clinician): 3</li>
            <li>Sites with elevated error rate: none</li>
          </ul>
        </div>
      </div>
    </AppPage>
  );
}
