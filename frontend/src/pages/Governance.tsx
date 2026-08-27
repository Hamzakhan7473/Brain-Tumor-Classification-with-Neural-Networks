import React from "react";
import { AppPage } from "../components/layout/AppPage";

export default function Governance() {
  return (
    <AppPage
      title="Governance & admin"
      subtitle="Admin console shell for RBAC, retention, keys, and audit exploration."
    >
      <div className="app-grid-2">
        <div className="card">
          <div className="app-card-title">Tenants &amp; roles</div>
          <p className="app-card-sub">
            Later, connect this to your auth provider and a <code>/admin/tenants</code> API.
          </p>
          <ul className="app-text-muted" style={{ marginTop: 8, paddingLeft: 18, fontSize: 13 }}>
            <li>Site-001 — Radiology pilot — Role: reader</li>
            <li>Site-002 — Research only — Role: data-science</li>
            <li>Global — Vendor — Role: admin</li>
          </ul>
        </div>

        <div className="card">
          <div className="app-card-title">Audit explorer</div>
          <p className="app-card-sub">
            UI entrypoint for exploring <code>/cases</code>, <code>/metrics</code>, and future audit logs.
          </p>
          <p className="app-text-muted" style={{ marginTop: 8, fontSize: 13 }}>
            Think of this as the compliance console where you can show regulators how the system behaved.
          </p>
        </div>
      </div>
    </AppPage>
  );
}
