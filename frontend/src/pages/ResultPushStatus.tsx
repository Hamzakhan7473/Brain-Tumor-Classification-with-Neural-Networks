import React from "react";

export default function ResultPushStatus() {
  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Result push status (Phase D)</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        Monitor whether AI results were successfully pushed to EHR/PACS and when retries are needed.
      </p>

      <div className="card" style={{ marginTop: 14 }}>
        <div style={{ fontWeight: 800 }}>Delivery log</div>
        <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
          Later, back this with a dedicated `/result-push` or audit endpoint.
        </p>

        <div style={{ marginTop: 10, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--ink-mute)" }}>
                <th style={{ padding: "6px 4px" }}>Study UID</th>
                <th style={{ padding: "6px 4px" }}>Destination</th>
                <th style={{ padding: "6px 4px" }}>Status</th>
                <th style={{ padding: "6px 4px" }}>Last attempt</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: "6px 4px" }}>demo-worklist-001</td>
                <td style={{ padding: "6px 4px" }}>EHR / HL7</td>
                <td style={{ padding: "6px 4px" }}>sent</td>
                <td style={{ padding: "6px 4px" }}>just now (demo)</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

