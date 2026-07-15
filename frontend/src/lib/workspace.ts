import { api } from "./api";

export interface TrendPoint {
  date: string;
  phq9: number | null;
  gad7: number | null;
}

export const NOTE_TYPES = [
  "contact",
  "assessment",
  "safety_check",
  "care_coordination",
  "other",
] as const;

export type NoteType = (typeof NOTE_TYPES)[number];

export const NOTE_TYPE_LABEL: Record<string, string> = {
  contact: "Contact",
  assessment: "Assessment",
  safety_check: "Safety check",
  care_coordination: "Care coordination",
  other: "Note",
};

// Notes typed as safety concerns get the red safety badge; the rest are neutral.
export const NOTE_TYPE_BADGE: Record<string, string> = {
  safety_check: "safety",
  assessment: "follow-up",
  contact: "open",
  care_coordination: "open",
  other: "open",
};

export const getScreeningHistory = (memberId: string, measure: string, token?: string | null) =>
  api.get<TrendPoint[]>(
    `/api/members/${memberId}/screening-history?measure=${encodeURIComponent(measure)}`,
    token,
  );
