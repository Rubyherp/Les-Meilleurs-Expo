import { DanceIssue } from "./DanceIssue";

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
}
