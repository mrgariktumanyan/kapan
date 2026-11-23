// Клиент API. Токен хранится в sessionStorage (сбрасывается при закрытии вкладки).
const TOKEN_KEY = "kapan_token";

export function getToken(): string | null {
  try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY); } catch { /* недоступно */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !(init.body instanceof URLSearchParams))
    headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) { setToken(null); if (!path.endsWith("/login")) window.location.assign("/login"); }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* не JSON */ }
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  get: <T>(p: string) => request<T>(p),
  post: <T>(p: string, body?: unknown) =>
    request<T>(p, { method: "POST", body: body instanceof FormData || body instanceof URLSearchParams ? body : JSON.stringify(body ?? {}) }),
  patch: <T>(p: string, body: unknown) => request<T>(p, { method: "PATCH", body: JSON.stringify(body) }),
};

// ---- Типы API ----
export type Role = "admin" | "planner" | "surveyor" | "geologist" | "management";
export interface User { id: number; username: string; full_name: string; role: Role }
export interface Project { id: number; name: string; description: string; crs: string; units: string; settings: Record<string, unknown> }
export interface Mine { id: number; project_id: number; name: string }
export interface Level { id: number; mine_id: number; name: string; elevation: number | null }
export interface Stope {
  id: number; level_id: number; name: string; orebody: string; area: string; status: string;
  level_name: string; mine_name: string; bbox: number[][] | null;
  last_analysis: { id: number; version: number; finished_at: string | null; ore_loss_pct: number | null; dilution_pct: number | null } | null;
}
export interface Check { code: string; level: "ok" | "warning" | "error"; message: string; details: Record<string, unknown> }
export interface StoredFile {
  id: number; stope_id: number; category: string; model_role: string; version: number; original_name: string;
  file_format: string; sha256: string; size_bytes: number; validation_status: "ok" | "warning" | "error";
  validation_report: Check[]; summary: Record<string, unknown>; is_active: boolean; uploaded_at: string;
}
export interface Analysis {
  id: number; stope_id: number; version: number; status: "queued" | "running" | "done" | "failed";
  progress: number; message: string; params: Record<string, number>; engine_version: string;
  inputs: Record<string, { file_id: number; sha256: string; name: string; version: number }>;
  created_at: string; finished_at: string | null; result?: ReconResult | null;
}
export type Zones = Record<string, number>;
export interface ReconResult {
  engine_version: string; formulas: Record<string, string>; warnings: string[]; params: Record<string, number>;
  checks: Record<string, number>; input_quality: Record<string, string>;
  ore_loss: Record<string, number | null> & { by_zone: Zones; metal_loss: Record<string, number>; areas: Area[]; by_elevation: Bin[] };
  dilution: Record<string, number | null> & { by_zone: Zones; areas: Area[]; by_elevation: Bin[]; grade_actual: Record<string, number> };
  conformance: Record<string, number | null> & { overbreak_by_zone: Zones; underbreak_by_zone: Zones };
}
export interface Area { id: number; volume_m3: number; centroid: number[]; bbox_min: number[]; bbox_max: number[]; dominant_zone: string }
export interface Bin { z_from: number; z_to: number; volume_m3: number }
