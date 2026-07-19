import { getPhase4ApiBaseUrl } from "./phase4Api";
import { normalizePhase5Result, Phase5Result, Phase5ResultJson } from "../models/Phase5Result";

/** The endpoint remains explicit so deployments can choose their own route. */
export async function loadPhase5Result(
  endpoint: string,
  options?: { baseUrl?: string; signal?: AbortSignal }
): Promise<Phase5Result | null> {
  const baseUrl = options?.baseUrl ?? getPhase4ApiBaseUrl();
  if (!baseUrl && !/^https?:\/\//i.test(endpoint)) return null;
  const url = /^https?:\/\//i.test(endpoint)
    ? endpoint
    : `${baseUrl}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;

  try {
    const response = await fetch(url, { signal: options?.signal });
    if (!response.ok) return null;
    const payload = (await response.json()) as Phase5ResultJson & {
      metadata?: Phase5ResultJson;
      result?: Phase5ResultJson;
      comparison?: Phase5ResultJson;
    };
    return normalizePhase5Result(payload.metadata ?? payload.comparison ?? payload.result ?? payload);
  } catch {
    // Comparison is an optional enhancement; mock analysis should remain usable.
    return null;
  }
}
