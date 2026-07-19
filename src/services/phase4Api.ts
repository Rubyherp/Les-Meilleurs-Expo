import {
  normalizePhase4Result,
  Phase4Result,
  Phase4ResultJson,
} from "../models/Phase4Result";

declare const process: { env?: Record<string, string | undefined> };

/**
 * There is intentionally no baked-in server address. Pass a route owned by
 * the deployment, or set EXPO_PUBLIC_API_URL in the Expo environment.
 */
export function getPhase4ApiBaseUrl(): string | undefined {
  const value = typeof process !== "undefined" ? process.env?.EXPO_PUBLIC_API_URL?.trim() : undefined;
  return value ? value.replace(/\/$/, "") : undefined;
}

export async function loadPhase4Result(
  endpoint: string,
  options?: { baseUrl?: string; signal?: AbortSignal }
): Promise<Phase4Result | null> {
  const baseUrl = options?.baseUrl ?? getPhase4ApiBaseUrl();
  if (!baseUrl && !/^https?:\/\//i.test(endpoint)) return null;

  const url = /^https?:\/\//i.test(endpoint)
    ? endpoint
    : `${baseUrl}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  try {
    const response = await fetch(url, { signal: options?.signal });
    if (!response.ok) return null;

    const payload = (await response.json()) as Phase4ResultJson & {
      metadata?: Phase4ResultJson;
      result?: Phase4ResultJson;
    };
    return normalizePhase4Result(payload.metadata ?? payload.result ?? payload);
  } catch {
    // A configured API is optional; callers can keep showing the mock result.
    return null;
  }
}
