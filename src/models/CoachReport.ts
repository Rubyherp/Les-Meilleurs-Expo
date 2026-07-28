/**
 * Wire-format and normalized types for the AI Coach report.
 *
 * Backend contract:
 *   POST /sessions/{sessionId}/coach -> { session_id, report, status, message }
 *   GET  /sessions/{sessionId}/coach -> { session_id, report, status, message }
 *
 * `report` is `null` when status is `not_configured` or `no_data`.
 */

// ── Status ──────────────────────────────────────────────────────────────────

export type CoachStatus =
  | "completed"
  | "processing"
  | "not_configured"
  | "no_data";

// ── Wire format (snake_case) ────────────────────────────────────────────────

export interface CoachReportAgentIssueJson {
  description: string;
  severity: string;
}

export interface CoachReportAgentJson {
  agent_name: string;
  summary: string;
  strengths: string[];
  issues: CoachReportAgentIssueJson[];
  suggestions: string[];
  confidence: number;
}

export interface CoachReportJson {
  session_id: string;
  mode: string;
  overall_summary: string;
  agents: CoachReportAgentJson[];
  generated_at: string;
}

export interface CoachReportResponseJson {
  session_id: string;
  report: CoachReportJson | null;
  status: CoachStatus;
  message?: string;
}

// ── Normalized (camelCase) ──────────────────────────────────────────────────

export interface CoachReportAgentIssue {
  description: string;
  severity: string;
}

export interface CoachReportAgent {
  agentName: string;
  summary: string;
  strengths: string[];
  issues: CoachReportAgentIssue[];
  suggestions: string[];
  confidence: number;
}

export interface CoachReport {
  sessionId: string;
  mode: string;
  overallSummary: string;
  agents: CoachReportAgent[];
  generatedAt: string;
}

export interface CoachReportResponse {
  sessionId: string;
  report: CoachReport | null;
  status: CoachStatus;
  message?: string;
}

// ── Normalizers ─────────────────────────────────────────────────────────────

function normalizeCoachReportAgentIssue(
  json: CoachReportAgentIssueJson
): CoachReportAgentIssue {
  return {
    description: json.description,
    severity: json.severity,
  };
}

function normalizeCoachReportAgent(
  json: CoachReportAgentJson
): CoachReportAgent {
  return {
    agentName: json.agent_name,
    summary: json.summary,
    strengths: json.strengths,
    issues: json.issues.map(normalizeCoachReportAgentIssue),
    suggestions: json.suggestions,
    confidence: json.confidence,
  };
}

export function normalizeCoachReport(json: CoachReportJson): CoachReport {
  return {
    sessionId: json.session_id,
    mode: json.mode,
    overallSummary: json.overall_summary,
    agents: json.agents.map(normalizeCoachReportAgent),
    generatedAt: json.generated_at,
  };
}

export function normalizeCoachReportResponse(
  json: CoachReportResponseJson
): CoachReportResponse {
  return {
    sessionId: json.session_id,
    report: json.report ? normalizeCoachReport(json.report) : null,
    status: json.status,
    message: json.message,
  };
}
