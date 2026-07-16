import { useState } from "react";
import { useSession } from "../../context/SessionContext";
import { summarizeCase, recordOutcome } from "../../lib/ai";
import { FEATURE_AI } from "../../lib/features";
import AiLabel from "../../components/AiLabel";

/**
 * The model tends to emit light markdown (**bold**, a redundant "Case Summary"
 * title, `- ` bullets) even when asked for plain prose. Rather than render a
 * markdown tree for a few sentences, normalize to clean text: drop emphasis
 * markers, strip a leading title line (the card header + AiLabel already say
 * what this is), and turn bullets into real ones.
 */
function cleanSummary(raw: string): string[] {
  const lines = raw
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/^#{1,6}\s*/gm, "")
    .split("\n")
    .map((l) => l.trim());
  // Drop a leading title-ish line, e.g. "Member Case Summary - DRAFT for Review"
  if (lines.length && /case summary|draft for/i.test(lines[0]) && lines[0].length < 80) {
    lines.shift();
  }
  return lines.filter(Boolean).map((l) => l.replace(/^[-*]\s+/, "• "));
}

/**
 * Feature E workspace affordance: a one-click AI case summary built from the
 * member's gaps + notes + screening history. Read-only — it never writes a note.
 * The summary is a draft for the care manager to read; "Use as note prompt" and
 * "Dismiss" report the interaction outcome for quality monitoring.
 */
export default function CaseSummary({ memberId }: { memberId: string }) {
  const { staff } = useSession();
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [interactionId, setInteractionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!FEATURE_AI) return null;

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const res = await summarizeCase(memberId, staff?.token);
      setSummary(res.summary);
      setInteractionId(res.interaction_id);
    } catch {
      setError("AI summary is unavailable right now.");
    } finally {
      setLoading(false);
    }
  }

  function dismiss() {
    if (interactionId) recordOutcome(interactionId, "discarded", staff?.token).catch(() => {});
    setSummary(null);
    setInteractionId(null);
  }

  function acknowledge() {
    if (interactionId) recordOutcome(interactionId, "accepted", staff?.token).catch(() => {});
  }

  return (
    <div className="card">
      <div className="note-row__head" style={{ marginBottom: 8 }}>
        <h2 className="card__title" style={{ margin: 0 }}>
          Case summary
        </h2>
        <button className="btn secondary sm" onClick={run} disabled={loading}>
          {loading ? "Summarizing…" : "✨ Summarize case"}
        </button>
      </div>
      {error && <p className="muted">{error}</p>}
      {summary && (
        <>
          <AiLabel style={{ display: "inline-block", marginBottom: 8 }} />
          <div className="ai-summary-body">
            {cleanSummary(summary).map((line, i) => (
              <p key={i}>{line}</p>
            ))}
          </div>
          <div className="stack" style={{ marginTop: 12 }}>
            <button className="btn ghost sm" onClick={acknowledge}>
              Looks useful
            </button>
            <button className="btn ghost sm" onClick={dismiss}>
              Dismiss
            </button>
          </div>
        </>
      )}
    </div>
  );
}
