import React, { useState } from "react";
import EvidenceDrawer, { EvidenceCitation } from "../components/EvidenceDrawer";
import { AppPage } from "../components/layout/AppPage";
import { IosButton } from "../components/ui/IosButton";

type Step = {
  id: string;
  label: string;
  summary: string;
};

const steps: Step[] = [
  {
    id: "orchestrator",
    label: "Orchestrator",
    summary: "Initialized prior auth workflow state and loaded case context.",
  },
  {
    id: "chart",
    label: "Chart Evidence Retriever",
    summary: "Pulled problems, prior imaging, and neurology notes via FHIR.",
  },
  {
    id: "policy",
    label: "Guideline/Policy Agent",
    summary: "Found payer policy and DTR fields for brain MRI prior auth.",
  },
  {
    id: "risk",
    label: "Risk Triage",
    summary: "Verified no red-flag symptoms or unsafe intents.",
  },
  {
    id: "comm",
    label: "Communication Agent",
    summary: "Drafted explanation for staff-facing or patient-facing communication.",
  },
];

const citations: EvidenceCitation[] = [
  {
    id: "trace-evidence-1",
    title: "Chart evidence bundle",
    source: "FHIR: Condition/Observation/DiagnosticReport",
    snippet:
      "Pulled: epilepsy diagnosis (ICD-10 G40), prior CT head (no mass), and neurology consult note describing breakthrough seizures despite meds.",
    score: 0.9,
  },
  {
    id: "trace-policy-1",
    title: "Payer MRI policy snippet",
    source: "Payer policy · Brain MRI",
    snippet:
      "Coverage when: (1) documented failure of conservative therapy, (2) new or worsening neurologic signs, (3) prior imaging inconclusive or outdated.",
    score: 0.88,
  },
];

export default function AgentTraceDetail() {
  const [selectedStep, setSelectedStep] = useState<Step>(steps[0]);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

  return (
    <AppPage
      title="Agent trace"
      subtitle="Inspect how the multi-agent swarm reached an output, step by step, with citations for chart and policy evidence."
    >
      <div className="app-grid-2">
        <div className="card">
          <div className="app-card-title">Steps</div>
          <ul style={{ listStyle: "none", padding: 0, marginTop: 10, fontSize: 13 }}>
            {steps.map((s) => (
              <li key={s.id}>
                <IosButton
                  variant="secondary"
                  fullWidth
                  onClick={() => setSelectedStep(s)}
                  className={selectedStep.id === s.id ? "app-list-item--selected" : ""}
                  style={{ justifyContent: "flex-start", marginBottom: 6 }}
                >
                  {s.label}
                </IosButton>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <div className="app-card-title">Step detail</div>
          <p className="app-card-sub" style={{ marginTop: 8 }}>{selectedStep.summary}</p>

          <div style={{ marginTop: 12 }}>
            <IosButton variant="secondary" onClick={() => setDrawerOpen(true)}>
              View evidence
            </IosButton>
          </div>
        </div>
      </div>

      <EvidenceDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Agent evidence" citations={citations} />
    </AppPage>
  );
}
