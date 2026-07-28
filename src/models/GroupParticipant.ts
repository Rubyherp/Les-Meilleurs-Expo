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

export function createGroupParticipants(): GroupParticipant[] {
  return [
    { id: randomUUID(), displayName: "You", role: ParticipantRole.Dancer },
    { id: randomUUID(), displayName: "Maya", role: ParticipantRole.Dancer },
    { id: randomUUID(), displayName: "Noah", role: ParticipantRole.Dancer },
  ];
}
