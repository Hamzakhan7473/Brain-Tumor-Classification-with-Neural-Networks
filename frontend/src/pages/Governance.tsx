import React from "react";

export default function Governance() {
  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Governance &amp; admin (Phase D)</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        Admin console shell for RBAC, retention, keys, and audit exploration.
      </p>

      <div className="grid2" style={{ marginTop: 14 }}>
        <div className="card">
          <div style={{ fontWeight: 800 }}>Tenants &amp; roles</div>
          <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
            Later, connect this to your auth provider and a `/admin/tenants` API.
          </p>
          <ul style={{ marginTop: 8, paddingLeft: 18, fontSize: 13, color: "var(--ink-mute)" }}>
            <li>Site-001 — Radiology pilot — Role: reader</li>
            <li>Site-002 — Research only — Role: data-science</li>
            <li>Global — Vendor — Role: admin</li>
          </ul>
        </div>

        <div className="card">
          <div style={{ fontWeight: 800 }}>Audit explorer</div>
          <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 4 }}>
            UI entrypoint for exploring `/cases`, `/metrics`, and future audit logs (JSONL or Mongo).
          </p>
          <p style={{ fontSize: 13, color: "var(--ink-mute)", marginTop: 8 }}>
            Think of this as the “compliance console” where you can show regulators how the system behaved.
          </p>
        </div>
      </div>
    </div>
  );
}

