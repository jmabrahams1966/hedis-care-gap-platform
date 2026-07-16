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

// --- Tasks (Feature B Phase 2) ---

export interface CareTask {
  id: string;
  member_id: string;
  care_gap_id: string | null;
  title: string;
  due_at: string | null;
  sla_hours: number | null;
  assignee_staff_id: string | null;
  status: "open" | "done" | "cancelled";
  created_at: string;
  completed_at: string | null;
  overdue: boolean;
}

export const getMemberTasks = (memberId: string, token?: string | null) =>
  api.get<CareTask[]>(`/api/members/${memberId}/tasks`, token);

export const createTask = (
  memberId: string,
  body: { title: string; due_at?: string | null; care_gap_id?: string | null },
  token?: string | null,
) => api.post<CareTask>(`/api/members/${memberId}/tasks`, body, token);

export const updateTask = (taskId: string, status: CareTask["status"], token?: string | null) =>
  api.patch<CareTask>(`/api/tasks/${taskId}`, { status }, token);

export const getOverdueTasks = (token?: string | null) =>
  api.get<CareTask[]>(`/api/tasks?status=overdue`, token);

// --- Care plan (Feature B Phase 3) ---

export interface CarePlanGoal {
  id: string;
  member_id: string;
  care_gap_id: string | null;
  goal_text: string;
  interventions_text: string;
  target_date: string | null;
  status: "open" | "met" | "discontinued";
  created_at: string;
  updated_at: string;
}

export const GOAL_STATUS_BADGE: Record<string, string> = {
  open: "open",
  met: "done",
  discontinued: "excluded",
};

export const getCarePlan = (memberId: string, token?: string | null) =>
  api.get<CarePlanGoal[]>(`/api/members/${memberId}/care-plan`, token);

export const createGoal = (
  memberId: string,
  body: { goal_text: string; interventions_text?: string; target_date?: string | null; care_gap_id?: string | null },
  token?: string | null,
) => api.post<CarePlanGoal>(`/api/members/${memberId}/care-plan`, body, token);

export const updateGoal = (goalId: string, status: CarePlanGoal["status"], token?: string | null) =>
  api.patch<CarePlanGoal>(`/api/care-plan/${goalId}`, { status }, token);

// --- Safety plan + escalation (Feature B Phase 4) ---

export interface SafetyPlanSections {
  warning_signs: string;
  coping_strategies: string;
  support_contacts: string;
  means_restriction: string;
  notes: string;
  updated_at: string | null;
}

export interface EscalationStep {
  step_key: string;
  label: string;
  completed: boolean;
  completed_by: string | null;
  completed_at: string | null;
}

export type SafetyPlanField = keyof Omit<SafetyPlanSections, "updated_at">;

export const SAFETY_PLAN_FIELDS: { key: SafetyPlanField; label: string }[] = [
  { key: "warning_signs", label: "Warning signs" },
  { key: "coping_strategies", label: "Coping strategies" },
  { key: "support_contacts", label: "Support contacts" },
  { key: "means_restriction", label: "Means restriction" },
  { key: "notes", label: "Notes" },
];

export const getSafetyPlan = (memberId: string, token?: string | null) =>
  api.get<SafetyPlanSections>(`/api/members/${memberId}/safety-plan`, token);

export const putSafetyPlan = (
  memberId: string,
  body: Omit<SafetyPlanSections, "updated_at">,
  token?: string | null,
) => api.put<SafetyPlanSections>(`/api/members/${memberId}/safety-plan`, body, token);

export const getEscalation = (careGapId: string, token?: string | null) =>
  api.get<EscalationStep[]>(`/api/care-gaps/${careGapId}/escalation`, token);

export const toggleEscalationStep = (careGapId: string, stepKey: string, token?: string | null) =>
  api.post<EscalationStep>(`/api/care-gaps/${careGapId}/escalation/${stepKey}`, {}, token);

// --- Outreach enrollments (Feature C1, care-manager control) ---

export interface Enrollment {
  id: string;
  member_id: string;
  care_gap_id: string | null;
  sequence_id: string;
  status: "active" | "paused" | "ended";
  current_step_order: number;
  next_send_at: string | null;
  ended_reason: string | null;
}

export const getMemberEnrollments = (memberId: string, token?: string | null) =>
  api.get<Enrollment[]>(`/api/members/${memberId}/enrollments`, token);

export const pauseEnrollment = (id: string, token?: string | null) =>
  api.post<Enrollment>(`/api/enrollments/${id}/pause`, {}, token);

export const resumeEnrollment = (id: string, token?: string | null) =>
  api.post<Enrollment>(`/api/enrollments/${id}/resume`, {}, token);

export const endEnrollment = (id: string, token?: string | null) =>
  api.post<Enrollment>(`/api/enrollments/${id}/end`, {}, token);
