import React, { useEffect, useMemo, useState } from "react";
import { CaseSummary, listCases } from "../api/client";

export default function SafetyEscalation() {
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

  const escalated = useMemo(
    () =>
      cases.filter((c) => {
        const conf = c.confidence ?? 1;
        return conf < 0.6;
      }),
    [cases]
  );

  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Safety escalation (Phase C)</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        A simple view to track low-confidence or flagged cases that need mandatory overread.
      </p>

      <div className="card" style={{ marginTop: 14 }}>
        <div style={{ fontWeight: 800 }}>Escalation list</div>
        <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
          Currently escalates cases where model confidence &lt; 0.6. Later you can add richer rules via n8n.
        </p>

        {error ? <div style={{ marginTop: 8, color: "crimson", fontSize: 13 }}>{error}</div> : null}
        {loading ? <div style={{ marginTop: 8, color: "var(--ink-mute)", fontSize: 13 }}>Loading cases…</div> : null}

        <div style={{ marginTop: 10, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--ink-mute)" }}>
                <th style={{ padding: "6px 4px" }}>Study UID</th>
                <th style={{ padding: "6px 4px" }}>Reason</th>
                <th style={{ padding: "6px 4px" }}>Priority</th>
                <th style={{ padding: "6px 4px" }}>Assigned</th>
                <th style={{ padding: "6px 4px" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {escalated.map((c) => (
                <tr key={c.study_instance_uid}>
                  <td style={{ padding: "6px 4px" }}>{c.study_instance_uid}</td>
                  <td style={{ padding: "6px 4px" }}>
                    Low confidence {((c.confidence ?? 0) * 100).toFixed(1)}%
                  </td>
                  <td style={{ padding: "6px 4px" }}>High</td>
                  <td style={{ padding: "6px 4px" }}>Unassigned</td>
                  <td style={{ padding: "6px 4px" }}>Needs overread</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

