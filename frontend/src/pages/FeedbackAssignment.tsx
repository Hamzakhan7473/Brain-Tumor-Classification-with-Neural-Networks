import React, { useEffect, useState } from "react";
import { CaseSummary, listCases } from "../api/client";
import { AppPage } from "../components/layout/AppPage";

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
    <AppPage
      title="Feedback assignment"
      subtitle="Lightweight worklist for assigning shadow-mode cases to readers with due dates."
    >
      <div className="card">
        <div className="app-card-title">Assignment board</div>
        <p className="app-card-sub">
          Backed by <code>/cases</code>. In the future this can support assigned_to and due-date filters.
        </p>

        {error ? <div className="app-text-error" style={{ marginTop: 8, fontSize: 13 }}>{error}</div> : null}
        {loading ? <div className="app-text-muted" style={{ marginTop: 8, fontSize: 13 }}>Loading cases…</div> : null}

        <div className="app-table-wrap">
          <table className="app-table">
            <thead>
              <tr>
                <th>Study UID</th>
                <th>Reader</th>
                <th>Due</th>
                <th>Status</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.study_instance_uid}>
                  <td>{c.study_instance_uid}</td>
                  <td>Unassigned</td>
                  <td>—</td>
                  <td>{c.feedback_status || "pending"}</td>
                  <td>{c.site_id || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AppPage>
  );
}
