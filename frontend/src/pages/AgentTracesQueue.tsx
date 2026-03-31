import React from "react";
import { Link } from "react-router-dom";

type AgentTraceRow = {
  id: string;
  workflow: string;
  status: "success" | "error";
  risk: "low" | "medium" | "high";
  createdAt: string;
};

const mockTraces: AgentTraceRow[] = [
  {
    id: "trace-auth-001",
    workflow: "Prior auth · Brain MRI",
    status: "success",
    risk: "medium",
    createdAt: "Just now",
  },
  {
    id: "trace-inbox-001",
    workflow: "Inbox · MRI prep question",
    status: "success",
    risk: "low",
    createdAt: "5 min ago",
  },
];

export default function AgentTracesQueue() {
  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Agent traces</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        Multi-agent runs for workflows like auths, inbox, and discharge follow-up. Designed for audit and safety review.
      </p>

      <div className="card" style={{ marginTop: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
          <div>
            <div style={{ fontWeight: 800 }}>Runs</div>
            <div style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
              Total: {mockTraces.length}. Each run shows how the AI assistants worked together on a case.
            </div>
          </div>
        </div>

        <div style={{ marginTop: 10, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--ink-mute)" }}>
                <th style={{ padding: "6px 4px" }}>Workflow</th>
                <th style={{ padding: "6px 4px" }}>Status</th>
                <th style={{ padding: "6px 4px" }}>Risk</th>
                <th style={{ padding: "6px 4px" }}>Started</th>
                <th style={{ padding: "6px 4px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {mockTraces.map((t) => (
                <tr key={t.id}>
                  <td style={{ padding: "6px 4px" }}>{t.workflow}</td>
                  <td style={{ padding: "6px 4px" }}>{t.status}</td>
                  <td style={{ padding: "6px 4px" }}>{t.risk}</td>
                  <td style={{ padding: "6px 4px" }}>{t.createdAt}</td>
                  <td style={{ padding: "6px 4px" }}>
                    <Link to={`/agents-traces/${encodeURIComponent(t.id)}`} className="btn">
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

