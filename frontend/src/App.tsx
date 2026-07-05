import { Navigate, Route, Routes } from "react-router-dom";
import { useSession } from "./context/SessionContext";
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
          <RequireStaff>
            <Queue />
          </RequireStaff>
        }
      />
      <Route
        path="/queue/:gapId"
        element={
          <RequireStaff>
            <CaseDetail />
          </RequireStaff>
        }
      />
      <Route
        path="/admin/measures"
        element={
          <RequireStaff>
            <TenantConfig />
          </RequireStaff>
        }
      />
      <Route
        path="/superadmin"
        element={
          <RequireStaff>
            <SuperAdmin />
          </RequireStaff>
        }
      />
    </Routes>
  );
}
