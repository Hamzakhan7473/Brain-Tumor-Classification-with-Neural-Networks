import React, { useEffect, useState } from "react";
import { CaseSummary, listCases } from "../api/client";

export default function FeedbackAssignment() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const data = await listCases({ limit: 100 });
        if (!mounted) return;
        setCases(data);
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
      <h2 style={{ marginTop: 16 }}>Feedback assignment (Phase B)</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        Lightweight worklist for assigning shadow-mode cases to readers with due dates.
      </p>

      <div className="card" style={{ marginTop: 14 }}>
        <div style={{ fontWeight: 800 }}>Assignment board</div>
        <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
          Backed by <code>/cases</code>. In the future this can support `assigned_to` and due-date filters.
        </p>

        {error ? <div style={{ marginTop: 8, color: "crimson", fontSize: 13 }}>{error}</div> : null}
        {loading ? <div style={{ marginTop: 8, color: "var(--ink-mute)", fontSize: 13 }}>Loading cases…</div> : null}

        <div style={{ marginTop: 10, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--ink-mute)" }}>
                <th style={{ padding: "6px 4px" }}>Study UID</th>
                <th style={{ padding: "6px 4px" }}>Reader</th>
                <th style={{ padding: "6px 4px" }}>Due</th>
                <th style={{ padding: "6px 4px" }}>Status</th>
                <th style={{ padding: "6px 4px" }}>Notes</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.study_instance_uid}>
                  <td style={{ padding: "6px 4px" }}>{c.study_instance_uid}</td>
                  <td style={{ padding: "6px 4px" }}>Unassigned</td>
                  <td style={{ padding: "6px 4px" }}>—</td>
                  <td style={{ padding: "6px 4px" }}>{c.feedback_status || "pending"}</td>
                  <td style={{ padding: "6px 4px" }}>{c.site_id || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

