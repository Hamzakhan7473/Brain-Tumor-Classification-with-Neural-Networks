import React, { useState } from "react";
import { Link } from "react-router-dom";

export default function AppShell(props: { children: React.ReactNode }) {
  const [moreOpen, setMoreOpen] = useState(false);

  return (
    <>
      <nav>
        <Link to="/dashboard" className="nav-logo">
          <img src="/genie-transparent.png" alt="NeuroSight genie" className="nav-logo-img" />
          <span className="nav-logo-text">
            Neuro<span>Sight</span>
          </span>
        </Link>

        <ul className="nav-links">
          <li>
            <Link to="/dashboard">Dashboard</Link>
          </li>
          <li>
            <Link to="/upload">Upload</Link>
          </li>
          <li>
            <Link to="/inbox">Inbox</Link>
          </li>
          <li>
            <Link to="/auths">Auths</Link>
          </li>
          <li className="nav-more">
            <button
              type="button"
              className="btn-ghost"
              onClick={() => setMoreOpen((v) => !v)}
              aria-haspopup="true"
              aria-expanded={moreOpen}
            >
              More
            </button>
            <div className="nav-more-menu" style={{ display: moreOpen ? "flex" : "none" }}>
              <Link to="/docs-assistant" onClick={() => setMoreOpen(false)}>
                Docs
              </Link>
              <Link to="/shadow-queue" onClick={() => setMoreOpen(false)}>
                Pilot &amp; ops
              </Link>
              <Link to="/report" onClick={() => setMoreOpen(false)}>
                Report
              </Link>
              <Link to="/clinical-feedback" onClick={() => setMoreOpen(false)}>
                Feedback
              </Link>
              <Link to="/agents-traces" onClick={() => setMoreOpen(false)}>
                Traces
              </Link>
            </div>
          </li>
        </ul>

        <div className="nav-actions">
          <Link to="/upload" className="btn-primary">
            New scan
          </Link>
        </div>
      </nav>

      <div className="page">{props.children}</div>
    </>
  );
}

