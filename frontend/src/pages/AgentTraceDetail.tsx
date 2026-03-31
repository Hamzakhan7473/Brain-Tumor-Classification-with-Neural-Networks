import React, { useState } from "react";
import EvidenceDrawer, { EvidenceCitation } from "../components/EvidenceDrawer";

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
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Agent trace · demo</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        Inspect how the multi-agent swarm reached an output, step by step, with citations for chart and policy evidence.
      </p>

      <div className="grid2" style={{ marginTop: 14 }}>
        <div className="card">
          <div style={{ fontWeight: 800 }}>Steps</div>
          <ul style={{ listStyle: "none", padding: 0, marginTop: 10, fontSize: 13 }}>
            {steps.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setSelectedStep(s)}
                  style={{
                    width: "100%",
                    justifyContent: "flex-start",
                    marginBottom: 6,
                    background: selectedStep.id === s.id ? "var(--green-50)" : "var(--white)",
                  }}
                >
                  {s.label}
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <div style={{ fontWeight: 800 }}>Step detail</div>
          <p style={{ marginTop: 8, fontSize: 13, color: "var(--ink-mute)" }}>{selectedStep.summary}</p>

          <div style={{ marginTop: 12 }}>
            <button className="btn" type="button" onClick={() => setDrawerOpen(true)}>
              View evidence
            </button>
          </div>
        </div>
      </div>

      <EvidenceDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Agent evidence" citations={citations} />
    </div>
  );
}

