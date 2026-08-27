import React from "react";
import { Link } from "react-router-dom";
import { IosLinkButton } from "../ui/IosButton";
import { ThemeToggle } from "./ThemeToggle";

type IosNavBarProps = {
  moreOpen: boolean;
  setMoreOpen: (v: boolean | ((prev: boolean) => boolean)) => void;
  onOpenCommandPalette: () => void;
};

export function IosNavBar({ moreOpen, setMoreOpen, onOpenCommandPalette }: IosNavBarProps): React.ReactElement {
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

      <div className="nav-actions" style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button type="button" className="cmdk-trigger min-tap-target ios-hide-narrow-nav" onClick={onOpenCommandPalette}>
          <span className="cmdk-trigger-label">Search</span>
          <kbd className="cmdk-trigger-kbd">⌘K</kbd>
        </button>
        <ThemeToggle />
        <span className="text-ios-caption2 font-semibold font-ios ios-hide-narrow-nav app-modern-badge">Research only</span>
        <IosLinkButton to="/upload" variant="primary" className="min-tap-target">
          New scan
        </IosLinkButton>
      </div>
    </nav>
  );
}
