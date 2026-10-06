// Mirrors snorkel.publish.status.StatusDoc (Python). Timestamps are ISO UTC.

export type Verdict = "yes" | "maybe" | "no" | "unknown";
export type Confidence = "high" | "medium" | "low";

export interface Factor {
  label: string;
  effect: "+" | "-" | "~";
  detail: string;
}

export interface TimeWindow {
  start: string;
  end: string;
}

export interface HourScore {
  time: string;
  score: number;
  tide_ft: number | null;
  tide_trend: string | null;
  wind_kt: number | null;
}

export interface SpotConditions {
  hs_ft: number | null;
  tp_s: number | null;
  swell_dir_deg: number | null;
  wave_source: string | null;
  orbital_ms: number | null;
  wind_kt: number | null;
  gust_kt: number | null;
  wind_dir_deg: number | null;
  wind_onshore: boolean | null;
  tide_ft: number | null;
  tide_trend: string | null;
}

export interface SpotStatus {
  id: string;
  name: string;
  tier: number;
  difficulty: string;
  verdict: Verdict;
  confidence: Confidence;
  vis_ft: [number, number] | null;
  reason: string;
  window: TimeWindow | null;
  window_day: "today" | "tomorrow" | null;
  gates: string[];
  cautions: string[];
  factors: Factor[];
  conditions: SpotConditions;
  hourly: HourScore[];
  shore_normal_deg: number;
}

export interface SourceHealth {
  id: string;
  label: string;
  ok: boolean;
  stale: boolean;
  fetched_at: string;
  valid_at: string | null;
  error: string | null;
}

export interface TidePoint {
  time: string;
  ft: number;
}

export interface TideTurn extends TidePoint {
  kind: "high" | "low";
}

export interface DayConditions {
  date: string;
  sunrise: string;
  sunset: string;
  water_temp_f: number | null;
  water_temp_source: string | null;
  wetsuit: string | null;
  turbidity_ntu: number | null;
  chlorophyll_ug_l: number | null;
  alerts: string[];
  tide_curve: TidePoint[];
  tide_turns: TideTurn[];
}

export interface StatusDoc {
  version: number;
  generated_at: string;
  timezone: string;
  summary: string;
  best_bet: string | null;
  spots: SpotStatus[];
  day: DayConditions;
  sources: SourceHealth[];
  disclaimer: string;
  cam_url?: string | null;
}
