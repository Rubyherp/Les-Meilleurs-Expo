import { randomUUID } from "expo-crypto";
import { CalibrationCorners, CalibrationSource } from "./Calibration";

export type PracticeType = "solo" | "group";

export interface DanceSession {
  id: string;
  title: string;
  recordedAt: number; // unix ms
  duration: number;   // seconds
  practiceType: PracticeType;
  expectedDancerCount: number;
  participantIDs: string[];
  attemptVideoUri?: string;
  referenceVideoUri?: string;
  calibrationCorners?: CalibrationCorners;
  calibrationSource?: CalibrationSource;
  remoteSessionID?: string;
  remoteTaskID?: string;
}

export interface DanceSessionMediaOptions {
  attemptVideoUri?: string;
  referenceVideoUri?: string;
  calibrationCorners?: CalibrationCorners;
  calibrationSource?: CalibrationSource;
}

export function createDanceSession(
  title: string,
  isGroup: boolean,
  duration = 24,
  participantIDs?: string[],
  expectedDancerCount = isGroup ? 2 : 1
): DanceSession {
  const normalizedDancerCount = isGroup
    ? Math.max(2, Math.min(8, Math.round(expectedDancerCount)))
    : 1;
  const participants = participantIDs ?? (isGroup
    ? Array.from({ length: normalizedDancerCount }, () => randomUUID())
    : []);
  return {
    id: randomUUID(),
    title: title.trim() || "Social trend practice",
    recordedAt: Date.now(),
    duration,
    practiceType: isGroup ? "group" : "solo",
    expectedDancerCount: normalizedDancerCount,
    participantIDs: participants,
  };
}
