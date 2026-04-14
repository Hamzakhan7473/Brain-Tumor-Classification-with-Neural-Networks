import React, { useState } from "react";
import { Link } from "react-router-dom";

export default function Signup() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [org, setOrg] = useState("");
  const [role, setRole] = useState("Radiologist");
  const [subspecialty, setSubspecialty] = useState("General");
  const [state, setState] = useState("");
  const [agreeCompliance, setAgreeCompliance] = useState(false);

  return (
    <div className="container" style={{ maxWidth: 840 }}>
      <h2 style={{ marginTop: 16 }}>Sign up</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        For U.S. hospitals, imaging centers, and radiologists interested in piloting NeuroSight. For a hands-on demo,
        you can skip this form.
      </p>

      <div className="card" style={{ marginTop: 14 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
          <Link to="/upload" className="btn-primary">
            Skip — try the demo app
          </Link>
          <Link to="/dashboard" className="btn btnOutline">
            Open dashboard
          </Link>
        </div>
        <div className="grid2">
          <div style={{ display: "grid", gap: 10 }}>
            <label>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>Full name</div>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Dr. First Last" />
            </label>
            <label>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>Work email</div>
              <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@hospital.org" />
            </label>
            <label>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>Organization</div>
              <input value={org} onChange={(e) => setOrg(e.target.value)} placeholder="Hospital / health system / practice" />
            </label>
          </div>

          <div style={{ display: "grid", gap: 10 }}>
            <label>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>Role</div>
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
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>Radiology subspecialty (optional)</div>
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
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>U.S. state (optional)</div>
              <input value={state} onChange={(e) => setState(e.target.value)} placeholder="e.g. CA, NY, TX" />
            </label>
          </div>
        </div>

        <div style={{ marginTop: 14, fontSize: 13, color: "var(--ink)" }}>
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

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 16 }}>
          <Link to="/dashboard" className="btn-primary" aria-disabled={!agreeCompliance}>
            Create account
          </Link>
          <Link to="/login" className="btn btnOutline">
            I already have an account
          </Link>
          <Link to="/" className="btn">
            Back to home
          </Link>
        </div>

        <p style={{ marginTop: 10, fontSize: 12, color: "var(--ink-mute)" }}>
          After you sign up, our team will reach out to learn more about your radiology practice, volumes, and pilot goals.
        </p>
      </div>
    </div>
  );
}

