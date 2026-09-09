import React from "react";
import { AppPage } from "../components/layout/AppPage";
import { IosButton, IosLinkButton } from "../components/ui/IosButton";

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
    <AppPage
      title="Prior authorizations"
      subtitle="Queue of imaging prior authorizations with status and SLA visibility."
    >
      <div className="card">
        <div className="app-toolbar">
          <div>
            <div className="app-card-title">Worklist</div>
            <div className="app-card-sub">
              Total: {mockAuths.length} · Approaching SLA (CMS 7d/72h rules) highlighted in red.
            </div>
          </div>
          <IosButton variant="secondary">New auth</IosButton>
        </div>

        <div className="app-table-wrap">
          <table className="app-table">
            <thead>
              <tr>
                <th>Patient</th>
                <th>Payer</th>
                <th>Service line</th>
                <th>Status</th>
                <th>SLA remaining</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {mockAuths.map((a) => {
                const nearBreach = a.slaHoursRemaining <= 48;
                return (
                  <tr key={a.id}>
                    <td>{a.patient}</td>
                    <td>{a.payer}</td>
                    <td>{a.serviceLine}</td>
                    <td>{a.status}</td>
                    <td className={nearBreach ? "app-text-error" : undefined} style={{ fontWeight: nearBreach ? 700 : 400 }}>
                      {a.slaHoursRemaining} h
                    </td>
                    <td>
                      <IosLinkButton to={`/auths/${encodeURIComponent(a.id)}`} variant="secondary" size="sm">
                        Open
                      </IosLinkButton>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </AppPage>
  );
}
