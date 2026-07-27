// src/utils/logger.ts

type LogCategory =
  | "UI:PRESS"
  | "UI:NAV"
  | "UI:INPUT"
  | "API:REQ"
  | "API:RES"
  | "PHASE"
  | "STORE"
  | "ERROR"
  | "SYSTEM";

function safeLog(category: LogCategory, message: string, data?: unknown) {
  try {
    const now = new Date();
    const timestamp =
      now.toISOString().slice(11, 23); // "HH:MM:SS.mmm"
    const prefix = `[${timestamp}][${category}]`;
    if (data !== undefined) {
      console.log(prefix, message, data);
    } else {
      console.log(prefix, message);
    }
  } catch {
    // Never let logging crash the app
  }
}

export const logger = {
  ui: {
    press: (label: string) => safeLog("UI:PRESS", label),
    navigate: (from: string, to: string) =>
      safeLog("UI:NAV", `${from} → ${to}`),
    input: (field: string, action: string) =>
      safeLog("UI:INPUT", `${field}: ${action}`),
  },
  api: {
    request: (method: string, path: string) =>
      safeLog("API:REQ", `${method} ${path}`),
    response: (
      method: string,
      path: string,
      status: number,
      durationMs: number,
    ) =>
      safeLog(
        "API:RES",
        `${method} ${path} → ${status} (${durationMs}ms)`,
      ),
  },
  phase: (message: string) => safeLog("PHASE", message),
  store: {
    action: (name: string, payload?: unknown) =>
      safeLog("STORE", name, payload),
  },
  error: (context: string, err: unknown) =>
    safeLog("ERROR", `${context}: ${err instanceof Error ? err.message : String(err)}`),
  system: (message: string) => safeLog("SYSTEM", message),
};
