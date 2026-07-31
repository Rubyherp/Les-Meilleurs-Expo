export type IntegrationProvider = "gmi" | "agnes" | "openai" | "zo";
export type IntegrationStatus = "not_configured" | "pending" | "running" | "completed" | "fallback" | "failed";

export interface IntegrationRunJson {
  provider: IntegrationProvider;
  product: string;
  model?: string | null;
  status: IntegrationStatus;
  latency_ms?: number | null;
  fallback_reason?: string | null;
  request_id?: string | null;
}

export interface IntegrationRun {
  provider: IntegrationProvider;
  product: string;
  model: string | null;
  status: IntegrationStatus;
  latencyMs: number | null;
  fallbackReason: string | null;
  requestId: string | null;
}

export function normalizeIntegrationRun(value: IntegrationRunJson): IntegrationRun {
  return {
    provider: value.provider,
    product: value.product,
    model: value.model ?? null,
    status: value.status,
    latencyMs: Number.isFinite(value.latency_ms) ? value.latency_ms! : null,
    fallbackReason: value.fallback_reason ?? null,
    requestId: value.request_id ?? null,
  };
}
