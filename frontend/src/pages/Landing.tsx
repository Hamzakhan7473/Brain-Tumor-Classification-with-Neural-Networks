import React from "react";

export default function Landing() {
  return (
    <div className="container" style={{ paddingTop: 88 }}>
      <h2 style={{ marginBottom: 4 }}>Dashboard</h2>
      <p style={{ color: "var(--ink-mute)", marginBottom: 20 }}>
        Use the navigation above to upload a scan, view AI results, generate a report, and record clinician feedback.
      </p>
    </div>
  );
}

