import { Navigate, Route, Routes } from "react-router-dom";
import { useSession } from "./context/SessionContext";
import AppNav from "./components/AppNav";
import Landing from "./pages/Landing";
import StaffLogin from "./pages/StaffLogin";
import MemberEntry from "./pages/member/MemberEntry";
import Verify from "./pages/member/Verify";
import ScreeningFlow from "./pages/member/ScreeningFlow";
import Queue from "./pages/care-manager/Queue";
import CaseDetail from "./pages/care-manager/CaseDetail";
import TenantConfig from "./pages/admin/TenantConfig";
import SuperAdmin from "./pages/superadmin/SuperAdmin";

function RequireStaff({ children }: { children: JSX.Element }) {
  const { staff } = useSession();
  return staff ? children : <Navigate to="/login" replace />;
}

function RequireMember({ children }: { children: JSX.Element }) {
  const { member } = useSession();
  return member ? children : <Navigate to="/start" replace />;
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
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<StaffLogin />} />
      <Route path="/start" element={<MemberEntry />} />
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
        path="/queue"
        element={
          <StaffPage wide>
            <Queue />
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
        path="/superadmin"
        element={
          <StaffPage wide>
            <SuperAdmin />
          </StaffPage>
        }
      />
    </Routes>
  );
}
