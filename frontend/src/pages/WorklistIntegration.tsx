import React from "react";

export default function WorklistIntegration() {
  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Worklist integration (Phase D)</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        PACS-like worklist shell for mapping accessions / study UIDs to AI cases.
      </p>

      <div className="card" style={{ marginTop: 14 }}>
        <div style={{ fontWeight: 800 }}>Integrated worklist</div>
        <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
          Later, this can be driven by an `/worklist` API backed by your RIS/PACS integration.
        </p>

        <div style={{ marginTop: 10, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--ink-mute)" }}>
                <th style={{ padding: "6px 4px" }}>Accession</th>
                <th style={{ padding: "6px 4px" }}>Study UID</th>
                <th style={{ padding: "6px 4px" }}>Patient</th>
                <th style={{ padding: "6px 4px" }}>Site</th>
                <th style={{ padding: "6px 4px" }}>AI status</th>
                <th style={{ padding: "6px 4px" }}>Result</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: "6px 4px" }}>ACC-12345</td>
                <td style={{ padding: "6px 4px" }}>demo-worklist-001</td>
                <td style={{ padding: "6px 4px" }}>Jane D.</td>
                <td style={{ padding: "6px 4px" }}>site-001</td>
                <td style={{ padding: "6px 4px" }}>AI ready</td>
                <td style={{ padding: "6px 4px" }}>glioma (0.92)</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

