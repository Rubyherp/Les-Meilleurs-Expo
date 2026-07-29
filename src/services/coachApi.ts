import { logger } from "@/utils/logger";
import { CoachResponseJson, normalizeCoachResponse } from "@/models/CoachReport";
import type { CoachResponse } from "@/models/CoachReport";

const API_PREFIX = "/api/v1";
const TIMEOUT_MS = 20_000;

function getApiBaseUrl(): string {
  const configured = process.env?.EXPO_PUBLIC_API_URL?.trim();
  if (!configured) return "";
  const base = configured.replace(/\/$/, "");
  return base;
}

function buildUrl(path: string): string {
  const base = getApiBaseUrl();
  const fullBase = base.endsWith(API_PREFIX) ? base : `${base}${API_PREFIX}`;
  return `${fullBase}${path.startsWith("/") ? path : `/${path}`}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = buildUrl(path);
  const method = init.method ?? "GET";
  logger.api.request(method, path);
  
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      ...init,
      signal: controller.signal,
      headers: { Accept: "application/json", ...(init.headers ?? {}) },
    });
    const body = await response.json().catch(() => undefined);
    if (!response.ok) {
      throw new Error(body?.detail ?? `Coach request failed (${response.status}).`);
    }
    return body as T;
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error("Coach server timed out.");
    }
    throw err instanceof Error ? err : new Error("Coach server unreachable.");
  } finally {
    clearTimeout(timeout);
  }
}

export async function triggerCoach(
  sessionId: string,
  isGroup: boolean
): Promise<CoachResponse> {
  const json = await request<CoachResponseJson>(
    `/sessions/${encodeURIComponent(sessionId)}/coach`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_group: isGroup }),
    }
  );
  return normalizeCoachResponse(json);
}

export async function getCoachReport(sessionId: string): Promise<CoachResponse> {
  const json = await request<CoachResponseJson>(
    `/sessions/${encodeURIComponent(sessionId)}/coach`
  );
  return normalizeCoachResponse(json);
}
