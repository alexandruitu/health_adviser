const BASE = "/api";

export function getToken(): string | null {
  return localStorage.getItem("auth_token");
}
export function setToken(t: string) {
  localStorage.setItem("auth_token", t);
}
export function clearToken() {
  localStorage.removeItem("auth_token");
  window.dispatchEvent(new Event("auth:logout"));
}

function authHeader(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

function handleStatus(res: Response, path: string) {
  if (res.status === 401) { clearToken(); throw new Error("Unauthorized"); }
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
}

async function get<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined) url.searchParams.set(k, v);
    });
  }
  const res = await fetch(url.toString(), { headers: authHeader() });
  handleStatus(res, path);
  return res.json();
}

export interface DailySummary {
  date: string;
  StepCount?: number;
  ActiveEnergyBurned?: number;
  HeartRate_mean?: number;
  HeartRate_min?: number;
  HeartRate_max?: number;
  RestingHeartRate?: number;
  HeartRateVariabilitySDNN?: number;
  BodyMass?: number;
  BodyFatPercentage?: number;
  BodyMassIndex?: number;
  BloodGlucose_mean?: number;
  BloodGlucose_min?: number;
  BloodGlucose_max?: number;
  BloodPressureSystolic_mean?: number;
  BloodPressureDiastolic_mean?: number;
  DistanceWalkingRunning?: number;
  VO2Max?: number;
  WalkingSpeed?: number;
  [key: string]: string | number | undefined;
}

export interface SleepDay {
  night: string;
  total_sleep_hours?: number;
  Deep?: number;
  REM?: number;
  Core?: number;
  Awake?: number;
}

export interface ReadinessDay {
  date: string;
  readiness: number;
  label: "Peak" | "High" | "Moderate" | "Low" | "Recovery";
  hrv_score?: number;
  sleep_score?: number;
  battery_score?: number;
  tsb_modifier: number;
  hrv_val?: number;
  hrv_baseline?: number;
  sleep_raw?: number;
  sleep_baseline?: number;
  battery_val?: number;
  tsb?: number;
  atl?: number;
  ctl?: number;
}

export interface SleepWellnessDay {
  date: string;
  GarminSleepScore?: number;
  GarminSleepHR?: number;
  GarminSleepRespiration?: number;
  GarminSleepRespirationLow?: number;
  GarminSleepSpO2?: number;
  GarminSleepSpO2Low?: number;
  GarminSleepRestless?: number;
  GarminBodyBatteryChange?: number;
  GarminBodyBatteryDuringSleep?: number;
  GarminAvgSleepStress?: number;
  GarminSkinTempChange?: number;
}

export interface Workout {
  startDate: string;
  workoutType: string;
  duration_min?: number;
  distance?: number;
  distanceUnit?: string;
  activeEnergy_kcal?: number;
}

export interface SummaryCards {
  avg_steps_90d: number | null;
  avg_resting_hr_90d: number | null;
  avg_hrv_90d: number | null;
  avg_sleep_90d: number | null;
  latest_weight_kg: number | null;
  latest_body_fat_pct: number | null;
  latest_vo2max: number | null;
  workouts_90d: number | null;
  avg_active_kcal_90d: number | null;
  period: string;
}

export interface MetricStats {
  count: number;
  mean: number;
  median: number;
  std: number;
  min: number;
  max: number;
  q25: number;
  q75: number;
  unit: string;
  date_min: string;
  date_max: string;
}

export type Resolution = "week" | "month" | "year";

export interface TrainingVolume {
  period: string;
  running_min: number;
  cycling_min: number;
  running_sessions: number;
  cycling_sessions: number;
  longest_run_min: number;
  longest_ride_min: number;
  running_km: number;
  cycling_km: number;
  running_elev_m?: number;
  cycling_elev_m?: number;
}

export interface PMCPoint {
  date: string;
  load: number;
  run_min: number;
  cyc_min: number;
  atl: number;
  ctl: number;
  tsb: number;
}

export interface PMCProjectionPoint {
  date: string;
  maintain_ctl: number;
  maintain_atl: number;
  maintain_tsb: number;
  decay_ctl: number;
  decay_atl: number;
  decay_tsb: number;
}

export interface PMCProjection {
  current_ctl: number | null;
  current_atl: number | null;
  current_tsb: number | null;
  avg_load_28d: number;
  projection: PMCProjectionPoint[];
}

export interface Goal {
  id: number;
  name: string;
  event_date: string;
  target_ctl: number | null;
  created_at: number;
}

export interface HRVPoint {
  date: string;
  hrv: number | null;
  hrv_30d: number | null;
}

export interface YoYResponse {
  data: Record<string, number | string>[];
  years: string[];
}

export interface StravaInsights {
  period: string;
  run_elevation_m: number;
  cyc_elevation_m: number;
  run_avg_hr: number;
  cyc_avg_hr: number;
  run_suffer: number;
  cyc_suffer: number;
  run_avg_cadence: number;
  cyc_avg_cadence: number;
  run_avg_pace: number;   // min/km
  run_avg_watts: number;
  cyc_avg_watts: number;
}

export interface StravaStatus {
  connected: boolean;
  last_sync: number | null;
  athlete_name: string | null;
}

export interface StravaSyncResult {
  added: number;
  skipped: number;
}

export interface ActivityRecord {
  date: string; name: string; type: string; source: string;
  distance_km: number | null; duration_min: number | null; pace_min_km: number | null;
  avg_hr: number | null; max_hr: number | null; elevation_m: number | null;
  suffer_score: number | null; avg_cadence: number | null; avg_watts: number | null;
  trainer: boolean;
}
export interface HRZone {
  zone: string; run_count: number; cyc_count: number;
  run_hours: number; cyc_hours: number; hr_min: number; hr_max: number;
}
export interface PRRecord {
  type: string; value: number | string; unit: string; date: string;
}

export const api = {
  profile: () => get<Record<string, string>>("/profile"),
  summaryCards: () => get<SummaryCards>("/summary/cards"),
  daily: (params?: { start?: string; end?: string; metrics?: string }) =>
    get<DailySummary[]>("/daily", params),
  dailyColumns: () => get<string[]>("/daily/columns"),
  sleep: (params?: { start?: string; end?: string }) =>
    get<SleepDay[]>("/sleep", params),
  readiness: (params?: { start?: string; end?: string }) =>
    get<ReadinessDay[]>("/readiness", params),
  sleepWellness: (params?: { start?: string; end?: string }) =>
    get<SleepWellnessDay[]>("/sleep/wellness", params),
  workouts: (params?: { start?: string; end?: string; workout_type?: string }) =>
    get<Workout[]>("/workouts", params),
  workoutTypes: () => get<{ type: string; count: number }[]>("/workouts/types"),
  activity: (params?: { start?: string; end?: string }) =>
    get<Record<string, string | number>[]>("/activity", params),
  metricSeries: (name: string, params?: { start?: string; end?: string; resample?: string }) =>
    get<Record<string, string | number>[]>(`/metric/${name}`, params),
  metricStats: (name: string, params?: { start?: string; end?: string }) =>
    get<MetricStats>(`/metric/${name}/stats`, params),
  availableMetrics: () => get<string[]>("/available_metrics"),
  // training analytics
  trainingVolume: (resolution: Resolution, start?: string, end?: string) =>
    get<TrainingVolume[]>("/training/volume", { resolution, start, end }),
  trainingPMC: (start?: string, end?: string) =>
    get<PMCPoint[]>("/training/pmc", { start, end }),
  trainingPMCProjection: (weeks = 10) =>
    get<PMCProjection>("/training/pmc/projection", { weeks }),
  // Goals
  goalsList: () => get<Goal[]>("/goals"),
  goalsCreate: (name: string, event_date: string, target_ctl?: number) =>
    fetch("/api/goals", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ name, event_date, target_ctl }),
    }).then(r => r.json()) as Promise<Goal>,
  goalsDelete: (id: number) =>
    fetch(`/api/goals/${id}`, { method: "DELETE", headers: authHeader() }).then(r => r.json()),
  trainingYoY: (sport: "running" | "cycling") =>
    get<YoYResponse>("/training/yoy", { sport }),
  trainingHRV: (start?: string, end?: string) =>
    get<HRVPoint[]>("/training/hrv", { start, end }),
  trainingStravaInsights: (resolution: Resolution, start?: string, end?: string) =>
    get<StravaInsights[]>("/training/strava_insights", { resolution, start, end }),
  // Apple Health Auto Export integration
  healthStatus: () => get<{ last_ingest: number | null; total_added: number; webhook_url: string }>("/health/status"),
  // Strava integration
  stravaStatus: () => get<StravaStatus>("/strava/status"),
  stravaSync: (force = false): Promise<{ status: string }> =>
    fetch(`/api/strava/sync${force ? "?force=true" : ""}`, { method: "POST", headers: authHeader() }).then(r => {
      if (!r.ok) throw new Error(`Sync failed: ${r.status}`);
      return r.json();
    }),
  stravaSyncStatus: () => get<StravaSyncResult & { status: string; error: string | null }>("/strava/sync/status"),
  activitiesList: (params: {
    sport?: string; start?: string; end?: string;
    sort_by?: string; sort_dir?: string; page?: number; page_size?: number; search?: string;
  }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v != null && q.set(k, String(v)));
    return get<{ total: number; page: number; page_size: number; records: ActivityRecord[] }>(`/activities/list?${q}`);
  },
  trainingHRZones: (start: string, end: string, hrMax?: number) => {
    const q = hrMax ? `&hr_max=${hrMax}` : "";
    return get<HRZone[]>(`/training/hr_zones?start=${start}&end=${end}${q}`);
  },
  trainingRecords: (sport: string) => get<PRRecord[]>(`/training/records?sport=${sport}`),
  // Biomarkers
  biomarkersUploads: () => get<BiomarkerUpload[]>("/biomarkers/uploads"),
  biomarkersAll: () => get<BiomarkerReading[]>("/biomarkers/all"),
  biomarkersTrends: (marker?: string) =>
    get<BiomarkerReading[]>("/biomarkers/trends", marker ? { marker } : undefined),
  biomarkersDeleteUpload: (id: number): Promise<{ deleted: number }> =>
    fetch(`/api/biomarkers/uploads/${id}`, { method: "DELETE", headers: authHeader() }).then(r => r.json()),
  biomarkersUpload: async (file: File): Promise<BiomarkersExtracted> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/biomarkers/upload", { method: "POST", headers: authHeader(), body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Upload failed" }));
      throw new Error(err.detail || "Upload failed");
    }
    return res.json();
  },
  biomarkersConfirm: async (payload: BiomarkersExtracted): Promise<{ upload_id: number; saved: number }> => {
    const res = await fetch("/api/biomarkers/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Save failed" }));
      throw new Error(err.detail || "Save failed");
    }
    return res.json();
  },
  // Garmin Connect integration
  garminStatus: () => get<GarminStatus>("/garmin/status"),
  garminConnect: (email: string, password: string, mfa_code?: string): Promise<{ connected: boolean; email: string }> =>
    fetch("/api/garmin/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ email, password, mfa_code }),
    }).then(async r => {
      if (!r.ok) { const e = await r.json(); throw new Error(e.detail || "Login failed"); }
      return r.json();
    }),
  garminDisconnect: (): Promise<{ connected: boolean }> =>
    fetch("/api/garmin/disconnect", { method: "POST", headers: authHeader() }).then(r => r.json()),
  garminSync: (force = false): Promise<{ status: string }> =>
    fetch(`/api/garmin/sync${force ? "?force=true" : ""}`, { method: "POST", headers: authHeader() }).then(r => {
      if (!r.ok) throw new Error(`Sync failed: ${r.status}`);
      return r.json();
    }),
  garminSyncStatus: () =>
    get<SyncResult & { status: string; error: string | null }>("/garmin/sync/status"),

  // AI activity search
  aiSearch: async (query: string): Promise<AISearchResult> => {
    const res = await fetch("/api/activities/ai_search", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Search failed" }));
      throw new Error(err.detail || `Error ${res.status}`);
    }
    return res.json();
  },

  // Health Adviser AI assessment
  adviserAssess: async (
    tab: string,
    start: string,
    end: string,
    data: Record<string, unknown>,
    onChunk: (text: string) => void,
    onDone: () => void,
    onError: (err: string) => void,
  ) => {
    try {
      const res = await fetch("/api/adviser/assess", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ tab, start, end, data }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Assessment failed" }));
        onError(err.detail || `Error ${res.status}`);
        return;
      }
      const reader = res.body?.getReader();
      if (!reader) { onError("No response body"); return; }
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const payload = line.slice(6).trim();
            if (payload === "[DONE]") { onDone(); return; }
            try {
              const { text } = JSON.parse(payload);
              if (text) onChunk(text);
            } catch { /* skip malformed */ }
          }
        }
      }
      onDone();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Unknown error");
    }
  },

  adviserFollowup: async (
    tab: string,
    start: string,
    end: string,
    data: Record<string, unknown>,
    conversation: { role: "user" | "assistant"; content: string }[],
    onChunk: (text: string) => void,
    onDone: () => void,
    onError: (err: string) => void,
  ) => {
    try {
      const res = await fetch("/api/adviser/followup", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ tab, start, end, data, conversation }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Follow-up failed" }));
        onError(err.detail || `Error ${res.status}`);
        return;
      }
      const reader = res.body?.getReader();
      if (!reader) { onError("No response body"); return; }
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const payload = line.slice(6).trim();
            if (payload === "[DONE]") { onDone(); return; }
            try {
              const { text } = JSON.parse(payload);
              if (text) onChunk(text);
            } catch { /* skip malformed */ }
          }
        }
      }
      onDone();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Unknown error");
    }
  },

  // Global advisor (sidebar) — simple non-streaming Q&A with full health context
  advisorAsk: async (question: string): Promise<{ answer: string }> => {
    const res = await fetch("/api/advisor/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(err.detail || `Error ${res.status}`);
    }
    return res.json();
  },
};

export interface BiomarkerUpload {
  id: number;
  filename: string;
  upload_ts: number;
  test_date: string | null;
  lab_name: string | null;
  records_extracted: number;
}

export interface BiomarkerReading {
  test_date: string;
  marker_canonical: string;
  marker_name: string;
  value: number;
  unit: string;
  ref_min: number | null;
  ref_max: number | null;
  category: string;
  status: string;
  upload_id?: number;
  lab_name?: string;
}

export interface ExtractedMarker {
  name: string;
  canonical: string;
  value: number;
  unit: string;
  ref_min: number | null;
  ref_max: number | null;
  category: string;
  status: string;
}

export interface BiomarkersExtracted {
  filename: string;
  test_date: string | null;
  lab_name: string | null;
  markers: ExtractedMarker[];
  count: number;
}

export interface AISearchResult {
  query: string;
  filters: Record<string, unknown>;
  summary: string;
  total: number;
  records: ActivityRecord[];
}

export interface GarminStatus {
  connected: boolean;
  email: string | null;
  last_sync: number | null;
}

export interface SyncResult {
  added: number;
  skipped: number;
}
