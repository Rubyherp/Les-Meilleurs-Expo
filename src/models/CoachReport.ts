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

export interface CoachPhaseJson {
  phase: number;
  name: string;
  available: boolean;
  source: string;
  summary: string;
  strengths: string[];
  issues: CoachPhaseIssueJson[];
  suggestions: string[];
  confidence: number;
}

export interface CoachReportJson {
  session_id: string;
  report_version: number;
  mode: "single" | "comparison";
  overall_summary: string;
  phases: CoachPhaseJson[];
  generated_at: string;
  llm_model_used: string | null;
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

export interface CoachPhase {
  phase: number;
  name: string;
  available: boolean;
  source: string;
  summary: string;
  strengths: string[];
  issues: CoachPhaseIssue[];
  suggestions: string[];
  confidence: number;
}

export interface CoachReport {
  sessionId: string;
  reportVersion: number;
  mode: "single" | "comparison";
  overallSummary: string;
  phases: CoachPhase[];
  generatedAt: string;
  llmModelUsed: string | null;
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

function normalizeCoachPhase(json: CoachPhaseJson): CoachPhase {
  return {
    phase: json.phase,
    name: json.name,
    available: json.available,
    source: json.source,
    summary: json.summary,
    strengths: json.strengths,
    issues: json.issues.map(normalizeCoachPhaseIssue),
    suggestions: json.suggestions,
    confidence: json.confidence,
  };
}

function normalizeCoachReport(json: CoachReportJson): CoachReport {
  return {
    sessionId: json.session_id,
    reportVersion: json.report_version,
    mode: json.mode,
    overallSummary: json.overall_summary,
    phases: json.phases.map(normalizeCoachPhase),
    generatedAt: json.generated_at,
    llmModelUsed: json.llm_model_used,
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