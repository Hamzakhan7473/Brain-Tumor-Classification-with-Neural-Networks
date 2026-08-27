import React from "react";
import { AppPage } from "../components/layout/AppPage";
import { IosLinkButton } from "../components/ui/IosButton";

type AgentTraceRow = {
  id: string;
  workflow: string;
  status: "success" | "error";
  risk: "low" | "medium" | "high";
  createdAt: string;
};

const mockTraces: AgentTraceRow[] = [
  {
    id: "trace-auth-001",
    workflow: "Prior auth · Brain MRI",
    status: "success",
    risk: "medium",
    createdAt: "Just now",
  },
  {
    id: "trace-inbox-001",
    workflow: "Inbox · MRI prep question",
    status: "success",
    risk: "low",
    createdAt: "5 min ago",
  },
];

export default function AgentTracesQueue() {
  return (
    <AppPage
      title="Agent traces"
      subtitle="Multi-agent runs for workflows like auths, inbox, and discharge follow-up. Designed for audit and safety review."
    >
      <div className="card">
        <div className="app-toolbar">
          <div>
            <div className="app-card-title">Runs</div>
            <div className="app-card-sub">
              Total: {mockTraces.length}. Each run shows how the AI assistants worked together on a case.
            </div>
          </div>
        </div>

        <div className="app-table-wrap">
          <table className="app-table">
            <thead>
              <tr>
                <th>Workflow</th>
                <th>Status</th>
                <th>Risk</th>
                <th>Started</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {mockTraces.map((t) => (
                <tr key={t.id}>
                  <td>{t.workflow}</td>
                  <td>{t.status}</td>
                  <td>{t.risk}</td>
                  <td>{t.createdAt}</td>
                  <td>
                    <IosLinkButton to={`/agents-traces/${encodeURIComponent(t.id)}`} variant="secondary" size="sm">
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
