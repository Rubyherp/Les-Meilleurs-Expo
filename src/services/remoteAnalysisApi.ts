import { CalibrationCorners } from "../models/Calibration";
import { Phase4ResultJson } from "../models/Phase4Result";

declare const process: { env?: Record<string, string | undefined> };

const API_PREFIX = "/api/v1";
const REQUEST_TIMEOUT_MS = 20_000;
const POLL_INTERVAL_MS = 1_500;
const POLL_TIMEOUT_MS = 15 * 60 * 1_000;

export interface RemoteSessionResponse {
  session_id: string;
  status: string;
}

export interface RemoteUploadResponse {
  session_id: string;
  media_id: string;
  task_id: string;
  status: string;
}

export interface RemoteTaskResponse {
  task_id: string;
  session_id: string;
  status: string;
  progress: number;
  error?: string | null;
  result?: Record<string, unknown> | null;
}

export interface RemoteResultsResponse {
  session_id: string;
  task_id: string;
  created_at: string;
  metadata: Phase4ResultJson;
}

export class RemoteAnalysisError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "RemoteAnalysisError";
    this.status = status;
  }
}

export function getRemoteApiBaseUrl(): string | undefined {
  const configured =
    typeof process !== "undefined" ? process.env?.EXPO_PUBLIC_API_URL?.trim() : undefined;
  if (!configured) return undefined;
  const base = configured.replace(/\/$/, "");
  return base.endsWith(API_PREFIX) ? base : `${base}${API_PREFIX}`;
}

function requireBaseUrl(): string {
  const baseUrl = getRemoteApiBaseUrl();
  if (!baseUrl) {
    throw new RemoteAnalysisError(
      "Remote analysis is not configured. Set EXPO_PUBLIC_API_URL and try again."
    );
  }
  return baseUrl;
}

function joinUrl(baseUrl: string, path: string): string {
  return `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
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
    const body = await response.json().catch(() => undefined);
    if (!response.ok) {
      const detail =
        body && typeof body === "object" && "detail" in body
          ? String((body as { detail?: unknown }).detail)
          : `Request failed with HTTP ${response.status}.`;
      throw new RemoteAnalysisError(detail, response.status);
    }
    return body as T;
  } catch (error) {
    if (error instanceof RemoteAnalysisError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new RemoteAnalysisError("The analysis server took too long to respond.");
    }
    throw new RemoteAnalysisError(
      error instanceof Error ? error.message : "The analysis server could not be reached."
    );
  } finally {
    clearTimeout(timeout);
  }
}

export async function createRemoteSession(): Promise<RemoteSessionResponse> {
  return request<RemoteSessionResponse>("/sessions", { method: "POST" });
}

export async function submitCalibration(
  sessionID: string,
  corners: CalibrationCorners
): Promise<void> {
  await request(`/sessions/${encodeURIComponent(sessionID)}/calibration`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ points: corners.map((corner) => [corner.x, corner.y]) }),
  });
}

function fileNameForUri(uri: string): string {
  const lastPart = uri.split("/").pop()?.split("?")[0];
  if (lastPart && /\.[a-z0-9]+$/i.test(lastPart)) return lastPart;
  return `attempt-${Date.now()}.mp4`;
}

function mimeTypeForName(name: string): string {
  const extension = name.split(".").pop()?.toLowerCase();
  if (extension === "mov") return "video/quicktime";
  if (extension === "webm") return "video/webm";
  if (extension === "mkv") return "video/x-matroska";
  return "video/mp4";
}

export async function uploadAttemptVideo(
  sessionID: string,
  uri: string,
  options?: { name?: string; type?: string }
): Promise<RemoteUploadResponse> {
  const name = options?.name ?? fileNameForUri(uri);
  const form = new FormData();
  form.append(
    "video",
    {
      uri,
      name,
      type: options?.type ?? mimeTypeForName(name),
    } as unknown as Blob
  );
  return request<RemoteUploadResponse>(`/sessions/${encodeURIComponent(sessionID)}/upload`, {
    method: "POST",
    body: form,
  });
}

export async function getTaskStatus(taskID: string): Promise<RemoteTaskResponse> {
  return request<RemoteTaskResponse>(`/tasks/${encodeURIComponent(taskID)}`);
}

export async function pollRemoteTask(
  taskID: string,
  options?: {
    onStatus?: (status: RemoteTaskResponse) => void;
    intervalMs?: number;
    timeoutMs?: number;
  }
): Promise<RemoteTaskResponse> {
  const startedAt = Date.now();
  const intervalMs = options?.intervalMs ?? POLL_INTERVAL_MS;
  const timeoutMs = options?.timeoutMs ?? POLL_TIMEOUT_MS;
  while (Date.now() - startedAt < timeoutMs) {
    const status = await getTaskStatus(taskID);
    options?.onStatus?.(status);
    if (status.status === "completed") return status;
    if (status.status === "failed") {
      throw new RemoteAnalysisError(status.error || "The server could not finish this analysis.");
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new RemoteAnalysisError("The analysis is taking longer than expected. Please retry.");
}

export async function getRemoteResults(sessionID: string): Promise<RemoteResultsResponse> {
  return request<RemoteResultsResponse>(`/sessions/${encodeURIComponent(sessionID)}/results`);
}
