import { useState } from "react";
import { useSession } from "../../context/SessionContext";
import { MEASURE_LABELS } from "../../data/measures";
import { draftSequenceStep, recordOutcome } from "../../lib/ai";
import { FEATURE_AI } from "../../lib/features";
import AiLabel from "../../components/AiLabel";

/**
 * Feature E admin affordance: draft outreach copy for a sequence step. The
 * platform's steps reference a template_key, so this is a reference-copy helper
 * (not an auto-apply) — the admin reads/copies the draft into whatever authors
 * the templates. Nothing is written to a sequence here.
 */
export default function OutreachCopyAssistant({ defaultMeasure }: { defaultMeasure: string }) {
  const { staff } = useSession();
  const [measure, setMeasure] = useState(defaultMeasure);
  const [channel, setChannel] = useState("sms");
  const [intent, setIntent] = useState("");
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<{ text: string; interactionId: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!FEATURE_AI) return null;

  async function run() {
    if (!intent.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await draftSequenceStep(
        { measure_code: measure, intent: intent.trim(), channel },
        staff?.token,
      );
      setDraft({ text: res.draft, interactionId: res.interaction_id });
    } catch {
      setError("AI copy drafting is unavailable right now.");
    } finally {
      setLoading(false);
    }
  }

  async function copy() {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(draft.text);
    } catch {
      /* clipboard may be blocked; ignore */
    }
    recordOutcome(draft.interactionId, "accepted", staff?.token).catch(() => {});
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h2 className="card__title">✨ Copy assistant</h2>
      <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
        Draft reference outreach copy for a step. Review and adapt before using — nothing is
        applied to a sequence automatically.
      </p>
      <div className="stack" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label style={{ margin: 0 }}>
          Measure
          <select value={measure} onChange={(e) => setMeasure(e.target.value)} style={{ marginBottom: 0 }}>
            {Object.entries(MEASURE_LABELS).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label style={{ margin: 0 }}>
          Channel
          <select value={channel} onChange={(e) => setChannel(e.target.value)} style={{ marginBottom: 0 }}>
            <option value="sms">SMS</option>
            <option value="email">Email</option>
          </select>
        </label>
      </div>
      <label htmlFor="copy-intent" style={{ marginTop: 8 }}>
        Step intent
      </label>
      <input
        id="copy-intent"
        value={intent}
        onChange={(e) => setIntent(e.target.value)}
        placeholder="e.g. friendly second reminder to complete the screening"
      />
      <button className="btn secondary sm" onClick={run} disabled={loading || !intent.trim()}>
        {loading ? "Drafting…" : "Draft copy"}
      </button>
      {error && <p className="muted">{error}</p>}
      {draft && (
        <div style={{ marginTop: 10 }}>
          <AiLabel style={{ display: "inline-block", marginBottom: 6 }} />
          <p style={{ whiteSpace: "pre-wrap", margin: "4px 0 8px" }}>{draft.text}</p>
          <button className="btn ghost sm" onClick={copy}>
            Copy to clipboard
          </button>
        </div>
      )}
    </div>
  );
}
