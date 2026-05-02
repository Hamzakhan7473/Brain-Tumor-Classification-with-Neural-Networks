/**
 * Navbar colors from global.css :root:
 *   surface wash: color-mix with --surface
 *   border bottom: --line
 *   primary text/logo: --ink, span accent --green-600 (existing .nav-logo-text)
 *   warning pill: bg --green-50, border --green-300, text --green-700
 */

import React from "react";
import { Link } from "react-router-dom";

type IosNavBarProps = {
  moreOpen: boolean;
  setMoreOpen: (v: boolean | ((prev: boolean) => boolean)) => void;
};

export function IosNavBar({ moreOpen, setMoreOpen }: IosNavBarProps): React.ReactElement {
  return (
    <nav>
      <Link to="/dashboard" className="nav-logo min-tap-target" style={{ minHeight: "var(--tap-min)" }}>
        <img src="/genie-transparent.png" alt="NeuroSight genie" className="nav-logo-img" />
        <span className="nav-logo-text text-ios-body font-semibold" style={{ letterSpacing: "-0.02em" }}>
          Neuro<span>Sight</span>
        </span>
      </Link>

      <ul className="nav-links">
        <li>
          <Link to="/dashboard" className="min-tap-target" style={{ display: "inline-flex", alignItems: "center" }}>
            Dashboard
          </Link>
        </li>
        <li>
          <Link to="/upload" className="min-tap-target" style={{ display: "inline-flex", alignItems: "center" }}>
            Upload
          </Link>
        </li>
        <li>
          <Link to="/inbox" className="min-tap-target" style={{ display: "inline-flex", alignItems: "center" }}>
            Inbox
          </Link>
        </li>
        <li>
          <Link to="/auths" className="min-tap-target" style={{ display: "inline-flex", alignItems: "center" }}>
            Auths
          </Link>
        </li>
        <li className="nav-more">
          <button
            type="button"
            className="btn-ghost min-tap-target"
            onClick={() => setMoreOpen((v) => !v)}
            aria-haspopup="true"
            aria-expanded={moreOpen}
            style={{ minWidth: "var(--tap-min)" }}
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

      <div className="nav-actions" style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span
          className="text-ios-caption2 font-semibold font-ios ios-hide-narrow-nav"
          style={{
            padding: "4px 12px",
            borderRadius: 999,
            border: "1px solid var(--green-300)",
            background: "var(--green-50)",
            color: "var(--green-700)",
            whiteSpace: "nowrap",
          }}
        >
          Research only
        </span>
        <Link to="/upload" className="btn-primary min-tap-target" style={{ display: "inline-flex", alignItems: "center" }}>
          New scan
        </Link>
      </div>
    </nav>
  );
}
