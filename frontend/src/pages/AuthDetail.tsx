import React, { useState } from "react";
import EvidenceDrawer, { EvidenceCitation } from "../components/EvidenceDrawer";
import { AppPage } from "../components/layout/AppPage";
import { IosButton } from "../components/ui/IosButton";

const mockCitations: EvidenceCitation[] = [
  {
    id: "cms-0057f",
    title: "CMS-0057-F Prior Auth API rule",
    source: "cms.gov / rule / CMS-0057-F",
    snippet:
      "CMS-0057-F requires certain payers to implement a standards-based Prior Authorization API and adhere to specific timeframes, such as 7 days for standard requests.",
    score: 0.92,
  },
  {
    id: "dv-crd",
    title: "HL7 Da Vinci CRD",
    source: "hl7.org / Da Vinci / CRD",
    snippet:
      "The Coverage Requirements Discovery (CRD) IG defines how a SMART-on-FHIR app can discover whether prior authorization is required for a given order.",
    score: 0.88,
  },
];

export default function AuthDetail() {
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);
  const [check1, setCheck1] = useState<boolean>(false);
  const [check2, setCheck2] = useState<boolean>(false);
  const [check3, setCheck3] = useState<boolean>(false);
  const allChecked = check1 && check2 && check3;

  function onMarkReady() {
    if (!allChecked) return;
    alert("Marked auth packet as ready to submit.");
  }

  return (
    <AppPage
      title="Prior authorization"
      subtitle="Packet-style report for a brain MRI prior authorization. Context + AI-assisted draft + evidence."
    >
      <div className="app-grid-2">
        <div className="card">
          <div className="app-card-title">Structured context</div>
          <div className="app-text-muted" style={{ marginTop: 8, fontSize: 13 }}>
            <div>Patient: Jane D. (MRN 12345)</div>
            <div>Order: Brain MRI w/wo contrast</div>
            <div>Payer: Medicare Advantage</div>
            <div>Urgency: Standard (CMS 7d SLA)</div>
          </div>
          <div className="app-text-muted" style={{ marginTop: 10, fontSize: 13 }}>
            <b>Coverage requirements (CRD-style)</b>
            <ul style={{ marginTop: 4, paddingLeft: 18 }}>
              <li>Conservative therapy tried and failed (document yes/no with duration).</li>
              <li>Symptoms and neuro exam findings documented in note.</li>
              <li>Prior imaging and neurologist consult summarized.</li>
            </ul>
          </div>
        </div>

        <div className="card">
          <div className="app-card-title">Auth packet draft</div>
          <p className="app-card-sub">
            Draft text that combines chart information and payer criteria into a clear prior authorization packet.
          </p>
          <textarea
            rows={8}
            defaultValue={
              "Indication: Patient with breakthrough seizures despite optimized anti-epileptic regimen. Concern for structural lesion.\n\nConservative therapy: On levetiracetam with therapeutic levels for 6 months; seizure frequency increased over last 8 weeks despite dose titration.\n\nPrior imaging/consults: CT head 8 months ago without mass or acute findings. Neurology consult recommends brain MRI w/wo contrast to evaluate for underlying lesion or progression."
            }
            style={{ marginTop: 10, width: "100%" }}
          />
          <div style={{ marginTop: 10 }}>
            <IosButton variant="secondary" onClick={() => setDrawerOpen(true)}>
              View policy evidence
            </IosButton>
          </div>

          <div style={{ marginTop: 12, fontSize: 13 }}>
            <div className="app-card-title" style={{ marginBottom: 6 }}>Sign-off checklist</div>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 4 }}>
              <input type="checkbox" checked={check1} onChange={(e) => setCheck1(e.target.checked)} />
              <span>Conservative therapy and neurologic symptoms are documented and consistent with payer criteria.</span>
            </label>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 4 }}>
              <input type="checkbox" checked={check2} onChange={(e) => setCheck2(e.target.checked)} />
              <span>Prior imaging/consults are summarized accurately from the chart.</span>
            </label>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <input type="checkbox" checked={check3} onChange={(e) => setCheck3(e.target.checked)} />
              <span>AI text has been reviewed and edited as needed before submission.</span>
            </label>
          </div>

          <div style={{ marginTop: 12 }}>
            <IosButton variant="primary" disabled={!allChecked} onClick={onMarkReady}>
              Mark ready to submit
            </IosButton>
          </div>
        </div>
      </div>

      <EvidenceDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Prior auth policies" citations={mockCitations} />
    </AppPage>
  );
}
