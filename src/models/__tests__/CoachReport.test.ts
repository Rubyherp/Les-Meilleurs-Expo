import {
  CoachResponseJson,
  normalizeCoachResponse,
} from "../CoachReport";

let passed = 0;
let failed = 0;

function assert(condition: boolean, label: string): void {
  if (condition) {
    passed++;
  } else {
    console.error(`FAIL: ${label}`);
    failed++;
  }
}

function assertEqual<T>(actual: T, expected: T, label: string): void {
  assert(
    actual === expected,
    `${label} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
  );
}

const response: CoachResponseJson = {
  session_id: "session-1",
  status: "completed",
  report: {
    session_id: "session-1",
    report_version: 3,
    mode: "single",
    practice_type: "group",
    overall_summary: "Group coaching team report.",
    coordination_notes: ["Timing was paused."],
    agents: [
      {
        agent_id: 1,
        name: "Observation Agent",
        available: true,
        source: "deterministic",
        summary: "Visibility was clear.",
        strengths: [],
        issues: [],
        suggestions: [],
        evidence: [
          {
            metric: "visibility_coverage",
            value: 0.9,
            unit: "ratio",
            start_seconds: null,
            end_seconds: null,
            dancer_ids: [],
          },
        ],
        confidence: 0.9,
      },
    ],
    generated_at: "2026-07-29T00:00:00Z",
    llm_model_used: null,
  },
};

const normalized = normalizeCoachResponse(response);
assertEqual(normalized.report?.practiceType, "group", "practice type normalizes");
assertEqual(normalized.report?.agents[0].agentId, 1, "agent id normalizes");
assertEqual(
  normalized.report?.agents[0].evidence[0].metric,
  "visibility_coverage",
  "evidence normalizes"
);
assertEqual(
  normalized.report?.coordinationNotes[0],
  "Timing was paused.",
  "coordination notes normalize"
);

const legacy = normalizeCoachResponse({
  ...response,
  report: response.report
    ? {
        ...response.report,
        agents: undefined,
        phases: response.report.agents?.map((agent) => ({
          ...agent,
          agent_id: undefined,
          phase: agent.agent_id,
          evidence: undefined,
        })),
        coordination_notes: undefined,
      }
    : null,
});
assertEqual(legacy.report?.agents[0].agentId, 1, "legacy phase id remains readable");
assertEqual(legacy.report?.agents[0].evidence.length, 0, "legacy evidence defaults empty");

console.log(`CoachReport tests: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
