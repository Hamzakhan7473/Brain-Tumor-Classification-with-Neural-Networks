import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing";
import UploadPredict from "./pages/UploadPredict";
import GenerateReport from "./pages/GenerateReport";
import ClinicalFeedback from "./pages/ClinicalFeedback";
import Dashboard from "./pages/Dashboard";
import CaseDetail from "./pages/CaseDetail";
import AppShell from "./components/AppShell";
import MarketingLanding from "./pages/MarketingLanding";

function App() {
  return (
    <Routes>
      {/* App shell routes */}
      <Route
        path="/"
        element={
          <AppShell>
            <Dashboard />
          </AppShell>
        }
      />
      <Route
        path="/dashboard"
        element={
          <AppShell>
            <Dashboard />
          </AppShell>
        }
      />
      <Route
        path="/cases/:studyId"
        element={
          <AppShell>
            <CaseDetail />
          </AppShell>
        }
      />
      {/* Core app flows */}
      <Route
        path="/upload"
        element={
          <AppShell>
            <UploadPredict />
          </AppShell>
        }
      />
      <Route
        path="/report"
        element={
          <AppShell>
            <GenerateReport />
          </AppShell>
        }
      />
      <Route
        path="/clinical-feedback"
        element={
          <AppShell>
            <ClinicalFeedback />
          </AppShell>
        }
      />
      {/* Marketing / static landing */}
      <Route path="/marketing" element={<MarketingLanding />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;

