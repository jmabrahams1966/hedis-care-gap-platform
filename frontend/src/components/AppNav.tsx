import { Link, useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../context/SessionContext";
import { FEATURE_OVERVIEW } from "../lib/features";

const ROLE_LABEL: Record<string, string> = {
  super_admin: "Super Admin",
  payer_admin: "Payer Admin",
  care_manager: "Care Manager",
};

export default function AppNav() {
  const { staff, setStaff } = useSession();
  const location = useLocation();
  const navigate = useNavigate();

  function logout() {
    setStaff(null);
    navigate("/");
  }

  const links: { to: string; label: string }[] = [];
  if (FEATURE_OVERVIEW && (staff?.role === "payer_admin" || staff?.role === "super_admin")) {
    links.push({ to: "/overview", label: "Overview" });
  }
  if (staff?.role === "care_manager" || staff?.role === "payer_admin" || staff?.role === "super_admin") {
    links.push({ to: "/queue", label: "Care Gap Queue" });
  }
  if (staff?.role === "payer_admin" || staff?.role === "super_admin") {
    links.push({ to: "/admin/measures", label: "Measures" });
    links.push({ to: "/admin/sequences", label: "Sequences" });
    links.push({ to: "/admin/outreach", label: "Outreach" });
  }
  if (staff?.role === "super_admin") {
    links.push({ to: "/superadmin", label: "Tenants" });
  }
  if (staff) {
    links.push({ to: "/security", label: "Security" });
  }

  return (
    <nav className="top-nav">
      <div className="top-nav__inner">
        <Link to="/queue" className="brand">
          <span className="brand__mark" aria-hidden="true">
            +
          </span>
          HEDIS Care Gap
        </Link>
        <div className="top-nav__links">
          {links.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className={`top-nav__link${location.pathname.startsWith(link.to) ? " active" : ""}`}
            >
              {link.label}
            </Link>
          ))}
          <div className="top-nav__user">
            {staff && <span className="top-nav__role">{ROLE_LABEL[staff.role] ?? staff.role}</span>}
            <button className="btn ghost sm" onClick={logout}>
              Sign out
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
