import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CaseSummary, formatApiConnectionHint, getMetrics, listCases, MetricsResponse } from "../api/client";

type StoredPrediction = {
  scanBase64: string;
  filename: string;
  model: string;
  study_instance_uid: string;
  site_id?: string;
  shadow_mode: boolean;
  prediction: {
    label: string;
    confidence: number;
  };
};

export default function Dashboard() {
  const [stored, setStored] = useState<StoredPrediction | null>(null);
  const [feedbackStatus, setFeedbackStatus] = useState<string>("pending");
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [filter, setFilter] = useState<string>("");

  useEffect(() => {
    const raw = sessionStorage.getItem("lastPrediction");
    if (raw) {
      try {
        setStored(JSON.parse(raw) as StoredPrediction);
      } catch {
        // ignore
      }
    }
    const fb = sessionStorage.getItem("lastFeedbackStatus");
    if (fb) setFeedbackStatus(fb);
  }, []);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const [c, m] = await Promise.all([listCases({ limit: 25 }), getMetrics()]);
        if (!mounted) return;
        setCases(c);
        setMetrics(m);
      } catch (e) {
        if (!mounted) return;
        const raw = e instanceof Error ? e.message : String(e);
        setError(formatApiConnectionHint(raw));
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const filteredCases = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return cases;
    return cases.filter((c) => (c.study_instance_uid || "").toLowerCase().includes(q) || (c.site_id || "").toLowerCase().includes(q));
  }, [cases, filter]);

  const pending = filteredCases.filter((c) => (c.feedback_status || "pending") === "pending");

  return (
    <div className="container" style={{ paddingTop: 88 }}>
      <h2 style={{ marginBottom: 4 }}>Dashboard</h2>
      <p style={{ color: "var(--ink-mute)", marginBottom: 16 }}>
        Recent cases and feedback status across your imaging AI workflows.
      </p>

      <div style={{ display: "flex", gap: 12, marginBottom: 18, flexWrap: "wrap" }}>
        <div className="card" style={{ flex: "1 1 160px", padding: "12px 14px" }}>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.08, color: "var(--ink-mute)" }}>
            Total cases
          </div>
          <div style={{ fontSize: 20, fontWeight: 800 }}>{metrics?.total_cases ?? (stored ? 1 : 0)}</div>
        </div>
        <div className="card" style={{ flex: "1 1 160px", padding: "12px 14px" }}>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.08, color: "var(--ink-mute)" }}>
            Feedback submitted
          </div>
          <div style={{ fontSize: 20, fontWeight: 800 }}>{metrics?.total_feedback ?? (feedbackStatus !== "pending" && stored ? 1 : 0)}</div>
        </div>
        <div className="card" style={{ flex: "1 1 160px", padding: "12px 14px" }}>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.08, color: "var(--ink-mute)" }}>
            Corrected / unclear
          </div>
          <div style={{ fontSize: 20, fontWeight: 800 }}>{(metrics?.corrected ?? 0) + (metrics?.unclear ?? 0) || (stored && (feedbackStatus === "wrong_class" || feedbackStatus === "unclear") ? 1 : 0)}</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <h3 style={{ margin: 0 }}>Cases</h3>
          <input
            type="text"
            placeholder="Search by study UID or site…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ maxWidth: 360 }}
          />
          <Link className="btn-primary" to="/upload">
            New scan
          </Link>
        </div>
        {error ? <p style={{ color: "crimson", marginTop: 10, whiteSpace: "pre-wrap" }}>{error}</p> : null}
        {loading ? (
          <p style={{ color: "var(--ink-mute)", marginTop: 10 }}>Loading cases…</p>
        ) : (
          <div style={{ marginTop: 12, overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", color: "var(--ink-mute)" }}>
                  <th style={{ padding: "8px 6px" }}>Study UID</th>
                  <th style={{ padding: "8px 6px" }}>Site</th>
                  <th style={{ padding: "8px 6px" }}>Model</th>
                  <th style={{ padding: "8px 6px" }}>Label</th>
                  <th style={{ padding: "8px 6px" }}>Conf</th>
                  <th style={{ padding: "8px 6px" }}>Feedback</th>
                </tr>
              </thead>
              <tbody>
                {filteredCases.map((c) => (
                  <tr key={c.study_instance_uid} style={{ borderTop: "1px solid var(--line)" }}>
                    <td style={{ padding: "10px 6px" }}>
                      <Link to={`/cases/${c.study_instance_uid}`} style={{ textDecoration: "underline" }}>
                        {c.study_instance_uid}
                      </Link>
                    </td>
                    <td style={{ padding: "10px 6px" }}>{c.site_id || "—"}</td>
                    <td style={{ padding: "10px 6px" }}>{c.model || "—"}</td>
                    <td style={{ padding: "10px 6px" }}>{c.label || "—"}</td>
                    <td style={{ padding: "10px 6px" }}>
                      {typeof c.confidence === "number" ? `${(c.confidence * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td style={{ padding: "10px 6px" }}>
                      {(c.feedback_status || "pending") === "pending" ? (
                        <span style={{ color: "#92400e" }}>Pending</span>
                      ) : (
                        <span style={{ color: "#166534" }}>{c.feedback_status}</span>
                      )}
                    </td>
                  </tr>
                ))}
                {!filteredCases.length ? (
                  <tr>
                    <td colSpan={6} style={{ padding: "12px 6px", color: "var(--ink-mute)" }}>
                      No cases found.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0, marginBottom: 8 }}>Pending feedback</h3>
        {!pending.length ? (
          <p style={{ color: "var(--ink-mute)" }}>No pending cases.</p>
        ) : (
          <ul style={{ marginLeft: 16 }}>
            {pending.slice(0, 8).map((c) => (
              <li key={c.study_instance_uid} style={{ marginBottom: 6 }}>
                <Link to={`/cases/${c.study_instance_uid}`} style={{ textDecoration: "underline" }}>
                  {c.study_instance_uid}
                </Link>{" "}
                <span style={{ color: "var(--ink-mute)" }}>· {c.site_id || "—"} · {c.label || "—"}</span>
                <span style={{ marginLeft: 8 }}>
                  <Link to="/clinical-feedback" className="btn" style={{ padding: "4px 10px", fontSize: 12 }}>
                    Open feedback
                  </Link>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

