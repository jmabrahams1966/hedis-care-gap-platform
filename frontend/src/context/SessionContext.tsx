import { createContext, useContext, useState, type ReactNode } from "react";

interface StaffSession {
  token: string;
  role: "super_admin" | "payer_admin" | "care_manager";
  name: string;
  tenantId: string | null;
}

interface MemberSession {
  token: string;
  firstName: string;
}

interface SessionState {
  staff: StaffSession | null;
  member: MemberSession | null;
  setStaff: (s: StaffSession | null) => void;
  setMember: (m: MemberSession | null) => void;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [staff, setStaffState] = useState<StaffSession | null>(() => {
    const raw = sessionStorage.getItem("staff_session");
    return raw ? JSON.parse(raw) : null;
  });
  const [member, setMemberState] = useState<MemberSession | null>(() => {
    const raw = sessionStorage.getItem("member_session");
    return raw ? JSON.parse(raw) : null;
  });

  const setStaff = (s: StaffSession | null) => {
    setStaffState(s);
    if (s) sessionStorage.setItem("staff_session", JSON.stringify(s));
    else sessionStorage.removeItem("staff_session");
  };
  const setMember = (m: MemberSession | null) => {
    setMemberState(m);
    if (m) sessionStorage.setItem("member_session", JSON.stringify(m));
    else sessionStorage.removeItem("member_session");
  };

  return (
    <SessionContext.Provider value={{ staff, member, setStaff, setMember }}>{children}</SessionContext.Provider>
  );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
