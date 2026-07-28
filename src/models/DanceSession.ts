import { randomUUID } from "expo-crypto";
import { CalibrationCorners } from "./Calibration";

export interface DanceSession {
  id: string;
  title: string;
  recordedAt: number; // unix ms
  duration: number;   // seconds
  participantIDs: string[];
  attemptVideoUri?: string;
  referenceVideoUri?: string;
  calibrationCorners?: CalibrationCorners;
  remoteSessionID?: string;
  remoteTaskID?: string;
}

export interface DanceSessionMediaOptions {
  attemptVideoUri?: string;
  referenceVideoUri?: string;
  calibrationCorners?: CalibrationCorners;
}

export function createDanceSession(
  title: string,
  isGroup: boolean,
  duration = 24,
  participantIDs?: string[]
): DanceSession {
  const participants = participantIDs ?? (isGroup
    ? [randomUUID(), randomUUID(), randomUUID()]
    : []);
  return {
    id: randomUUID(),
    title: title.trim() || "Social trend practice",
    recordedAt: Date.now(),
    duration,
    participantIDs: participants,
  };
}
