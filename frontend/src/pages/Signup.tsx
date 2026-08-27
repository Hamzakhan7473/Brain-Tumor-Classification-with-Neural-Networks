import React, { useState } from "react";
import { AuthShell } from "../components/layout/AuthShell";
import { IosLinkButton } from "../components/ui/IosButton";

export default function Signup() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [org, setOrg] = useState("");
  const [role, setRole] = useState("Radiologist");
  const [subspecialty, setSubspecialty] = useState("General");
  const [state, setState] = useState("");
  const [agreeCompliance, setAgreeCompliance] = useState(false);

  return (
    <AuthShell>
      <h1>Sign up</h1>
      <p>
        For U.S. hospitals, imaging centers, and radiologists interested in piloting NeuroSight. For a hands-on demo,
        you can skip this form.
      </p>

      <div className="card">
        <div className="auth-actions auth-actions--top">
          <IosLinkButton to="/upload" variant="primary">
            Skip — try the demo app
          </IosLinkButton>
          <IosLinkButton to="/dashboard" variant="ghost">
            Open dashboard
          </IosLinkButton>
        </div>
        <div className="grid2">
          <div className="auth-form-grid">
            <label>
              <span>Full name</span>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Dr. First Last" />
            </label>
            <label>
              <span>Work email</span>
              <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@hospital.org" />
            </label>
            <label>
              <span>Organization</span>
              <input value={org} onChange={(e) => setOrg(e.target.value)} placeholder="Hospital / health system / practice" />
            </label>
          </div>

          <div className="auth-form-grid">
            <label>
              <span>Role</span>
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                <option>Radiologist</option>
                <option>Neuroradiologist</option>
                <option>Neurologist</option>
                <option>Technologist</option>
                <option>Administrator / Service Line Lead</option>
                <option>Informatics / CMIO team</option>
                <option>Other</option>
              </select>
            </label>
            <label>
              <span>Radiology subspecialty (optional)</span>
              <select value={subspecialty} onChange={(e) => setSubspecialty(e.target.value)}>
                <option>General</option>
                <option>Neuro</option>
                <option>Body</option>
                <option>MSK</option>
                <option>Pediatric</option>
                <option>Breast</option>
                <option>IR</option>
              </select>
            </label>
            <label>
              <span>U.S. state (optional)</span>
              <input value={state} onChange={(e) => setState(e.target.value)} placeholder="e.g. CA, NY, TX" />
            </label>
          </div>
        </div>

        <div style={{ marginTop: 14, fontSize: 13 }}>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input
              type="checkbox"
              checked={agreeCompliance}
              onChange={(e) => setAgreeCompliance(e.target.checked)}
            />
            <span>
              I confirm I am authorized to explore AI tools for my organization and understand this pilot is for{" "}
              <b>clinical evaluation and workflow design</b>, not for independent patient care decisions.
            </span>
          </label>
        </div>

        <div className="auth-actions">
          <IosLinkButton to="/dashboard" variant="primary" disabled={!agreeCompliance}>
            Create account
          </IosLinkButton>
          <IosLinkButton to="/login" variant="ghost">
            I already have an account
          </IosLinkButton>
          <IosLinkButton to="/" variant="secondary">
            Back to home
          </IosLinkButton>
        </div>

        <p className="app-text-muted" style={{ marginTop: 12, fontSize: 12 }}>
          After you sign up, our team will reach out to learn more about your radiology practice, volumes, and pilot goals.
        </p>
      </div>
    </AuthShell>
  );
}
