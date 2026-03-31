import React, { useState } from "react";
import EvidenceDrawer, { EvidenceCitation } from "../components/EvidenceDrawer";

const mockCitations: EvidenceCitation[] = [
  {
    id: "inbox-policy-1",
    title: "Portal messaging policy",
    source: "org-policy / portal-messages",
    snippet:
      "Clinical advice via portal messages should be limited to non-urgent concerns. Red-flag symptoms must be routed to phone triage or ED according to protocol.",
    score: 0.91,
  },
  {
    id: "language-policy",
    title: "Language access policy",
    source: "org-policy / language-access",
    snippet:
      "Use language-concordant communication whenever possible. For non-English messages, ensure certified interpreter resources are used when clinical decisions are involved.",
    score: 0.87,
  },
];

export default function InboxDetail() {
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);
  const [check1, setCheck1] = useState<boolean>(false);
  const [check2, setCheck2] = useState<boolean>(false);

  function onApprove() {
    if (!(check1 && check2)) return;
    alert("Message approved for send.");
  }

  return (
    <div className="container">
      <h2 style={{ marginTop: 16 }}>Inbox message · demo</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        Review an AI-drafted reply with policy-backed guardrails, similar to how you review imaging reports.
      </p>

      <div className="grid2" style={{ marginTop: 14 }}>
        <div className="card">
          <div style={{ fontWeight: 800 }}>Structured context</div>
          <div style={{ marginTop: 8, fontSize: 13, color: "var(--ink-mute)" }}>
            <div>Patient: Jane D. (MRN 12345)</div>
            <div>Subject: MRI appointment prep question</div>
            <div>Type: Clinical · Risk: low</div>
          </div>
          <div
            style={{
              marginTop: 10,
              borderRadius: 12,
              border: "1px solid var(--line)",
              padding: 10,
              fontSize: 13,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Patient message</div>
            <p style={{ color: "var(--ink)" }}>
              “Hi, I have an MRI scheduled next week. Should I stop my usual medications or not eat beforehand?”
            </p>
          </div>
        </div>

        <div className="card">
          <div style={{ fontWeight: 800 }}>Draft reply</div>
          <p style={{ marginTop: 6, fontSize: 13, color: "var(--ink-mute)" }}>
            Draft text should be grounded in chart + org policies. This is a static placeholder wired to the evidence drawer.
          </p>
          <textarea
            rows={8}
            defaultValue={
              "Thanks for your message.\n\nFor your upcoming brain MRI, you can continue your usual medications unless your ordering clinician has advised otherwise. You may eat and drink normally unless you were given specific fasting instructions for sedation or contrast.\n\nIf you have kidney problems, are pregnant, or develop new or worsening symptoms such as severe headache, weakness, or changes in vision, please contact our office or nurse triage line.\n\nThis message does not replace emergency care. If you develop severe or sudden symptoms, seek urgent care or the emergency department."
            }
            style={{ marginTop: 10 }}
          />

          <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn" type="button" onClick={() => setDrawerOpen(true)}>
              View policy evidence
            </button>
          </div>

          <div style={{ marginTop: 12, fontSize: 13, color: "var(--ink)" }}>
            <div style={{ fontWeight: 800, marginBottom: 6 }}>Safety checklist</div>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 4 }}>
              <input type="checkbox" checked={check1} onChange={(e) => setCheck1(e.target.checked)} />
              <span>Reviewed for red-flag symptoms and escalated to phone/ED pathways if present.</span>
            </label>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <input type="checkbox" checked={check2} onChange={(e) => setCheck2(e.target.checked)} />
              <span>Checked that advice is consistent with local MRI prep and language access policies.</span>
            </label>
          </div>

          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
            <button className="btnPrimary" type="button" disabled={!(check1 && check2)} onClick={onApprove}>
              Approve &amp; send
            </button>
          </div>
        </div>
      </div>

      <EvidenceDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="Inbox policies"
        citations={mockCitations}
      />
    </div>
  );
}

