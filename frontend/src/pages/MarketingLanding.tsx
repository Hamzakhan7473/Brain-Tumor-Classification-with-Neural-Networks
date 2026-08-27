import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { checkApiHealth, fetchPublicFeatures, type PublicFeature } from "../api/client";
import { IosSymbol } from "../components/ui/IosSymbol";
import { APP_WORKFLOW_TILES, GlassTilePanel } from "../components/ui/GlassTilePanel";
import "./MarketingLanding.css";

const FALLBACK_FEATURES: PublicFeature[] = [
  {
    id: "wmh-segmentation",
    title: "WMH regional volumes",
    description:
      "3D segmentation with periventricular, deep, and infratentorial volumes — structured for trial endpoints.",
    available: true,
  },
  {
    id: "bicr-workflow",
    title: "BICR dual-read workflow",
    description:
      "Independent reader slots, adjudication on disagreement, time-point lock, and Part 11-style e-signatures.",
    available: true,
  },
  {
    id: "report-drafts",
    title: "Structured reports + PDF",
    description:
      "RSNA-style draft reports with longitudinal comparison, normative percentiles, and signed PDF export.",
    available: true,
  },
  {
    id: "shadow-mode",
    title: "Shadow-mode audit trail",
    description:
      "Every inference logged with study UID, site ID, and immutable audit IDs — ready for core-lab validation.",
    available: true,
  },
];

const TRIO = [
  {
    symbol: "chart.bar" as const,
    title: "Measure",
    caption: "Regional WMH volumes — periventricular, deep, and infratentorial cc for trial endpoints.",
    gradient: "linear-gradient(160deg, #22d3ee 0%, #0e7490 48%, #083344 100%)",
  },
  {
    symbol: "eye" as const,
    title: "Review",
    caption: "BICR dual-read workflow with blinded reads, adjudication, and time-point locking.",
    gradient: "linear-gradient(160deg, #a78bfa 0%, #6d28d9 50%, #2e1065 100%)",
  },
  {
    symbol: "doc.text" as const,
    title: "Sign",
    caption: "Structured PDF reports with longitudinal deltas and signed audit hashes.",
    gradient: "linear-gradient(160deg, #f0abfc 0%, #c026d3 48%, #4a044e 100%)",
  },
];

const STORIES = [
  {
    quote:
      "Regional WMH volumes replaced subjective Fazekas grading in our MS sub-study — reviewers finally had numbers they could reconcile.",
    name: "Imaging core lab lead",
    place: "Academic trial site",
  },
  {
    quote:
      "Dual-read with adjudication cut our reconciliation meetings in half. The blinded reader UI kept us honest.",
    name: "Central reader",
    place: "CRO imaging hub",
  },
  {
    quote:
      "Structured PDFs with audit hashes gave our sponsor something inspection-ready without a full PACS integration.",
    name: "Clinical operations",
    place: "Biotech sponsor",
  },
];

const STAGES = [
  {
    tag: "Stage 1",
    title: "Quantitative WMH report",
    body: "Regional volumes, longitudinal comparison, structured PDF — the flagship trial artifact.",
  },
  {
    tag: "Stage 2",
    title: "BICR reader workflow",
    body: "Dual independent reads, adjudication, time-point lock, and Part 11 e-signatures.",
  },
  {
    tag: "Phase B",
    title: "Shadow mode",
    body: "Background inference queues and ops views without changing standard-of-care decisions.",
  },
  {
    tag: "Phase D",
    title: "PACS integration",
    body: "DICOM SR delivery and worklist hooks once analytic validity is proven with a design partner.",
  },
];

const PREVIEW_ROWS = [
  { label: "Total WMH burden", value: "14.2 cc", pct: 78 },
  { label: "Periventricular", value: "8.1 cc", pct: 62 },
  { label: "Deep white matter", value: "5.3 cc", pct: 44 },
  { label: "Infratentorial", value: "0.8 cc", pct: 12 },
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
    <div className="nsl-landing">
      {import.meta.env.DEV && apiReachable === false ? (
        <div className="nsl-dev-banner" role="status">
          Demo tip: start the API — <code>./scripts/demo_local.sh</code>
        </div>
      ) : null}

      <nav className="nsl-nav">
        <Link to="/" className="nsl-logo">
          <img src="/genie-transparent.png" alt="NeuroSight genie" />
          <span className="nsl-logo-text">
            Neuro<em>Sight</em>
          </span>
        </Link>
        <ul className="nsl-nav-links">
          <li>
            <a href="#workflows">Product</a>
          </li>
          <li>
            <a href="#features">Features</a>
          </li>
          <li>
            <a href="#stages">Trials</a>
          </li>
          <li>
            <a href="#stories">Stories</a>
          </li>
        </ul>
        <div className="nsl-nav-actions">
          <Link to="/login" className="nsl-btn nsl-btn--ghost">
            Log in
          </Link>
          <Link to="/signup" className="nsl-btn nsl-btn--solid">
            Get started
          </Link>
        </div>
      </nav>

      <header className="nsl-hero">
        <div className="nsl-hero-copy">
          <span className="nsl-hero-badge">
            <IosSymbol name="lock.shield" size={13} strokeWidth={2} />
            Research build · Part 11 audit trail · HIPAA-ready
          </span>
          <h1>
            Quantitative brain reads.
            <br />
            <span className="nsl-grad">Trial-grade by design.</span>
          </h1>
          <p className="nsl-hero-sub">
            Regional WMH volumes, blinded BICR dual-reads, and signed structured reports — built for imaging core
            labs, not generic radiology triage.
          </p>
          <div className="nsl-hero-cta">
            <Link to="/upload" className="nsl-btn nsl-btn--solid nsl-btn--lg">
              Upload &amp; predict
            </Link>
            <Link to="/bicr-review" className="nsl-btn nsl-btn--glass nsl-btn--lg">
              BICR review
            </Link>
          </div>
        </div>

        <aside className="nsl-preview" aria-label="Sample structured report">
          <div className="nsl-preview-head">
            <div>
              <strong>WMH Structured Report</strong>
              <span>FLAIR 3D · baseline vs month 12</span>
            </div>
            <span className="nsl-chip nsl-chip--live">Signed</span>
          </div>
          <div className="nsl-preview-rows">
            {PREVIEW_ROWS.map((row) => (
              <div key={row.label} className="nsl-preview-row">
                <span className="nsl-preview-label">{row.label}</span>
                <div className="nsl-preview-bar" aria-hidden>
                  <i style={{ width: `${row.pct}%` }} />
                </div>
                <span className="nsl-preview-value">{row.value}</span>
              </div>
            ))}
          </div>
          <div className="nsl-preview-foot">
            <span className="nsl-chip">BICR locked</span>
            <span className="nsl-chip">PDF export</span>
            <span className="nsl-chip">audit #A1F3-88</span>
          </div>
        </aside>
      </header>

      <section id="workflows" className="nsl-section nsl-tiles">
        <div className="nsl-section-head">
          <span className="nsl-eyebrow">One workspace</span>
          <h2>All your trial imaging workflows in one place</h2>
        </div>
        <GlassTilePanel variant="landing" tiles={APP_WORKFLOW_TILES} aria-label="Workflow shortcuts" />
      </section>

      <section className="nsl-section">
        <div className="nsl-section-head">
          <span className="nsl-eyebrow">How it works</span>
          <h2>Measure, review, sign</h2>
        </div>
        <div className="nsl-trio-grid">
          {TRIO.map((item) => (
            <article key={item.title} className="nsl-trio-card" style={{ background: item.gradient }}>
              <div className="nsl-trio-icon" aria-hidden>
                <IosSymbol name={item.symbol} size={26} strokeWidth={1.5} />
              </div>
              <h3>{item.title}</h3>
              <p>{item.caption}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="features" className="nsl-section">
        <div className="nsl-section-head">
          <span className="nsl-eyebrow">Capabilities</span>
          <h2>Built for trial imaging teams</h2>
          {featuresLoaded && apiVersion ? <span className="nsl-api-version">API v{apiVersion}</span> : null}
        </div>
        <div className="nsl-feature-grid">
          {featureItems.map((f) => (
            <article key={f.id} className="nsl-feature-card">
              <div className="nsl-feature-head">
                <h3>{f.title}</h3>
                <span className={`nsl-chip ${f.available ? "nsl-chip--live" : ""}`}>
                  {f.available ? "Live" : "Setup"}
                </span>
              </div>
              <p>{f.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="stories" className="nsl-section">
        <div className="nsl-section-head">
          <span className="nsl-eyebrow">In the field</span>
          <h2>See how NeuroSight fits real workflows</h2>
        </div>
        <div className="nsl-story-grid">
          {STORIES.map((s) => (
            <article key={s.name} className="nsl-story-card">
              <blockquote>&ldquo;{s.quote}&rdquo;</blockquote>
              <div className="nsl-story-meta">
                <strong>{s.name}</strong>
                <span>{s.place}</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section id="stages" className="nsl-section">
        <div className="nsl-section-head">
          <span className="nsl-eyebrow">Roadmap</span>
          <h2>From research to trial-grade</h2>
        </div>
        <div className="nsl-stage-grid">
          {STAGES.map((s, i) => (
            <article key={s.tag} className="nsl-stage-card">
              <span className="nsl-stage-num">{String(i + 1).padStart(2, "0")}</span>
              <span className="nsl-stage-tag">{s.tag}</span>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="nsl-cta">
        <img src="/genie-transparent.png" alt="" aria-hidden className="nsl-cta-genie" />
        <h2>Start as a design partner</h2>
        <p>Prove WMH quantification and BICR workflow with one imaging core lab before scaling to multi-site trials.</p>
        <div className="nsl-hero-cta">
          <Link to="/upload" className="nsl-btn nsl-btn--solid nsl-btn--lg">
            Explore the app
          </Link>
          <Link to="/signup" className="nsl-btn nsl-btn--glass nsl-btn--lg">
            Create an account
          </Link>
        </div>
      </section>

      <footer className="nsl-footer">
        <div className="nsl-footer-inner">
          <div className="nsl-footer-brand">
            <Link to="/" className="nsl-logo">
              <img src="/genie-transparent.png" alt="" />
              <span className="nsl-logo-text">
                Neuro<em>Sight</em>
              </span>
            </Link>
            <p>Brain MRI AI for WMH quantification and clinical-trials imaging workflows. Research use only.</p>
          </div>
          <div className="nsl-footer-col">
            <h4>Product</h4>
            <Link to="/upload">Upload &amp; predict</Link>
            <Link to="/bicr-review">BICR review</Link>
            <Link to="/clinical-feedback">Clinical feedback</Link>
            <Link to="/shadow-queue">Shadow queue</Link>
          </div>
          <div className="nsl-footer-col">
            <h4>Learn</h4>
            <a href="#features">Features</a>
            <a href="#stages">Trial stages</a>
            <Link to="/docs-assistant">Docs assistant</Link>
          </div>
          <div className="nsl-footer-col">
            <h4>Account</h4>
            <Link to="/login">Log in</Link>
            <Link to="/signup">Sign up</Link>
            <Link to="/dashboard">Dashboard</Link>
          </div>
        </div>
        <div className="nsl-footer-bottom">
          <span>© {new Date().getFullYear()} NeuroSight. Research tool — not for clinical diagnosis.</span>
          <span>Founded for trial imaging teams</span>
        </div>
      </footer>
    </div>
  );
}
