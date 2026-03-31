import React, { useState } from "react";
import { Link } from "react-router-dom";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  return (
    <div className="container" style={{ maxWidth: 720 }}>
      <h2 style={{ marginTop: 16 }}>Log in</h2>
      <p style={{ color: "var(--ink-mute)", marginTop: 4 }}>
        Access your NeuroSight dashboard.
      </p>

      <div className="card" style={{ marginTop: 14 }}>
        <div style={{ display: "grid", gap: 10 }}>
          <label>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>Email</div>
            <input
              type="text"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@hospital.org"
            />
          </label>
          <label>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>Password</div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </label>
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 14 }}>
          <Link to="/dashboard" className="btn-primary">
            Log in
          </Link>
          <Link to="/signup" className="btn btnOutline">
            Create account
          </Link>
          <Link to="/" className="btn">
            Back to home
          </Link>
        </div>

        <p style={{ marginTop: 10, fontSize: 12, color: "var(--ink-mute)" }}>
          Use your hospital or pilot credentials to access NeuroSight.
        </p>
      </div>
    </div>
  );
}

