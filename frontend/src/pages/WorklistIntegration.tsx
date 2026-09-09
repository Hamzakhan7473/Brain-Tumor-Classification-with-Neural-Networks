import React from "react";
import { AppPage } from "../components/layout/AppPage";

export default function WorklistIntegration() {
  return (
    <AppPage
      title="Worklist integration"
      subtitle="PACS-like worklist shell for mapping accessions / study UIDs to AI cases."
    >
      <div className="card">
        <div className="app-card-title">Integrated worklist</div>
        <p className="app-card-sub">
          Later, this can be driven by an <code>/worklist</code> API backed by your RIS/PACS integration.
        </p>

        <div className="app-table-wrap">
          <table className="app-table">
            <thead>
              <tr>
                <th>Accession</th>
                <th>Study UID</th>
                <th>Patient</th>
                <th>Site</th>
                <th>AI status</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>ACC-12345</td>
                <td>demo-worklist-001</td>
                <td>Jane D.</td>
                <td>site-001</td>
                <td>AI ready</td>
                <td>glioma (0.92)</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </AppPage>
  );
}
