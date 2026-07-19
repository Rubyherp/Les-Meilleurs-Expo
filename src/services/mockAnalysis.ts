import { AnalysisResult, ParticipantAnalysisResult } from "../models/AnalysisResult";
import { DanceIssue, IssueCategory, IssueSeverity } from "../models/DanceIssue";

function stableHash(str: string): number {
  let hash = 17;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash * 31 + str.codePointAt(i)!) % 10_000 + 10_000) % 10_000;
  }
  return hash;
}

function deterministicUUID(str: string): string {
  const bytes = new Uint8Array(16);
  const encoder = new TextEncoder();
  const encoded = encoder.encode(str);
  for (let i = 0; i < encoded.length; i++) {
    const slot = i % 16;
    bytes[slot] = (bytes[slot] * 31 + encoded[i]) & 0xff;
    bytes[(slot + 7) % 16] ^= encoded[i];
  }
  const hex = Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function mockAnalyze(
  sessionID: string,
  participantIDs: string[],
  duration: number
): Promise<AnalysisResult> {
  const seed = stableHash(sessionID);
  const score = 0.72 + (seed % 21) / 100.0;

  const timingIssue: DanceIssue = {
    id: deterministicUUID(`${sessionID}-timing`),
    category: IssueCategory.Timing,
    severity: IssueSeverity.Suggestion,
    message: "A few transitions could land more consistently on the beat.",
    timestamp: Math.min(duration, 12),
  };

  const spacingIssue: DanceIssue = {
    id: deterministicUUID(`${sessionID}-spacing`),
    category: IssueCategory.Spacing,
    severity: IssueSeverity.Warning,
    message: "The group spacing changes during the middle section.",
    timestamp: Math.min(duration, 28),
  };

  const participantResults: ParticipantAnalysisResult[] = participantIDs.map(
    (pid, index) => {
      const pSeed = stableHash(pid);
      const pScore = Math.max(
        0,
        Math.min(1, score - 0.04 + ((pSeed + index) % 9) / 100.0)
      );
      return {
        participantID: pid,
        score: pScore,
        issues: index % 2 === 0 ? [timingIssue] : [],
      };
    }
  );

  return {
    id: deterministicUUID(`${sessionID}-result`),
    sessionID,
    analyzedAt: Date.now(),
    overallScore: score,
    issues: [timingIssue, spacingIssue],
    participantResults,
  };
}
