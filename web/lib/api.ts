// Typed client for the Round Zero FastAPI backend (api/main.py).
// The browser talks to FastAPI directly (CORS enabled) so SSE isn't buffered by a proxy.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ReviewMode = "live" | "replay" | "auto";
export type Severity = "high" | "medium" | "low";

export interface Contact {
  name: string;
  role: string;
}

export interface Client {
  id: string;
  name: string;
  industry: string;
  contacts: Contact[];
  brand: { palette: Record<string, string>; fonts: Record<string, string>; voice: string };
  brand_after_rebrand: Client["brand"] | null;
  banks: { id: string; label: string }[];
}

export interface Draft {
  file: string;
  client: string;
  project: string;
  format: string;
  url: string;
  notes: string | null;
  planted: string[];
  uploaded?: boolean;
}

export interface Citation {
  document_id: string;
  quote: string;
  author: string;
  role: string;
  date: string;
  project_name: string | null;
  round: string | null;
  kind: string;
}

export interface Flag {
  severity: Severity;
  topic: string;
  issue: string;
  suggestion: string;
  evidence: string[];
  directive: string | null;
  citations: Citation[];
  observations: string[];
}

export interface Review {
  client_id: string;
  bank_id: string | null;
  memory: boolean;
  engine: string;
  verdict: "ready_for_client" | "needs_changes";
  summary: string;
  flags: Flag[];
  discarded: { flag: Omit<Flag, "citations" | "observations">; reason: string }[];
  memories_consulted: number;
  elapsed_s: number;
  timings: Record<string, number>;
  source: "live" | "replay";
  recorded_at: string | null;
}

export interface ReviewEvent {
  stage: "extract" | "recall" | "evidence" | "reflect" | "verify" | "done" | "error";
  status: "start" | "progress" | "done";
  message: string;
  data: Record<string, unknown>;
  t: number;
}

export interface Observation {
  id: string;
  text: string;
  proof_count: number;
  sources: number;
  updated_at: string;
}

export interface TasteProfile {
  bank: string;
  total: number;
  topics: Record<string, Observation[]>;
}

export interface ObservationChange {
  previous_text: string;
  changed_at: string | null;
  source_facts: string[];
}

export interface ProjectRow {
  project_id: string;
  name: string;
  format: string;
  phase: string;
  started: string;
  rounds: number;
  approved: boolean;
  reviewed_with_round_zero: boolean;
  source: "history" | "logged";
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  clients: () => get<Client[]>("/api/clients"),
  drafts: () => get<Draft[]>("/api/drafts"),
  projects: (clientId: string) => get<ProjectRow[]>(`/api/clients/${clientId}/projects`),
  profile: (bank: string) => get<TasteProfile>(`/api/banks/${bank}/profile`),
  history: (bank: string, id: string) => get<ObservationChange[]>(`/api/banks/${bank}/observations/${id}/history`),
  operations: (bank: string) => get<{ active: number; types: string[] }>(`/api/banks/${bank}/operations`),
  config: () => get<{ review_mode: ReviewMode; topics: string[] }>("/api/config"),

  async logFeedback(body: Record<string, unknown>, bank?: string) {
    const q = bank ? `?bank=${encodeURIComponent(bank)}` : "";
    const res = await fetch(`${API_URL}/api/feedback${q}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.json() as Promise<{ bank: string; document_id: string; project_id: string }>;
  },

  async uploadDraft(file: File, client: string, project: string, format: string): Promise<Draft> {
    const form = new FormData();
    form.set("file", file);
    form.set("client", client);
    form.set("project", project);
    form.set("format", format);
    const res = await fetch(`${API_URL}/api/drafts`, { method: "POST", body: form });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.json();
  },
};

export interface StreamParams {
  draft: Draft;
  memory: boolean;
  bank?: string;
  mode: ReviewMode;
  speed?: number;
}

export interface StreamHandlers {
  onStart?: (info: { has_recording: boolean; mode: ReviewMode }) => void;
  onEvent: (e: ReviewEvent) => void;
  onResult: (r: Review) => void;
  onError: (message: string) => void;
}

/** Open the SSE review stream. Returns a function that cancels it. */
export function streamReview(p: StreamParams, h: StreamHandlers): () => void {
  const q = new URLSearchParams({
    file: p.draft.file,
    client: p.draft.client,
    project: p.draft.project,
    format: p.draft.format,
    memory: String(p.memory),
    mode: p.mode,
    speed: String(p.speed ?? 1),
  });
  if (p.memory && p.bank) q.set("bank", p.bank);
  const es = new EventSource(`${API_URL}/api/review/stream?${q}`);
  let finished = false;
  es.addEventListener("start", (e) => h.onStart?.(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("progress", (e) => h.onEvent(JSON.parse((e as MessageEvent).data)));
  es.addEventListener("result", (e) => {
    finished = true;
    h.onResult(JSON.parse((e as MessageEvent).data));
    es.close();
  });
  es.addEventListener("error", (e) => {
    const data = (e as MessageEvent).data;
    if (data) {
      finished = true;
      h.onError(JSON.parse(data).message);
      es.close();
    } else if (!finished) {
      finished = true;
      h.onError("Lost connection to the Round Zero API");
      es.close();
    }
  });
  return () => {
    finished = true;
    es.close();
  };
}

export const assetUrl = (path: string) => `${API_URL}${path}`;

export function formatDate(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T12:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
