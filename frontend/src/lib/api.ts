import useSWR from "swr";
import type {
  AgentsResponse,
  ApproveBody,
  ApproveResult,
  Autonomy,
  CaseDetail,
  CaseSummary,
  ChatBody,
  ChatResult,
  DecideBody,
  DecideResult,
  Inbox,
  Overview,
  Person,
  PollResult,
  Setup,
  SetupSectionKey,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

/** Access key for the deployed demo: opened once as ?key=..., then remembered in this browser. */
export function accessKey(): string {
  if (typeof window === "undefined") return "";
  try {
    const fromUrl = new URLSearchParams(window.location.search).get("key");
    if (fromUrl) window.localStorage.setItem("aurora_key", fromUrl);
    return fromUrl || window.localStorage.getItem("aurora_key") || "";
  } catch {
    return "";
  }
}

function keyHeaders(): Record<string, string> {
  const k = accessKey();
  return k ? { "x-aurora-key": k } : {};
}

const POLL_MS = 5000;

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", headers: keyHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { ...keyHeaders(), ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function useOverview() {
  return useSWR<Overview>("/api/overview", getJSON, { refreshInterval: POLL_MS });
}

export function useCases() {
  return useSWR<CaseSummary[]>("/api/cases", getJSON, { refreshInterval: POLL_MS });
}

export function useCase(id: string | null) {
  return useSWR<CaseDetail>(id ? `/api/cases/${encodeURIComponent(id)}` : null, getJSON, {
    refreshInterval: POLL_MS,
  });
}

/** Details for several cases at once (e.g. to sort the judgement list by the Investigator's verdict). */
export function useCaseDetails(ids: string[]) {
  return useSWR<CaseDetail[]>(
    ids.length ? `details:${ids.join(",")}` : null,
    () => Promise.all(ids.map((id) => getJSON<CaseDetail>(`/api/cases/${encodeURIComponent(id)}`))),
    { refreshInterval: POLL_MS },
  );
}

export function useSetup() {
  return useSWR<Setup>("/api/setup", getJSON, { refreshInterval: 15000 });
}

export function useAgents() {
  return useSWR<AgentsResponse>("/api/agents", getJSON, { refreshInterval: 15000 });
}

export function usePeople() {
  return useSWR<Person[]>("/api/people", getJSON, { refreshInterval: POLL_MS });
}

/** One person's inbox. 404 (endpoint not there yet) is not retried; callers derive from /api/cases instead. */
export function useInbox(name: string | null) {
  return useSWR<Inbox>(name ? `/api/people/${encodeURIComponent(name)}/inbox` : null, getJSON, {
    refreshInterval: POLL_MS,
    shouldRetryOnError: false,
  });
}

export const api = {
  confirmSetup: (section: SetupSectionKey, by: string) =>
    postJSON<unknown>(`/api/setup/confirm`, { section, by }),
  confirmSource: (path: string, by: string, table?: string) =>
    postJSON<unknown>(`/api/sources/confirm`, { path, by, table }),
  approve: (id: string, body: ApproveBody) =>
    postJSON<ApproveResult>(`/api/cases/${encodeURIComponent(id)}/approve`, body),
  decide: (id: string, body: DecideBody) =>
    postJSON<DecideResult>(`/api/cases/${encodeURIComponent(id)}/decide`, body),
  setAuto: (playbookId: string, on: boolean) =>
    postJSON<Autonomy>(`/api/playbooks/${encodeURIComponent(playbookId)}/auto?on=${on}`),
  poll: () => postJSON<PollResult>(`/api/poll`),
  chat: (body: ChatBody) => postJSON<ChatResult>(`/api/chat`, body),
};

export function fileUrl(path: string): string {
  const k = accessKey();
  return `${API_URL}/api/files/${path.split("/").map(encodeURIComponent).join("/")}${k ? `?key=${encodeURIComponent(k)}` : ""}`;
}
