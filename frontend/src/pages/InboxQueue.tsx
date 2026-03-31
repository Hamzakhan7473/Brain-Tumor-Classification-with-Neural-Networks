import React from "react";
import { Link } from "react-router-dom";

type InboxRow = {
  id: string;
  patient: string;
  subject: string;
  type: "admin" | "clinical";
  risk: "low" | "medium" | "high";
  ageMinutes: number;
};

const mockMessages: InboxRow[] = [
  {
    id: "msg-demo-001",
    patient: "Jane D. (MRN 12345)",
    subject: "MRI appointment prep question",
    type: "clinical",
    risk: "medium",
    ageMinutes: 24,
  },
  {
    id: "msg-demo-002",
    patient: "John S. (MRN 67890)",
    subject: "Insurance / billing question",
    type: "admin",
    risk: "low",
    ageMinutes: 240,
  },
];

export default function InboxQueue() {
  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Inbox triage</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        Message worklist for portal messages and calls. Later this will tie into EHR inbox APIs.
      </p>

      <div className="card" style={{ marginTop: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
          <div>
            <div style={{ fontWeight: 800 }}>Queue</div>
            <div style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
              Total: {mockMessages.length} · Drafted replies are reviewed before sending.
            </div>
          </div>
        </div>

        <div style={{ marginTop: 10, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--ink-mute)" }}>
                <th style={{ padding: "6px 4px" }}>Patient</th>
                <th style={{ padding: "6px 4px" }}>Subject</th>
                <th style={{ padding: "6px 4px" }}>Type</th>
                <th style={{ padding: "6px 4px" }}>Risk</th>
                <th style={{ padding: "6px 4px" }}>Age</th>
                <th style={{ padding: "6px 4px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {mockMessages.map((m) => (
                <tr key={m.id}>
                  <td style={{ padding: "6px 4px" }}>{m.patient}</td>
                  <td style={{ padding: "6px 4px" }}>{m.subject}</td>
                  <td style={{ padding: "6px 4px" }}>{m.type}</td>
                  <td style={{ padding: "6px 4px" }}>{m.risk}</td>
                  <td style={{ padding: "6px 4px" }}>{m.ageMinutes} min</td>
                  <td style={{ padding: "6px 4px" }}>
                    <Link to={`/inbox/${encodeURIComponent(m.id)}`} className="btn">
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

