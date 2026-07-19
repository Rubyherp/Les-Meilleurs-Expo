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
    { id: crypto.randomUUID(), displayName: "You", role: ParticipantRole.Dancer },
    { id: crypto.randomUUID(), displayName: "Maya", role: ParticipantRole.Dancer },
    { id: crypto.randomUUID(), displayName: "Noah", role: ParticipantRole.Dancer },
  ];
}
