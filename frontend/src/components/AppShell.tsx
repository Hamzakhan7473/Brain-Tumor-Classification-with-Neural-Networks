import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { checkApiHealth, isFrontendApiKeyConfigured } from "../api/client";

export default function AppShell(props: { children: React.ReactNode }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [apiBanner, setApiBanner] = useState<"ok" | "down" | "need_key">("ok");

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      const h = await checkApiHealth();
      if (cancelled) return;
      if (!h.ok) {
        setApiBanner("down");
        return;
      }
      if (h.auth_required && !isFrontendApiKeyConfigured()) {
        setApiBanner("need_key");
        return;
      }
      setApiBanner("ok");
    };
    run();
    const t = window.setInterval(run, 45_000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  return (
    <>
      {apiBanner === "down" ? (
        <div
          role="status"
          style={{
            background: "rgba(251, 191, 36, 0.25)",
            borderBottom: "1px solid rgba(245, 158, 11, 0.45)",
            padding: "10px 16px",
            fontSize: 13,
            color: "var(--ink)",
          }}
        >
          <strong>Backend not reachable.</strong> Upload and reports need the API. From the project root run{" "}
          <code style={{ background: "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4 }}>./scripts/demo_local.sh</code>{" "}
          or{" "}
          <code style={{ background: "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4 }}>./scripts/run_api.sh</code>
          , then refresh this page.
        </div>
      ) : null}
      {apiBanner === "need_key" ? (
        <div
          role="status"
          style={{
            background: "rgba(96, 165, 250, 0.2)",
            borderBottom: "1px solid rgba(59, 130, 246, 0.35)",
            padding: "10px 16px",
            fontSize: 13,
            color: "var(--ink)",
          }}
        >
          <strong>API key required.</strong> The server expects <code>X-API-Key</code>. Add{" "}
          <code style={{ background: "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4 }}>VITE_API_KEY</code> to{" "}
          <code style={{ background: "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4 }}>frontend/.env</code>{" "}
          (same value as backend <code style={{ background: "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4 }}>API_KEY</code>
          ), restart <code style={{ background: "rgba(0,0,0,0.06)", padding: "2px 6px", borderRadius: 4 }}>npm run dev</code>.
        </div>
      ) : null}
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

