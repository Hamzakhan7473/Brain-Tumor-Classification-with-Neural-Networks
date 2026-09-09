import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import UploadPredict from "./pages/UploadPredict";
import GenerateReport from "./pages/GenerateReport";
import ClinicalFeedback from "./pages/ClinicalFeedback";
import BicrReview from "./pages/BicrReview";
import Dashboard from "./pages/Dashboard";
import CaseDetail from "./pages/CaseDetail";
import AppShell from "./components/AppShell";
import MarketingLanding from "./pages/MarketingLanding";
import DocsAssistant from "./pages/DocsAssistant";
import ReadingMode from "./pages/ReadingMode";
import ShadowQueue from "./pages/ShadowQueue";
import OpsMonitor from "./pages/OpsMonitor";
import FeedbackAssignment from "./pages/FeedbackAssignment";
import ReportComposer from "./pages/ReportComposer";
import ReportDraft from "./pages/ReportDraft";
import SafetyEscalation from "./pages/SafetyEscalation";
import WorklistIntegration from "./pages/WorklistIntegration";
import ResultPushStatus from "./pages/ResultPushStatus";
import Governance from "./pages/Governance";
import AuthsQueue from "./pages/AuthsQueue";
import AuthDetail from "./pages/AuthDetail";
import InboxQueue from "./pages/InboxQueue";
import InboxDetail from "./pages/InboxDetail";
import AgentTracesQueue from "./pages/AgentTracesQueue";
import AgentTraceDetail from "./pages/AgentTraceDetail";
import Login from "./pages/Login";
import Signup from "./pages/Signup";

function App() {
  return (
    <Routes>
      {/* Landing */}
      <Route path="/" element={<MarketingLanding />} />
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
      <Route
        path="/docs-assistant"
        element={
          <AppShell>
            <DocsAssistant />
          </AppShell>
        }
      />
      <Route
        path="/auths"
        element={
          <AppShell>
            <AuthsQueue />
          </AppShell>
        }
      />
      <Route
        path="/auths/:authId"
        element={
          <AppShell>
            <AuthDetail />
          </AppShell>
        }
      />
      <Route
        path="/inbox"
        element={
          <AppShell>
            <InboxQueue />
          </AppShell>
        }
      />
      <Route
        path="/inbox/:messageId"
        element={
          <AppShell>
            <InboxDetail />
          </AppShell>
        }
      />
      <Route
        path="/agents-traces"
        element={
          <AppShell>
            <AgentTracesQueue />
          </AppShell>
        }
      />
      <Route
        path="/agents-traces/:traceId"
        element={
          <AppShell>
            <AgentTraceDetail />
          </AppShell>
        }
      />
      <Route
        path="/reading/:studyId"
        element={
          <AppShell>
            <ReadingMode />
          </AppShell>
        }
      />
      {/* Phase B: shadow-mode pilot */}
      <Route
        path="/shadow-queue"
        element={
          <AppShell>
            <ShadowQueue />
          </AppShell>
        }
      />
      <Route
        path="/ops-monitor"
        element={
          <AppShell>
            <OpsMonitor />
          </AppShell>
        }
      />
      <Route
        path="/feedback-assignment"
        element={
          <AppShell>
            <FeedbackAssignment />
          </AppShell>
        }
      />
      {/* Phase C: assistive / pre-read */}
      <Route
        path="/report-composer"
        element={
          <AppShell>
            <ReportComposer />
          </AppShell>
        }
      />
      <Route
        path="/report-draft/:reportId/signed"
        element={
          <AppShell>
            <ReportDraft />
          </AppShell>
        }
      />
      <Route
        path="/report-draft/:reportId"
        element={
          <AppShell>
            <ReportDraft />
          </AppShell>
        }
      />
      <Route
        path="/safety-escalation"
        element={
          <AppShell>
            <SafetyEscalation />
          </AppShell>
        }
      />
      {/* Phase D: integrated workflows */}
      <Route
        path="/worklist"
        element={
          <AppShell>
            <WorklistIntegration />
          </AppShell>
        }
      />
      <Route
        path="/result-push"
        element={
          <AppShell>
            <ResultPushStatus />
          </AppShell>
        }
      />
      <Route
        path="/governance"
        element={
          <AppShell>
            <Governance />
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
      <Route
        path="/bicr-review"
        element={
          <AppShell>
            <BicrReview />
          </AppShell>
        }
      />
      {/* Marketing alias */}
      <Route path="/marketing" element={<Navigate to="/" replace />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;

