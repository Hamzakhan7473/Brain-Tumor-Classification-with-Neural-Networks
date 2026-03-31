import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CaseSummary, listCases } from "../api/client";

export default function ShadowQueue() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [siteFilter, setSiteFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

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

  const filtered = useMemo(() => {
    return cases.filter((c) => {
      if (siteFilter && (c.site_id || "").toLowerCase() !== siteFilter.toLowerCase()) return false;
      if (statusFilter === "awaiting" && c.feedback_status !== "pending") return false;
      if (statusFilter === "completed" && c.feedback_status === "pending") return false;
      return true;
    });
  }, [cases, siteFilter, statusFilter]);

  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Shadow queue (Phase B)</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        Cases arriving automatically from PACS/RIS. This is the home for your shadow-mode pilot.
      </p>

      <div className="card" style={{ marginTop: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
          <div>
            <div style={{ fontWeight: 800 }}>Queue overview</div>
            <div style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
              {loading
                ? "Loading from /cases…"
                : `Total: ${cases.length} · Visible: ${filtered.length} · Pending feedback: ${
                    cases.filter((c) => c.feedback_status === "pending").length
                  }`}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              type="text"
              placeholder="Filter by site (e.g. site-001)"
              value={siteFilter}
              onChange={(e) => setSiteFilter(e.target.value)}
              style={{ maxWidth: 200 }}
            />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ maxWidth: 180, padding: "6px 10px" }}
            >
              <option value="all">All statuses</option>
              <option value="awaiting">Awaiting feedback</option>
              <option value="completed">Feedback completed</option>
            </select>
          </div>
        </div>

        {error ? (
          <div style={{ marginTop: 10, color: "crimson", fontSize: 13 }}>{error}</div>
        ) : null}

        <div style={{ marginTop: 12, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--ink-mute)" }}>
                <th style={{ padding: "6px 4px" }}>Study UID</th>
                <th style={{ padding: "6px 4px" }}>Site</th>
                <th style={{ padding: "6px 4px" }}>Status</th>
                <th style={{ padding: "6px 4px" }}>AI label</th>
                <th style={{ padding: "6px 4px" }}>Feedback</th>
                <th style={{ padding: "6px 4px" }}>Assigned to</th>
                <th style={{ padding: "6px 4px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr key={c.study_instance_uid}>
                  <td style={{ padding: "6px 4px" }}>
                    <Link to={`/cases/${encodeURIComponent(c.study_instance_uid)}`} style={{ textDecoration: "underline" }}>
                      {c.study_instance_uid}
                    </Link>
                  </td>
                  <td style={{ padding: "6px 4px" }}>{c.site_id || "—"}</td>
                  <td style={{ padding: "6px 4px" }}>{c.shadow_mode ? "shadow" : "live"}</td>
                  <td style={{ padding: "6px 4px" }}>
                    {c.label ? `${c.label} ${(c.confidence ?? 0 * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ padding: "6px 4px" }}>{c.feedback_status || "—"}</td>
                  <td style={{ padding: "6px 4px" }}>Unassigned</td>
                  <td style={{ padding: "6px 4px", display: "flex", gap: 6 }}>
                    <Link to={`/reading/${encodeURIComponent(c.study_instance_uid)}`} className="btn">
                      View
                    </Link>
                    <Link to="/clinical-feedback" className="btn">
                      Feedback
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid2" style={{ marginTop: 14 }}>
        <div className="card">
          <div style={{ fontWeight: 800 }}>Status filters</div>
          <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 6 }}>
            In a real deployment this would drive `GET /cases` queries with status + site filters.
          </p>
        </div>
        <div className="card">
          <div style={{ fontWeight: 800 }}>Shadow mode banner</div>
          <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 6 }}>
            Results here are **never** sent to the clinical record. They are for retrospective QA only.
          </p>
        </div>
      </div>
    </div>
  );
}

