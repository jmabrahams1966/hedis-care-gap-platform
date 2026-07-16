// Build-time feature flags. Set via Vite env at build (e.g. VITE_FEATURE_OVERVIEW=true).
//
// FEATURE_OVERVIEW gates the Quality Overview dashboard (Feature A). Its backend
// endpoint (GET /api/reports/overview) must be deployed before this is turned on —
// with the flag off, payer_admin lands on the queue and the Overview nav link is
// hidden, so the frontend can ship ahead of the backend without breaking login.
export const FEATURE_OVERVIEW = import.meta.env.VITE_FEATURE_OVERVIEW === "true";

// FEATURE_AI gates KaveraChat AI assist (Feature E) — the "Draft reply",
// "Summarize case", triage chips, and "Draft copy" affordances. Its backend is
// itself dormant behind settings.ai_enabled (503 until the Bedrock IAM grant is
// applied), so with this flag off the UI shows nothing and can ship ahead of
// both the backend enablement and the infra apply.
export const FEATURE_AI = import.meta.env.VITE_FEATURE_AI === "true";
