export type LoginRole = "member" | "nurse_manager" | "admin";

const CARDS: { role: LoginRole; label: string; icon: string }[] = [
  { role: "member", label: "Member", icon: "🧑" },
  { role: "nurse_manager", label: "Nurse Manager", icon: "🩺" },
  { role: "admin", label: "Admin", icon: "📊" },
];

/**
 * One-screen role picker (CogAi Campus style). The two staff cards both drive the
 * same staff form — the card is a presentational hint; the account's real role
 * decides the post-login destination.
 */
export default function RoleSelector({
  value,
  onChange,
}: {
  value: LoginRole;
  onChange: (r: LoginRole) => void;
}) {
  return (
    <div role="tablist" aria-label="Sign in as" style={{ display: "flex", gap: 8, marginBottom: 16 }}>
      {CARDS.map((c) => {
        const selected = value === c.role;
        return (
          <button
            key={c.role}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(c.role)}
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 4,
              padding: "12px 8px",
              borderRadius: "var(--radius-md)",
              border: `1px solid ${selected ? "var(--border-strong)" : "var(--border)"}`,
              background: selected ? "var(--info-bg)" : "var(--surface)",
              color: selected ? "var(--info)" : "var(--text)",
              cursor: "pointer",
              fontWeight: selected ? 700 : 500,
              fontSize: 13,
              transition: "border-color 120ms ease, background 120ms ease",
            }}
          >
            <span aria-hidden="true" style={{ fontSize: 22 }}>
              {c.icon}
            </span>
            {c.label}
          </button>
        );
      })}
    </div>
  );
}
