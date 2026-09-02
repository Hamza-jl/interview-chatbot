/**
 * API client.
 *
 * The access token lives in a module variable, never in localStorage: an XSS
 * payload cannot read it out of persistent storage, and it dies with the tab.
 * Longevity comes from the HttpOnly refresh cookie, which JavaScript cannot
 * read at all. Every mutating call echoes the CSRF cookie back in a header.
 */

const BASE = "/api/v1";

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
let onSessionLost: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function onLogout(handler: () => void): void {
  onSessionLost = handler;
}

function csrfCookie(): string {
  const match = document.cookie.match(/(?:^|;\s*)ic_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly fields?: string[],
  ) {
    super(message);
  }
}

function describe(status: number, body: unknown): { message: string; fields?: string[] } {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (Array.isArray(detail)) return { message: detail.join(" "), fields: detail.map(String) };
  if (typeof detail === "string") return { message: detail };
  if (status === 429) return { message: "Trop de tentatives. Merci de patienter un instant." };
  if (status >= 500) return { message: "Le service est momentanement indisponible." };
  return { message: "Une erreur est survenue." };
}

async function refresh(): Promise<boolean> {
  // Collapse concurrent 401s into a single rotation - the refresh token is
  // single-use, so parallel calls would trip the reuse detector and log the
  // user out for a security reason that never happened.
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch(`${BASE}/auth/refresh`, {
          method: "POST",
          credentials: "same-origin",
        });
        if (!res.ok) return false;
        const data = (await res.json()) as TokenResponse;
        accessToken = data.access_token;
        return true;
      } catch {
        return false;
      } finally {
        setTimeout(() => (refreshing = null), 0);
      }
    })();
  }
  return refreshing;
}

type Options = { method?: string; body?: unknown; raw?: boolean; retry?: boolean };

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const { method = "GET", body, raw = false, retry = true } = options;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    headers["X-CSRF-Token"] = csrfCookie();
  }

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (res.status === 401 && retry && accessToken !== null) {
    if (await refresh()) return api<T>(path, { ...options, retry: false });
    accessToken = null;
    onSessionLost?.();
  }

  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    const { message, fields } = describe(res.status, payload);
    throw new ApiError(res.status, message, fields);
  }

  if (res.status === 204) return undefined as T;
  if (raw) return (await res.blob()) as T;
  return (await res.json()) as T;
}

/** Blob download that still travels with the bearer token. */
export async function download(token: string, filename: string): Promise<void> {
  const res = await fetch(`${BASE}/exports/${encodeURIComponent(token)}`, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    credentials: "same-origin",
  });
  if (!res.ok) throw new ApiError(res.status, "Le telechargement a echoue.");

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function restoreSession(): Promise<TokenResponse | null> {
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      credentials: "same-origin",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as TokenResponse;
    accessToken = data.access_token;
    return data;
  } catch {
    return null;
  }
}

/* --------------------------------------------------------------------- */
/* Contracts                                                              */
/* --------------------------------------------------------------------- */
export interface User {
  id: string;
  email: string;
  full_name: string;
  organisation: string;
  role: string;
  must_change_password: boolean;
  totp_enabled: boolean;
}

export interface TokenResponse {
  access_token: string;
  expires_in: number;
  csrf_token: string;
  user: User;
}

export interface LoginResponse {
  stage: "totp_required" | "totp_enrollment" | "authenticated";
  challenge?: string;
  session?: TokenResponse;
}

export interface TotpEnrollment {
  secret: string;
  otpauth_uri: string;
  qr_svg: string;
  recovery_codes: string[];
}

export interface Structure {
  id: string;
  code: string;
  name: string;
  parent: string | null;
  template_kind: "dsi" | "entite";
}

export interface Column {
  id: string;
  label: string;
  hint: string;
  choices: string[] | null;
  required: boolean;
}

export interface Question {
  id: string;
  kind: "field" | "open" | "grid";
  section: string;
  label: string;
  prompt: string;
  help: string;
  example: string;
  columns: Column[];
  index: number;
  total: number;
}

export interface ProgressSection {
  title: string;
  total: number;
  answered: number;
  active: boolean;
}

export interface SessionState {
  id: string;
  structure: Structure;
  template_kind: string;
  status: string;
  cursor: number;
  total: number;
  answered: number;
  percent: number;
  question: Question | null;
  sections: ProgressSection[];
  /** Points still blank, in the order they are asked. */
  missing: MissingPoint[];
  /** Every question has been passed but the interview is not closed yet. */
  awaiting_review: boolean;
  /** ISO date the interview was closed, or null while it is still open. */
  completed_at: string | null;
  degraded: boolean;
  /** Model that produced the last turn, e.g. "qwen2.5:3b (local)". */
  engine: string;
}

export interface MissingPoint {
  question_id: string;
  label: string;
  section: string;
  index: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  body: string;
  intent: string | null;
  created_at: string;
}

export interface SessionDetail {
  state: SessionState;
  messages: Message[];
}

/** An extraction waiting to be verified. The interview holds until it is. */
export interface PendingAnswer {
  question_id: string;
  label: string;
  section: string;
  kind: "field" | "open" | "grid";
  prompt: string;
  help: string;
  example: string;
  columns: Column[];
  value: string | null;
  rows: Record<string, string>[] | null;
}

export interface ChatResponse {
  reply: Message;
  state: SessionState;
  intent: string;
  recorded: boolean;
  completed: boolean;
  pending: PendingAnswer | null;
}

export interface AnswerRow {
  question_id: string;
  label: string;
  section: string;
  kind: string;
  completeness: string;
  confirmed: boolean;
  value: string | null;
  rows: Record<string, string>[] | null;
  /** The question's own metadata, so any point can be opened for editing -
   *  including one never answered, which has no rows to infer columns from. */
  prompt: string;
  help: string;
  example: string;
  columns: Column[];
}

/** Where one entity stands. Counts and labels only - never answer content. */
export interface ProgressRow {
  structure_id: string;
  structure: string;
  code: string;
  template_kind: string;
  status: "non_demarre" | "in_progress" | "completed";
  session_id: string | null;
  answered: number;
  total: number;
  percent: number;
  missing: string[];
  participant: { name: string; email: string } | null;
  started_at: string | null;
  last_activity_at: string | null;
  completed_at: string | null;
}

export interface ProgressReport {
  structures: number;
  not_started: number;
  in_progress: number;
  completed: number;
  points_answered: number;
  points_total: number;
  rows: ProgressRow[];
}

export interface ResetReport {
  session_id: string;
  structure: string;
  previous_status: string;
  answers_deleted: number;
  messages_deleted: number;
}

export interface ExportResult {
  id: string;
  filename: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
  download_token: string;
}

export interface Contact {
  name: string;
  email: string;
  phone: string;
}
