import React from "react";
import { Link } from "react-router-dom";

export default function MarketingLanding() {
  return (
    <>
      <nav>
        <a href="/marketing" className="nav-logo">
          <img src="/genie-transparent.png" alt="NeuroSight genie" className="nav-logo-img" />
          <span className="nav-logo-text">
            Neuro<span>Sight</span>
          </span>
        </a>
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
          <button className="btn-ghost" type="button">
            Docs
          </button>
          <Link to="/upload" className="btn-primary">
            Launch app
          </Link>
        </div>
      </nav>

      <main>
        <section className="hero">
          <div className="hero-left">
            <div className="hero-eyebrow">Brain MRI AI · Clinical workflow ready</div>
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
                <span className="trust-check">✓</span> Shadow-mode logging with study_instance_uid &amp; site_id
              </div>
              <div className="trust-item">
                <span className="trust-check">✓</span> MongoDB Atlas + AWS/GCP deployment path
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
      </main>
    </>
  );
}

