import { DanceIssue } from "./DanceIssue";
import { Phase4Result } from "./Phase4Result";
import { Phase5Result } from "./Phase5Result";

export interface ParticipantAnalysisResult {
  participantID: string;
  score: number;
  issues: DanceIssue[];
}

export interface AnalysisResult {
  id: string;
  sessionID: string;
  analyzedAt: number; // unix ms
  overallScore: number;
  issues: DanceIssue[];
  participantResults: ParticipantAnalysisResult[];
  /** Present only when the analysis service has returned Phase 4 metadata. */
  phase4?: Phase4Result;
  /** Present only when a reference/attempt comparison is available. */
  comparison?: Phase5Result;
}
