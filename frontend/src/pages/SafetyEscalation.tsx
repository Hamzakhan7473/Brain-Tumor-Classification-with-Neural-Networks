import React, { useEffect, useMemo, useState } from "react";
import { CaseSummary, listCases } from "../api/client";
import { AppPage } from "../components/layout/AppPage";

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
    [cases],
  );

  return (
    <AppPage
      title="Safety escalation"
      subtitle="Track low-confidence or flagged cases that need mandatory overread."
    >
      <div className="card">
        <div className="app-card-title">Escalation list</div>
        <p className="app-card-sub">
          Currently escalates cases where model confidence &lt; 0.6. Later you can add richer rules via n8n.
        </p>

        {error ? <div className="app-text-error" style={{ marginTop: 8, fontSize: 13 }}>{error}</div> : null}
        {loading ? <div className="app-text-muted" style={{ marginTop: 8, fontSize: 13 }}>Loading cases…</div> : null}

        <div className="app-table-wrap">
          <table className="app-table">
            <thead>
              <tr>
                <th>Study UID</th>
                <th>Reason</th>
                <th>Priority</th>
                <th>Assigned</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {escalated.map((c) => (
                <tr key={c.study_instance_uid}>
                  <td>{c.study_instance_uid}</td>
                  <td>Low confidence {((c.confidence ?? 0) * 100).toFixed(1)}%</td>
                  <td>High</td>
                  <td>Unassigned</td>
                  <td>Needs overread</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AppPage>
  );
}
