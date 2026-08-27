import React from "react";
import { AppPage } from "../components/layout/AppPage";

export default function ResultPushStatus() {
  return (
    <AppPage
      title="Result push status"
      subtitle="Monitor whether AI results were successfully pushed to EHR/PACS and when retries are needed."
    >
      <div className="card">
        <div className="app-card-title">Delivery log</div>
        <p className="app-card-sub">
          Later, back this with a dedicated <code>/result-push</code> or audit endpoint.
        </p>

        <div className="app-table-wrap">
          <table className="app-table">
            <thead>
              <tr>
                <th>Study UID</th>
                <th>Destination</th>
                <th>Status</th>
                <th>Last attempt</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>demo-worklist-001</td>
                <td>EHR / HL7</td>
                <td>sent</td>
                <td>just now (demo)</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </AppPage>
  );
}
