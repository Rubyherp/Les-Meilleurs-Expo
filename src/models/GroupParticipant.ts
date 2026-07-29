import { randomUUID } from "expo-crypto";

export enum ParticipantRole {
  Dancer = "dancer",
  Instructor = "instructor",
}

export interface GroupParticipant {
  id: string;
  displayName: string;
  role: ParticipantRole;
}

const DEFAULT_NAMES = ["You", "Maya", "Noah", "Ari", "Sam", "Kai", "Jules", "Remy"];

export function createGroupParticipants(count = 2): GroupParticipant[] {
  const normalizedCount = Math.max(2, Math.min(8, Math.round(count)));
  return Array.from({ length: normalizedCount }, (_, index) => ({
    id: randomUUID(),
    displayName: DEFAULT_NAMES[index] ?? `Dancer ${index + 1}`,
    role: ParticipantRole.Dancer,
  }));
}
