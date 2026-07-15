import { api } from "./api";

export interface MeasureRow {
  code: string;
  name: string;
  eligible: number;
  completed: number;
  rate: number;
  remaining: number;
  source_split: { self_report: number; claims_confirmed: number };
  trend_points: number | null;
}

export interface WorklistRow {
  care_gap_id: string;
  measure_code: string;
  status: string;
  safety_flag: boolean;
}

export interface Overview {
  period: string;
  kpis: {
    gap_closure_rate: number;
    open_safety_flags: number;
    bonus_at_risk: number | null;
    members_reached: number;
    members_enrolled: number;
  };
  measures: MeasureRow[];
  worklist: WorklistRow[];
}

export const getOverview = (period: string, token?: string | null) =>
  api.get<Overview>(`/api/reports/overview?period=${encodeURIComponent(period)}`, token);
