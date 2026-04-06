import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { checkApiHealth, fetchPublicFeatures, type PublicFeature } from "../api/client";

const FALLBACK_FEATURES: PublicFeature[] = [
  {
    id: "shadow-mode",
    title: "Shadow-mode ready",
    description:
      "Every prediction can be run in shadow mode with study UID and site ID, so you can audit performance before AI impacts clinical decisions.",
    available: true,
  },
  {
    id: "clinical-feedback",
    title: "Feedback at the point of read",
    description:
      "Simple agree / correct / unclear flow with optional corrected class and reasons, wired into dashboards and safety views.",
    available: true,
  },
  {
    id: "report-drafts",
    title: "Report drafts with evidence",
    description:
      "Drafts are designed to sit next to your structured templates, with an evidence drawer to show what the model was grounded on.",
    available: true,
  },
  {
    id: "agent-traces",
    title: "Agent traces",
    description:
      "A dedicated view for seeing how AI assistants worked together on a case – evidence retrieved, policies checked, and decisions proposed.",
    available: true,
  },
];

export default function MarketingLanding() {
  const [featureItems, setFeatureItems] = useState<PublicFeature[]>(FALLBACK_FEATURES);
  const [featuresLoaded, setFeaturesLoaded] = useState(false);
  const [apiVersion, setApiVersion] = useState<string | null>(null);
  const [apiReachable, setApiReachable] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const data = await fetchPublicFeatures();
      if (cancelled || !data?.features?.length) return;
      setFeatureItems(data.features);
      setApiVersion(data.version);
      setFeaturesLoaded(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const h = await checkApiHealth();
      if (!cancelled) setApiReachable(h.ok);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      {import.meta.env.DEV && apiReachable === false ? (
        <div
          role="status"
          style={{
            background: "rgba(251, 191, 36, 0.22)",
            borderBottom: "1px solid rgba(245, 158, 11, 0.4)",
            padding: "8px 16px",
            fontSize: 12,
            textAlign: "center",
            color: "var(--ink)",
          }}
        >
          Demo tip: start the API so Upload and Features stay in sync —{" "}
          <code style={{ background: "rgba(0,0,0,0.06)", padding: "1px 6px", borderRadius: 4 }}>./scripts/demo_local.sh</code>
        </div>
      ) : null}
      <nav>
        <Link to="/" className="nav-logo">
          <img src="/genie-transparent.png" alt="NeuroSight genie" className="nav-logo-img" />
          <span className="nav-logo-text">
            Neuro<span>Sight</span>
          </span>
        </Link>
        <ul className="nav-links">
          <li>
            <a href="#workflow">Workflow</a>
          </li>
          <li>
            <a href="#features">Features</a>
          </li>
          <li>
            <a href="#phases">Clinical phases</a>
          </li>
          <li>
            <a href="#pricing">Pricing</a>
          </li>
        </ul>
        <div className="nav-actions">
          <Link to="/upload" className="btn-ghost">
            Live demo
          </Link>
          <Link to="/login" className="btn-ghost">
            Log in
          </Link>
          <Link to="/signup" className="btn-primary">
            Get started
          </Link>
        </div>
      </nav>

      <main>
        <section className="hero">
          <div className="hero-left">
            <div className="hero-eyebrow">Brain MRI AI · Built for radiology teams</div>
            <h1 className="hero-heading">
              NeuroSight turns <em>single-slice</em> brain MRI into a structured AI read.
            </h1>
            <p className="hero-sub">
              Upload a scan, run your tumor classifier, and get a saliency-backed read with report suggestions – all in
              a workflow designed for real radiology reading rooms.
            </p>
            <div className="hero-cta-row">
              <Link to="/upload" className="btn-large">
                Upload &amp; predict
              </Link>
              <Link to="/clinical-feedback" className="btn-large-outline">
                Clinical feedback mode
              </Link>
            </div>
            <div className="hero-trust">
              <div className="trust-item">
                <span className="trust-check">✓</span> Shadow-mode logging with case IDs and site tags
              </div>
              <div className="trust-item">
                <span className="trust-check">✓</span> Secure, cloud-ready deployment path
              </div>
            </div>
          </div>

          <div className="hero-right">
            <div className="genie-wrap">
              <img src="/genie-transparent.png" alt="NeuroSight genie" />
            </div>
            <div className="hero-card">
              <div className="hero-card-title">NeuroSight — Brain MRI AI</div>
              <div className="hero-card-sub">
                Classifies glioma, meningioma, pituitary, and no-tumor with saliency maps and structured report
                templates – ready for design-partner pilots.
              </div>
            </div>
          </div>
        </section>

        <section id="workflow" className="container" style={{ paddingTop: 48 }}>
          <div className="card">
            <h3 style={{ marginTop: 0, marginBottom: 8 }}>How NeuroSight fits your day</h3>
            <p style={{ color: "var(--ink-mute)", marginBottom: 16 }}>
              From first scan to final sign-off, NeuroSight keeps the AI in the loop and the clinician in control.
            </p>
            <div className="grid2">
              <div>
                <ol style={{ paddingLeft: 18, fontSize: 14, color: "var(--ink)" }}>
                  <li style={{ marginBottom: 8 }}>
                    <b>Upload &amp; classify</b> · Single-slice brain MRI via web or DICOM, with model selection and
                    shadow mode toggle.
                  </li>
                  <li style={{ marginBottom: 8 }}>
                    <b>Review AI read</b> · Tumor vs no-tumor prediction, confidence bars, and saliency-style overlay.
                  </li>
                  <li style={{ marginBottom: 8 }}>
                    <b>Draft report</b> · LLM-generated report text grounded in your model output and knowledge base.
                  </li>
                  <li style={{ marginBottom: 8 }}>
                    <b>Collect feedback</b> · Radiologists mark agree / correct / unclear, with reasons and notes.
                  </li>
                  <li>
                    <b>Close the loop</b> · Cases flow into dashboards, shadow queues, and safety views for monitoring.
                  </li>
                </ol>
              </div>
              <div>
                <div className="card" style={{ padding: 14 }}>
                  <div style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.08, color: "var(--ink-mute)" }}>
                    Live demo
                  </div>
                  <p style={{ marginTop: 6, fontSize: 14, color: "var(--ink-mute)" }}>
                    Try the full workflow in the app: upload, run the model, review the report, and leave feedback – all
                    from a browser.
                  </p>
                  <Link to="/upload" className="btn-primary" style={{ marginTop: 8, display: "inline-flex" }}>
                    Start with a scan
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="features" className="container" style={{ paddingTop: 32 }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
            <h3 style={{ marginBottom: 0 }}>Built for real radiology teams</h3>
            {featuresLoaded && apiVersion ? (
              <span style={{ fontSize: 12, color: "var(--ink-mute)" }}>API v{apiVersion}</span>
            ) : null}
          </div>
          <div className="grid2" style={{ marginTop: 10 }}>
            {featureItems.map((f) => (
              <div key={f.id} className="card">
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
                  <div style={{ fontWeight: 800, marginBottom: 4 }}>{f.title}</div>
                  <span
                    title={f.available ? "Enabled on this API deployment" : "Requires configuration on the server"}
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      textTransform: "uppercase",
                      letterSpacing: 0.06,
                      color: f.available ? "var(--accent, #0d9488)" : "var(--ink-mute)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {f.available ? "Live" : "Setup"}
                  </span>
                </div>
                <p style={{ fontSize: 14, color: "var(--ink-mute)", marginBottom: 0 }}>{f.description}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="phases" className="container" style={{ paddingTop: 32 }}>
          <h3 style={{ marginBottom: 10 }}>From research to clinical rollout</h3>
          <div className="grid2">
            <div className="card">
              <div style={{ fontWeight: 800 }}>Phase A · Design partner</div>
              <p style={{ fontSize: 14, color: "var(--ink-mute)", marginTop: 4 }}>
                Use NeuroSight as a design-partner console: upload scans, review AI reads, collect feedback, and export
                cases for analysis.
              </p>
            </div>
            <div className="card">
              <div style={{ fontWeight: 800 }}>Phase B · Shadow mode</div>
              <p style={{ fontSize: 14, color: "var(--ink-mute)", marginTop: 4 }}>
                Turn on automated queues and ops views that track how the model performs in the background without
                changing care.
              </p>
            </div>
            <div className="card">
              <div style={{ fontWeight: 800 }}>Phase C · Assistive pre-read</div>
              <p style={{ fontSize: 14, color: "var(--ink-mute)", marginTop: 4 }}>
                Let radiologists reveal AI suggestions inside a gated reading mode, with checklists before final sign-off.
              </p>
            </div>
            <div className="card">
              <div style={{ fontWeight: 800 }}>Phase D · Integrated</div>
              <p style={{ fontSize: 14, color: "var(--ink-mute)", marginTop: 4 }}>
                Connect into PACS/RIS/EHR worklists using your existing integration strategy while keeping provenance and
                audit traces visible.
              </p>
            </div>
          </div>
        </section>

        <section id="pricing" className="container" style={{ paddingTop: 32, paddingBottom: 40 }}>
          <div className="card">
            <h3 style={{ marginTop: 0, marginBottom: 8 }}>Start as a design partner</h3>
            <p style={{ fontSize: 14, color: "var(--ink-mute)", marginBottom: 12 }}>
              NeuroSight is built to start small with a research/design partner and grow into a production deployment.
              The goal is to prove value with real workflows before committing to a large program.
            </p>
            <ul style={{ paddingLeft: 18, fontSize: 14, color: "var(--ink-mute)" }}>
              <li>Design-partner pilots with a limited number of radiologists and sites.</li>
              <li>Clear path to volume-based or per-site pricing once metrics are in place.</li>
            </ul>
            <div style={{ marginTop: 12 }}>
              <Link to="/upload" className="btn-primary">
                Explore the app
              </Link>
            </div>
          </div>
        </section>
      </main>
    </>
  );
}

