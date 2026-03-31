import React, { useEffect, useState } from "react";
import { getMetrics, MetricsResponse } from "../api/client";

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
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Ops monitor (Phase B)</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        High-level view for volume and feedback. Backed by <code>/metrics</code>; latency/drift can be added later.
      </p>

      {error ? (
        <div style={{ marginTop: 8, color: "crimson", fontSize: 13 }}>{error}</div>
      ) : null}

      <div className="grid2" style={{ marginTop: 14 }}>
        <div className="card">
          <div style={{ fontWeight: 800 }}>Latency &amp; volume</div>
          <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
            {loading
              ? "Loading metrics from /metrics…"
              : metrics?.mongo_enabled
              ? "Metrics are coming from Mongo-backed aggregation."
              : "Mongo disabled; numbers below are illustrative placeholders."}
          </p>
          <div style={{ marginTop: 12, display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div className="card" style={{ flex: "1 1 120px", padding: 12 }}>
              <div style={{ fontSize: 12, color: "var(--ink-mute)" }}>Total cases</div>
              <div style={{ fontSize: 20, fontWeight: 800 }}>
                {metrics?.total_cases ?? "—"}
              </div>
            </div>
            <div className="card" style={{ flex: "1 1 120px", padding: 12 }}>
              <div style={{ fontSize: 12, color: "var(--ink-mute)" }}>Feedback submitted</div>
              <div style={{ fontSize: 20, fontWeight: 800 }}>
                {metrics?.total_feedback ?? "—"}
              </div>
            </div>
            <div className="card" style={{ flex: "1 1 120px", padding: 12 }}>
              <div style={{ fontSize: 12, color: "var(--ink-mute)" }}>Corrected / unclear</div>
              <div style={{ fontSize: 20, fontWeight: 800 }}>
                {(metrics?.corrected ?? 0) + (metrics?.unclear ?? 0)}
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div style={{ fontWeight: 800 }}>Error &amp; drift watch</div>
          <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
            Future: hook to a model monitoring service (e.g. custom `/ops/drift` endpoint or external).
          </p>
          <ul style={{ marginTop: 8, paddingLeft: 18, fontSize: 13, color: "var(--ink-mute)" }}>
            <li>Inference failures in last 24h: 0</li>
            <li>High-disagreement cases (AI vs clinician): 3</li>
            <li>Sites with elevated error rate: none</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

