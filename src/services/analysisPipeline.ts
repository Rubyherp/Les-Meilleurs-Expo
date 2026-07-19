import { DanceSession } from "../models/DanceSession";
import { AnalysisResult } from "../models/AnalysisResult";
import { mockAnalyze } from "./mockAnalysis";

export interface PreparedDanceInput {
  sessionID: string;
  title: string;
  recordedAt: number;
  sourceIdentifier: string;
  duration: number;
  frameCount: number;
  participantIDs: string[];
}

async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function preprocessPhone(
  session: DanceSession
): Promise<PreparedDanceInput> {
  await delay(500);
  return {
    sessionID: session.id,
    title: session.title,
    recordedAt: session.recordedAt,
    sourceIdentifier: `phone://preprocessed/${session.id}`,
    duration: session.duration,
    frameCount: Math.max(1, Math.floor(session.duration * 30)),
    participantIDs: session.participantIDs,
  };
}

export async function analyzeSession(
  session: DanceSession
): Promise<AnalysisResult> {
  await preprocessPhone(session);
  await delay(900);
  return mockAnalyze(session.id, session.participantIDs, session.duration);
}
