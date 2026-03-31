import React from "react";
import { Link } from "react-router-dom";

type AuthRow = {
  id: string;
  patient: string;
  payer: string;
  serviceLine: string;
  status: "draft" | "submitted" | "pending" | "approved" | "denied";
  slaHoursRemaining: number;
};

const mockAuths: AuthRow[] = [
  {
    id: "auth-demo-001",
    patient: "Jane D. (MRN 12345)",
    payer: "Medicare Advantage",
    serviceLine: "Brain MRI w/wo contrast",
    status: "pending",
    slaHoursRemaining: 36,
  },
  {
    id: "auth-demo-002",
    patient: "John S. (MRN 67890)",
    payer: "Commercial",
    serviceLine: "Follow-up brain MRI",
    status: "draft",
    slaHoursRemaining: 120,
  },
];

export default function AuthsQueue() {
  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Prior authorizations</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        Queue of imaging prior authorizations with status and SLA visibility.
      </p>

      <div className="card" style={{ marginTop: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
          <div>
            <div style={{ fontWeight: 800 }}>Worklist</div>
            <div style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
              Total: {mockAuths.length} · Approaching SLA (CMS 7d/72h rules) highlighted in red.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" type="button">
              New auth
            </button>
          </div>
        </div>

        <div style={{ marginTop: 10, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--ink-mute)" }}>
                <th style={{ padding: "6px 4px" }}>Patient</th>
                <th style={{ padding: "6px 4px" }}>Payer</th>
                <th style={{ padding: "6px 4px" }}>Service line</th>
                <th style={{ padding: "6px 4px" }}>Status</th>
                <th style={{ padding: "6px 4px" }}>SLA remaining</th>
                <th style={{ padding: "6px 4px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {mockAuths.map((a) => {
                const nearBreach = a.slaHoursRemaining <= 48;
                return (
                  <tr key={a.id}>
                    <td style={{ padding: "6px 4px" }}>{a.patient}</td>
                    <td style={{ padding: "6px 4px" }}>{a.payer}</td>
                    <td style={{ padding: "6px 4px" }}>{a.serviceLine}</td>
                    <td style={{ padding: "6px 4px" }}>{a.status}</td>
                    <td
                      style={{
                        padding: "6px 4px",
                        color: nearBreach ? "#b91c1c" : "inherit",
                        fontWeight: nearBreach ? 700 : 400,
                      }}
                    >
                      {a.slaHoursRemaining} h
                    </td>
                    <td style={{ padding: "6px 4px" }}>
                      <Link to={`/auths/${encodeURIComponent(a.id)}`} className="btn">
                        Open
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

