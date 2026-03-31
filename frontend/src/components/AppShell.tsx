import React from "react";
import { Link } from "react-router-dom";

export default function AppShell(props: { children: React.ReactNode }) {
  return (
    <>
      <nav>
        <Link to="/" className="nav-logo">
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
            <Link to="/report">Report</Link>
          </li>
          <li>
            <Link to="/clinical-feedback">Feedback</Link>
          </li>
        </ul>

        <div className="nav-actions">
          <a className="btn-ghost" href="/docs" onClick={(e) => e.preventDefault()}>
            Docs
          </a>
          <Link to="/upload" className="btn-primary">
            New scan
          </Link>
        </div>
      </nav>

      <div className="page">{props.children}</div>
    </>
  );
}

