import React from "react";

export default function ReportComposer() {
  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Structured report composer (Phase C)</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        Template-style report drafting with sections you can later wire to the LLM and PageIndex evidence.
      </p>

      <div className="grid2" style={{ marginTop: 14 }}>
        <div className="card">
          <div style={{ fontWeight: 800 }}>Template</div>
          <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
            Use this layout for indication, findings, and impression. It mirrors the structure used in your AI-generated reports.
          </p>

          <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
            <label>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Indication</div>
              <textarea rows={2} placeholder="e.g. New onset seizures, rule out tumor" />
            </label>
            <label>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Findings</div>
              <textarea rows={4} placeholder="Describe tumor location, size, edema, mass effect…" />
            </label>
            <label>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Impression</div>
              <textarea rows={3} placeholder="Most likely diagnosis, differential, recommended follow-up…" />
            </label>
          </div>
        </div>

        <div className="card">
          <div style={{ fontWeight: 800 }}>Evidence &amp; export</div>
          <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
            This panel is designed to sit next to the Docs assistant / evidence drawer.
          </p>
          <ul style={{ marginTop: 8, paddingLeft: 18, fontSize: 13, color: "var(--ink-mute)" }}>
            <li>Show citations inline (e.g. [1], [2])</li>
            <li>Audit trail of which evidence chunks were used</li>
            <li>Buttons for “Send to RIS/PACS” (later backend)</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

