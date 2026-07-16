import { Navigate, Route, Routes } from "react-router-dom";
import { useSession } from "./context/SessionContext";
import AppNav from "./components/AppNav";
import UnifiedLogin from "./pages/UnifiedLogin";
import Verify from "./pages/member/Verify";
import ScreeningFlow from "./pages/member/ScreeningFlow";
import MessageCenter from "./pages/member/MessageCenter";
import Inbox from "./pages/care-manager/Inbox";
import Overview from "./pages/care-manager/Overview";
import Queue from "./pages/care-manager/Queue";
import CaseDetail from "./pages/care-manager/CaseDetail";
import TenantConfig from "./pages/admin/TenantConfig";
import SequenceBuilder from "./pages/admin/SequenceBuilder";
import OutreachAnalytics from "./pages/admin/OutreachAnalytics";
import SuperAdmin from "./pages/superadmin/SuperAdmin";
import Security from "./pages/Security";

function RequireStaff({ children }: { children: JSX.Element }) {
  const { staff } = useSession();
  return staff ? children : <Navigate to="/" replace />;
}

function RequireMember({ children }: { children: JSX.Element }) {
  const { member } = useSession();
  return member ? children : <Navigate to="/" replace />;
}

function StaffPage({ children, wide = false }: { children: JSX.Element; wide?: boolean }) {
  return (
    <RequireStaff>
      <>
        <AppNav />
        <div className={wide ? "app-shell app-shell--wide" : "app-shell"}>{children}</div>
      </>
    </RequireStaff>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<UnifiedLogin />} />
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route path="/start" element={<Navigate to="/" replace />} />
      <Route path="/verify" element={<Verify />} />
      <Route
        path="/screening"
        element={
          <RequireMember>
            <ScreeningFlow />
          </RequireMember>
        }
      />
      <Route
        path="/messages"
        element={
          <RequireMember>
            <MessageCenter />
          </RequireMember>
        }
      />
      <Route
        path="/overview"
        element={
          <StaffPage wide>
            <Overview />
          </StaffPage>
        }
      />
      <Route
        path="/queue"
        element={
          <StaffPage wide>
            <Queue />
          </StaffPage>
        }
      />
      <Route
        path="/inbox"
        element={
          <StaffPage wide>
            <Inbox />
          </StaffPage>
        }
      />
      <Route
        path="/queue/:gapId"
        element={
          <StaffPage>
            <CaseDetail />
          </StaffPage>
        }
      />
      <Route
        path="/admin/measures"
        element={
          <StaffPage>
            <TenantConfig />
          </StaffPage>
        }
      />
      <Route
        path="/admin/sequences"
        element={
          <StaffPage wide>
            <SequenceBuilder />
          </StaffPage>
        }
      />
      <Route
        path="/admin/outreach"
        element={
          <StaffPage wide>
            <OutreachAnalytics />
          </StaffPage>
        }
      />
      <Route
        path="/superadmin"
        element={
          <StaffPage wide>
            <SuperAdmin />
          </StaffPage>
        }
      />
      <Route
        path="/security"
        element={
          <StaffPage>
            <Security />
          </StaffPage>
        }
      />
    </Routes>
  );
}
