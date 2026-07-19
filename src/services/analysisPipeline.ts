import { DanceSession } from "../models/DanceSession";
import { AnalysisResult } from "../models/AnalysisResult";
import {
  DEFAULT_CALIBRATION_CORNERS,
} from "../models/Calibration";
import { normalizePhase4Result } from "../models/Phase4Result";
import { mockAnalyze } from "./mockAnalysis";
import {
  createRemoteSession,
  getRemoteApiBaseUrl,
  getRemoteResults,
  pollRemoteTask,
  submitCalibration,
  uploadAttemptVideo,
} from "./remoteAnalysisApi";

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
  session: DanceSession,
  options?: {
    onRemoteSession?: (sessionID: string) => void;
    onRemoteTask?: (taskID: string) => void;
    onRemoteStatus?: (status: string) => void;
  }
): Promise<AnalysisResult> {
  const apiBaseUrl = getRemoteApiBaseUrl();
  if (apiBaseUrl && session.attemptVideoUri) {
    const remoteSession = await createRemoteSession();
    options?.onRemoteSession?.(remoteSession.session_id);
    await submitCalibration(
      remoteSession.session_id,
      session.calibrationCorners ?? DEFAULT_CALIBRATION_CORNERS
    );
    const upload = await uploadAttemptVideo(remoteSession.session_id, session.attemptVideoUri);
    options?.onRemoteTask?.(upload.task_id);
    const task = await pollRemoteTask(upload.task_id, {
      onStatus: (status) => options?.onRemoteStatus?.(status.status),
    });
    const remoteResults = await getRemoteResults(remoteSession.session_id);
    const phase4 = normalizePhase4Result(remoteResults.metadata);
    if (!phase4) {
      throw new Error("The server returned no usable Phase 4 movement result.");
    }
    return {
      id: `${session.id}-${task.task_id}`,
      sessionID: session.id,
      analyzedAt: Date.now(),
      // Phase 4 returns movement data, not a quality score yet.
      overallScore: 0,
      issues: [],
      participantResults: session.participantIDs.map((participantID) => ({
        participantID,
        score: 0,
        issues: [],
      })),
      phase4,
    };
  }

  await preprocessPhone(session);
  await delay(900);
  return mockAnalyze(session.id, session.participantIDs, session.duration);
}
