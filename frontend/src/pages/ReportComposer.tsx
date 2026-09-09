import React from "react";
import { AppPage } from "../components/layout/AppPage";

export default function ReportComposer() {
  return (
    <AppPage
      title="Structured report composer"
      subtitle="Template-style report drafting with sections you can wire to the LLM and PageIndex evidence."
    >
      <div className="app-grid-2">
        <div className="card">
          <div className="app-card-title">Template</div>
          <p className="app-card-sub">
            Use this layout for indication, findings, and impression. It mirrors the structure used in AI-generated reports.
          </p>

          <div className="auth-form-grid" style={{ marginTop: 10 }}>
            <label>
              <span>Indication</span>
              <textarea rows={2} placeholder="e.g. New onset seizures, rule out tumor" />
            </label>
            <label>
              <span>Findings</span>
              <textarea rows={4} placeholder="Describe tumor location, size, edema, mass effect…" />
            </label>
            <label>
              <span>Impression</span>
              <textarea rows={3} placeholder="Most likely diagnosis, differential, recommended follow-up…" />
            </label>
          </div>
        </div>

        <div className="card">
          <div className="app-card-title">Evidence &amp; export</div>
          <p className="app-card-sub">
            This panel is designed to sit next to the Docs assistant / evidence drawer.
          </p>
          <ul className="app-text-muted" style={{ marginTop: 8, paddingLeft: 18, fontSize: 13 }}>
            <li>Show citations inline (e.g. [1], [2])</li>
            <li>Audit trail of which evidence chunks were used</li>
            <li>Buttons for “Send to RIS/PACS” (later backend)</li>
          </ul>
        </div>
      </div>
    </AppPage>
  );
}
