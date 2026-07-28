import { logger } from "../utils/logger";
import type { CoachReportResponseJson } from "../models/CoachReport";

declare const process: { env?: Record<string, string | undefined> };

const API_PREFIX = "/api/v1";
const REQUEST_TIMEOUT_MS = 20_000;

// ── Error ───────────────────────────────────────────────────────────────────

export class CoachApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "CoachApiError";
    this.status = status;
  }
}

// ── URL helpers ─────────────────────────────────────────────────────────────

function getApiBaseUrl(): string | undefined {
  const configured =
    typeof process !== "undefined"
      ? process.env?.EXPO_PUBLIC_API_URL?.trim()
      : undefined;
  if (!configured) return undefined;
  const base = configured.replace(/\/$/, "");
  return base.endsWith(API_PREFIX) ? base : `${base}${API_PREFIX}`;
}

function requireBaseUrl(): string {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    throw new CoachApiError(
      "Coach API is not configured. Set EXPO_PUBLIC_API_URL and try again."
    );
  }
  return baseUrl;
}

function joinUrl(baseUrl: string, path: string): string {
  return `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

// ── Generic request helper ──────────────────────────────────────────────────

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  logger.api.request(method, path);
  const startedAt = Date.now();

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(joinUrl(requireBaseUrl(), path), {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(init.headers ?? {}),
      },
    });
    logger.api.response(method, path, response.status, Date.now() - startedAt);
    const body = await response.json().catch(() => undefined);
    if (!response.ok) {
      const detail =
        body && typeof body === "object" && "detail" in body
          ? String((body as { detail?: unknown }).detail)
          : `Coach request failed with HTTP ${response.status}.`;
      throw new CoachApiError(detail, response.status);
    }
    return body as T;
  } catch (error) {
    if (error instanceof CoachApiError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new CoachApiError("The coach server took too long to respond.");
    }
    throw new CoachApiError(
      error instanceof Error
        ? error.message
        : "The coach server could not be reached."
    );
  } finally {
    clearTimeout(timeout);
  }
}

// ── Public API ──────────────────────────────────────────────────────────────

/**
 * POST /sessions/{sessionId}/coach — trigger AI coaching for a session.
 * Returns the coaching report (or null if the session is not eligible).
 */
export async function requestCoachReport(
  sessionId: string
): Promise<CoachReportResponseJson> {
  return request<CoachReportResponseJson>(
    `/sessions/${encodeURIComponent(sessionId)}/coach`,
    { method: "POST" }
  );
}

/**
 * GET /sessions/{sessionId}/coach — retrieve an existing coaching report.
 * Returns the same shape as the POST variant.
 */
export async function getCoachReport(
  sessionId: string
): Promise<CoachReportResponseJson> {
  return request<CoachReportResponseJson>(
    `/sessions/${encodeURIComponent(sessionId)}/coach`
  );
}
