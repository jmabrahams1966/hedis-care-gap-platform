import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import RoleSelector, { type LoginRole } from "../components/auth/RoleSelector";
import MemberSignInForm from "../components/auth/MemberSignInForm";
import StaffSignInForm from "../components/auth/StaffSignInForm";

/**
 * Single-screen sign-in. A role selector (Member / Nurse Manager / Admin) swaps the
 * form below it. Members use ID/phone + DOB → magic link; staff use email + password
 * (with MFA). Replaces the old two-card Landing + standalone StaffLogin page.
 */
export default function UnifiedLogin() {
  const { staff, member } = useSession();
  const [role, setRole] = useState<LoginRole>("member");

  // Already signed in? Send them to their home rather than showing the login.
  if (staff) return <Navigate to={staff.role === "super_admin" ? "/superadmin" : "/queue"} replace />;
  if (member) return <Navigate to="/screening" replace />;

  return (
    <div className="app-shell" style={{ paddingTop: 64 }}>
      <div className="stack" style={{ alignItems: "center", marginBottom: 16 }}>
        <span className="brand__mark" aria-hidden="true">
          +
        </span>
        <span className="muted" style={{ fontWeight: 700, letterSpacing: "0.02em" }}>
          HEDIS CARE GAP PLATFORM
        </span>
      </div>

      <h2 style={{ marginBottom: 4 }}>Sign in</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Choose how you're signing in.
      </p>

      <RoleSelector value={role} onChange={setRole} />

      {role === "member" ? <MemberSignInForm /> : <StaffSignInForm />}
    </div>
  );
}
