export interface DanceSession {
  id: string;
  title: string;
  recordedAt: number; // unix ms
  duration: number;   // seconds
  participantIDs: string[];
}

export function createDanceSession(
  title: string,
  isGroup: boolean,
  duration = 24,
  participantIDs?: string[]
): DanceSession {
  const participants = participantIDs ?? (isGroup
    ? [crypto.randomUUID(), crypto.randomUUID(), crypto.randomUUID()]
    : []);
  return {
    id: crypto.randomUUID(),
    title: title.trim() || "Social trend practice",
    recordedAt: Date.now(),
    duration,
    participantIDs: participants,
  };
}
