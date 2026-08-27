import React from "react";
import { AppPage } from "../components/layout/AppPage";
import { IosLinkButton } from "../components/ui/IosButton";

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
    <AppPage
      title="Inbox triage"
      subtitle="Message worklist for portal messages and calls. Later this will tie into EHR inbox APIs."
    >
      <div className="card">
        <div className="app-toolbar">
          <div>
            <div className="app-card-title">Queue</div>
            <div className="app-card-sub">
              Total: {mockMessages.length} · Drafted replies are reviewed before sending.
            </div>
          </div>
        </div>

        <div className="app-table-wrap">
          <table className="app-table">
            <thead>
              <tr>
                <th>Patient</th>
                <th>Subject</th>
                <th>Type</th>
                <th>Risk</th>
                <th>Age</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {mockMessages.map((m) => (
                <tr key={m.id}>
                  <td>{m.patient}</td>
                  <td>{m.subject}</td>
                  <td>{m.type}</td>
                  <td>{m.risk}</td>
                  <td>{m.ageMinutes} min</td>
                  <td>
                    <IosLinkButton to={`/inbox/${encodeURIComponent(m.id)}`} variant="secondary" size="sm">
                      Open
                    </IosLinkButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AppPage>
  );
}
