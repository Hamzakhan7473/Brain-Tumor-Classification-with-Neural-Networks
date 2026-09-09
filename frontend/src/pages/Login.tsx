import React, { useState } from "react";
import { AuthShell } from "../components/layout/AuthShell";
import { IosLinkButton } from "../components/ui/IosButton";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  return (
    <AuthShell>
      <h1>Log in</h1>
      <p>For live demos, sign-in is optional — use the button below to enter the app immediately.</p>

      <div className="card">
        <div className="auth-actions auth-actions--top">
          <IosLinkButton to="/upload" variant="primary">
            Try demo — upload a scan
          </IosLinkButton>
          <IosLinkButton to="/dashboard" variant="ghost">
            Open dashboard
          </IosLinkButton>
        </div>
        <div className="app-section-label">Optional (placeholder) credentials</div>
        <div className="auth-form-grid">
          <label>
            <span>Email</span>
            <input
              type="text"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@hospital.org"
            />
          </label>
          <label>
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </label>
        </div>

        <div className="auth-actions">
          <IosLinkButton to="/dashboard" variant="secondary">
            Log in (same as open dashboard)
          </IosLinkButton>
          <IosLinkButton to="/signup" variant="ghost">
            Sign up form
          </IosLinkButton>
          <IosLinkButton to="/" variant="secondary">
            Back to home
          </IosLinkButton>
        </div>

        <p className="app-text-muted" style={{ marginTop: 12, fontSize: 12 }}>
          Hospital SSO and real accounts can be wired later; this build is optimized for guided demos.
        </p>
      </div>
    </AuthShell>
  );
}
