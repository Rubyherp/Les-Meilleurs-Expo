import { normalizeEvidenceMoment, type EvidenceMoment, type EvidenceMomentJson } from "./EvidenceMoment";
import { normalizeIntegrationRun, type IntegrationRun, type IntegrationRunJson } from "./IntegrationRun";

/**
 * Wire-format and normalized types for the AI Coach report.
 *
 * Backend contract:
 *   POST /api/v1/sessions/{sessionId}/coach — trigger coaching
 *   GET  /api/v1/sessions/{sessionId}/coach — retrieve existing report
 *
 * Both endpoints return the same response shape:
 *   { session_id, status, report, message }
 */

// ── Wire format (snake_case) ────────────────────────────────────────────────

export type CoachStatusJson = "completed" | "pending" | "not_configured" | "no_data" | "no_key";

export interface CoachPhaseIssueJson {
  description: string;
  severity: "low" | "medium" | "high";
  category: string | null;
}

export interface CoachEvidenceJson {
  metric: string;
  value: number | string;
  unit: string | null;
  start_seconds: number | null;
  end_seconds: number | null;
  dancer_ids: number[];
}

export interface CoachAgentJson {
  agent_id?: number;
  phase?: number;
  name: string;
  available: boolean;
  source: string;
  summary: string;
  strengths: string[];
  issues: CoachPhaseIssueJson[];
  suggestions: string[];
  evidence?: CoachEvidenceJson[];
  confidence: number;
}

export interface CoachReportJson {
  session_id: string;
  report_version: number;
  mode: "single" | "comparison";
  practice_type?: "solo" | "group";
  overall_summary: string;
  agents?: CoachAgentJson[];
  phases?: CoachAgentJson[];
  coordination_notes?: string[];
  generated_at: string;
  llm_model_used: string | null;
  evidence_moments?: EvidenceMomentJson[];
  integrations?: IntegrationRunJson[];
  trace_id?: string | null;
}

export interface CoachResponseJson {
  session_id: string;
  status: CoachStatusJson;
  report: CoachReportJson | null;
  message?: string;
}

// ── Normalized (camelCase) ──────────────────────────────────────────────────

export type CoachStatus = "completed" | "pending" | "not_configured" | "no_data" | "no_key";

export interface CoachPhaseIssue {
  description: string;
  severity: "low" | "medium" | "high";
  category: string | null;
}

export interface CoachEvidence {
  metric: string;
  value: number | string;
  unit: string | null;
  startSeconds: number | null;
  endSeconds: number | null;
  dancerIds: number[];
}

export interface CoachAgent {
  agentId: number;
  name: string;
  available: boolean;
  source: string;
  summary: string;
  strengths: string[];
  issues: CoachPhaseIssue[];
  suggestions: string[];
  evidence: CoachEvidence[];
  confidence: number;
}

export interface CoachReport {
  sessionId: string;
  reportVersion: number;
  mode: "single" | "comparison";
  practiceType: "solo" | "group";
  overallSummary: string;
  agents: CoachAgent[];
  coordinationNotes: string[];
  generatedAt: string;
  llmModelUsed: string | null;
  evidenceMoments: EvidenceMoment[];
  integrations: IntegrationRun[];
  traceId: string | null;
}

export interface CoachResponse {
  sessionId: string;
  status: CoachStatus;
  report: CoachReport | null;
  message?: string;
}

// ── Normalizers ─────────────────────────────────────────────────────────────

function normalizeCoachPhaseIssue(json: CoachPhaseIssueJson): CoachPhaseIssue {
  return {
    description: json.description,
    severity: json.severity,
    category: json.category,
  };
}

function normalizeCoachEvidence(json: CoachEvidenceJson): CoachEvidence {
  return {
    metric: json.metric,
    value: json.value,
    unit: json.unit,
    startSeconds: json.start_seconds,
    endSeconds: json.end_seconds,
    dancerIds: json.dancer_ids,
  };
}

function normalizeCoachAgent(json: CoachAgentJson): CoachAgent {
  return {
    agentId: json.agent_id ?? json.phase ?? 0,
    name: json.name,
    available: json.available,
    source: json.source,
    summary: json.summary,
    strengths: json.strengths,
    issues: json.issues.map(normalizeCoachPhaseIssue),
    suggestions: json.suggestions,
    evidence: (json.evidence ?? []).map(normalizeCoachEvidence),
    confidence: json.confidence,
  };
}

function normalizeCoachReport(json: CoachReportJson): CoachReport {
  return {
    sessionId: json.session_id,
    reportVersion: json.report_version,
    mode: json.mode,
    practiceType: json.practice_type ?? "solo",
    overallSummary: json.overall_summary,
    agents: (json.agents ?? json.phases ?? []).map(normalizeCoachAgent),
    coordinationNotes: json.coordination_notes ?? [],
    generatedAt: json.generated_at,
    llmModelUsed: json.llm_model_used,
    evidenceMoments: (json.evidence_moments ?? []).map(normalizeEvidenceMoment).filter((value): value is EvidenceMoment => value !== null),
    integrations: (json.integrations ?? []).map(normalizeIntegrationRun),
    traceId: json.trace_id ?? null,
  };
}

export function normalizeCoachResponse(json: CoachResponseJson): CoachResponse {
  return {
    sessionId: json.session_id,
    status: json.status,
    report: json.report ? normalizeCoachReport(json.report) : null,
    message: json.message,
  };
}
