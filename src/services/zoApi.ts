import type { ZoExportRequest, ZoExportResponse } from "@/models/ZoExport";

const API_PREFIX = "/api/v1";

function url(path: string) {
  const base = (process.env?.EXPO_PUBLIC_API_URL?.trim() ?? "").replace(/\/$/, "");
  const prefix = base.endsWith(API_PREFIX) ? base : `${base}${API_PREFIX}`;
  return `${prefix}${path}`;
}

export async function exportToZo(sessionId: string, payload: ZoExportRequest): Promise<ZoExportResponse> {
  const response = await fetch(url(`/sessions/${encodeURIComponent(sessionId)}/exports/zo`), {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail ?? `Zo export failed (${response.status}).`);
  return body as ZoExportResponse;
}
