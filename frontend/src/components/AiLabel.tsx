/**
 * Shared provenance label shown next to any AI-generated draft (Feature E).
 * Every AI surface renders this so the human always knows the text is a draft
 * to review, not a finished/authoritative output.
 */
export default function AiLabel({ style }: { style?: React.CSSProperties }) {
  return (
    <span className="ai-label" style={style}>
      <span aria-hidden="true">✨</span> AI-generated — review before use
    </span>
  );
}
