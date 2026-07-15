// Build-time feature flags. Set via Vite env at build (e.g. VITE_FEATURE_OVERVIEW=true).
//
// FEATURE_OVERVIEW gates the Quality Overview dashboard (Feature A). Its backend
// endpoint (GET /api/reports/overview) must be deployed before this is turned on —
// with the flag off, payer_admin lands on the queue and the Overview nav link is
// hidden, so the frontend can ship ahead of the backend without breaking login.
export const FEATURE_OVERVIEW = import.meta.env.VITE_FEATURE_OVERVIEW === "true";
