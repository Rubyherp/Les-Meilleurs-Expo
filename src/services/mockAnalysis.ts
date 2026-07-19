import { AnalysisResult, ParticipantAnalysisResult } from "../models/AnalysisResult";
import { DanceIssue, IssueCategory, IssueSeverity } from "../models/DanceIssue";
import { Phase4Frame, Phase4Result, Phase4Track } from "../models/Phase4Result";

function stableHash(str: string): number {
  let hash = 17;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash * 31 + str.codePointAt(i)!) % 10_000 + 10_000) % 10_000;
  }
  return hash;
}

function deterministicUUID(str: string): string {
  const bytes = new Uint8Array(16);
  const encoder = new TextEncoder();
  const encoded = encoder.encode(str);
  for (let i = 0; i < encoded.length; i++) {
    const slot = i % 16;
    bytes[slot] = (bytes[slot] * 31 + encoded[i]) & 0xff;
    bytes[(slot + 7) % 16] ^= encoded[i];
  }
  const hex = Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function clampNormalized(value: number): number {
  return Math.max(0.08, Math.min(0.92, value));
}

function seededPhase4Result(
  sessionID: string,
  participantIDs: string[],
  duration: number
): Phase4Result {
  const trackIDs = participantIDs.length > 0 ? participantIDs : ["solo-dancer"];
  const safeDuration = Math.max(0, duration);
  const sampleCount = 9;
  const gridColumns = 8;
  const gridRows = 6;

  const frames: Phase4Frame[] = Array.from({ length: sampleCount }, (_, frameIndex) => {
    const progress = frameIndex / (sampleCount - 1);
    const timestampSeconds = Number((safeDuration * progress).toFixed(3));
    const tracks: Phase4Track[] = trackIDs.map((trackID, trackIndex) => {
      const trackSeed = stableHash(`${sessionID}-phase4-${trackID}`);
      const phaseOffset = (trackSeed % 360) * (Math.PI / 180);
      const formationColumns = Math.ceil(Math.sqrt(trackIDs.length));
      const formationRows = Math.ceil(trackIDs.length / formationColumns);
      const column = trackIndex % formationColumns;
      const row = Math.floor(trackIndex / formationColumns);
      const anchorX = trackIDs.length === 1
        ? 0.5
        : 0.26 + (column / Math.max(1, formationColumns - 1)) * 0.48;
      const anchorY = trackIDs.length === 1
        ? 0.52
        : 0.38 + (row / Math.max(1, formationRows - 1)) * 0.24;
      const seededDrift = ((trackSeed % 17) - 8) / 1000;

      return {
        id: trackID,
        status: "active",
        source: "observed",
        position: {
          x: clampNormalized(
            anchorX +
              Math.sin(progress * Math.PI * 2 + phaseOffset) * 0.065 +
              Math.sin(progress * Math.PI * 4 + phaseOffset / 2) * 0.018 +
              seededDrift
          ),
          y: clampNormalized(
            anchorY +
              Math.cos(progress * Math.PI * 2 + phaseOffset) * 0.055 +
              Math.sin(progress * Math.PI * 3 + phaseOffset) * 0.014
          ),
        },
      };
    });

    return { index: frameIndex, timestampSeconds, tracks };
  });

  return {
    phase: 4,
    grid: {
      width: 8,
      height: 6,
      aspectRatio: 4 / 3,
      columns: gridColumns,
      rows: gridRows,
      xLabels: ["0m", "1m", "2m", "3m", "4m", "5m", "6m", "7m"],
      yLabels: ["0m", "1m", "2m", "3m", "4m", "5m"],
      unit: "metres",
      calibrated: true,
      calibration: {
        status: "calibrated",
        corners: [
          { x: 0.08, y: 0.08 },
          { x: 0.92, y: 0.08 },
          { x: 0.92, y: 0.92 },
          { x: 0.08, y: 0.92 },
        ],
      },
      coordinateOrigin: "top_left",
    },
    frames,
    frameRate: 4,
  };
}

export async function mockAnalyze(
  sessionID: string,
  participantIDs: string[],
  duration: number
): Promise<AnalysisResult> {
  const seed = stableHash(sessionID);
  const score = 0.72 + (seed % 21) / 100.0;

  const timingIssue: DanceIssue = {
    id: deterministicUUID(`${sessionID}-timing`),
    category: IssueCategory.Timing,
    severity: IssueSeverity.Suggestion,
    message: "A few transitions could land more consistently on the beat.",
    timestamp: Math.min(duration, 12),
  };

  const spacingIssue: DanceIssue = {
    id: deterministicUUID(`${sessionID}-spacing`),
    category: IssueCategory.Spacing,
    severity: IssueSeverity.Warning,
    message: "The group spacing changes during the middle section.",
    timestamp: Math.min(duration, 28),
  };

  const participantResults: ParticipantAnalysisResult[] = participantIDs.map(
    (pid, index) => {
      const pSeed = stableHash(pid);
      const pScore = Math.max(
        0,
        Math.min(1, score - 0.04 + ((pSeed + index) % 9) / 100.0)
      );
      return {
        participantID: pid,
        score: pScore,
        issues: index % 2 === 0 ? [timingIssue] : [],
      };
    }
  );

  return {
    id: deterministicUUID(`${sessionID}-result`),
    sessionID,
    analyzedAt: Date.now(),
    overallScore: score,
    issues: [timingIssue, spacingIssue],
    participantResults,
    phase4: seededPhase4Result(sessionID, participantIDs, duration),
  };
}
