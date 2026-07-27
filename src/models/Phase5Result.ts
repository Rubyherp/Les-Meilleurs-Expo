import {
  NormalizedTopDownPosition,
  Phase4Frame,
  Phase4GridMetadata,
  Phase4Result,
  Phase4ResultJson,
  Phase4TrackId,
} from "./Phase4Result";
import { normalizePhase4Result } from "./Phase4Result";

export interface Phase5AlignmentFramePair {
  referenceFrameIndex: number;
  attemptFrameIndex: number;
}

export interface Phase5Alignment {
  cost: number;
  framePairs: Phase5AlignmentFramePair[];
}

export interface Phase5Match {
  referenceTrackId: Phase4TrackId;
  attemptTrackId: Phase4TrackId;
  alignmentPath?: Phase5AlignmentFramePair[];
}

export interface Phase5AlignedPoint {
  referenceFrameIndex: number;
  attemptFrameIndex: number;
  referencePoint: NormalizedTopDownPosition | null;
  attemptPoint: NormalizedTopDownPosition | null;
  distance: number;
}

export interface Phase5Deviation {
  referenceTrackId: Phase4TrackId;
  attemptTrackId: Phase4TrackId;
  meanDistance: number;
  maxDistance: number;
  perFrame: Phase5AlignedPoint[];
}

export interface Phase5Result {
  phase: 5;
  reference: Phase4Result;
  attempt: Phase4Result;
  alignment?: Phase5Alignment;
  matches: Phase5Match[];
  deviations: Phase5Deviation[];
  overallScore: number;
}

export interface Phase5AlignmentJson {
  cost?: number;
  frame_pairs?: Phase5AlignmentFramePairJson[];
}

export interface Phase5AlignmentFramePairJson {
  reference_frame_index?: number;
  attempt_frame_index?: number;
  reference_index?: number;
  attempt_index?: number;
}

export interface Phase5MatchJson {
  reference_track_id: Phase4TrackId;
  attempt_track_id: Phase4TrackId;
  alignment_path?: [number, number][];
}

export interface Phase5AlignedPointJson {
  reference_frame_index?: number;
  attempt_frame_index?: number;
  reference?: NormalizedTopDownPosition | null;
  attempt?: NormalizedTopDownPosition | null;
  reference_point?: NormalizedTopDownPosition | null;
  attempt_point?: NormalizedTopDownPosition | null;
  distance?: number;
}

export interface Phase5DeviationJson {
  reference_track_id: Phase4TrackId;
  attempt_track_id: Phase4TrackId;
  mean_distance: number;
  max_distance: number;
  per_frame?: Phase5AlignedPointJson[];
  per_frame_aligned_points?: Phase5AlignedPointJson[];
}

export interface Phase5ResultJson {
  phase: 5;
  reference: Phase4ResultJson;
  attempt: Phase4ResultJson;
  alignment?: Phase5AlignmentJson;
  matches?: Phase5MatchJson[];
  deviations?: Phase5DeviationJson[];
  overall_score: number;
}

function finite(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function position(value: unknown): NormalizedTopDownPosition | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as { x?: unknown; y?: unknown };
  if (typeof candidate.x !== "number" || typeof candidate.y !== "number") return null;
  return {
    x: Math.max(0, Math.min(1, candidate.x)),
    y: Math.max(0, Math.min(1, candidate.y)),
  };
}

function trackId(value: unknown): Phase4TrackId | null {
  return typeof value === "string" || typeof value === "number" ? value : null;
}

function normalizeFramePair(pair: Phase5AlignmentFramePairJson): Phase5AlignmentFramePair | null {
  const referenceFrameIndex = finite(pair.reference_frame_index ?? pair.reference_index, NaN);
  const attemptFrameIndex = finite(pair.attempt_frame_index ?? pair.attempt_index, NaN);
  if (!Number.isFinite(referenceFrameIndex) || !Number.isFinite(attemptFrameIndex)) return null;
  return { referenceFrameIndex, attemptFrameIndex };
}

function normalizeAlignmentPath(path: unknown): Phase5AlignmentFramePair[] {
  if (!Array.isArray(path)) return [];
  return path
    .map((pair) => {
      if (!Array.isArray(pair) || pair.length < 2) return null;
      const referenceFrameIndex = finite(pair[0], NaN);
      const attemptFrameIndex = finite(pair[1], NaN);
      return Number.isFinite(referenceFrameIndex) && Number.isFinite(attemptFrameIndex)
        ? { referenceFrameIndex, attemptFrameIndex }
        : null;
    })
    .filter((pair): pair is Phase5AlignmentFramePair => pair !== null);
}

function normalizePhase4Side(input: Phase4ResultJson): Phase4Result | null {
  return normalizePhase4Result(input);
}

/**
 * Build a top-level alignment from per-deviation per_frame data.
 * Each unique reference frame is paired with its first encountered
 * attempt frame, preserving the backend DTW path.
 */
function deriveAlignmentFromDeviations(
  deviations: Phase5Deviation[]
): Phase5Alignment | undefined {
  const seen = new Set<number>();
  const framePairs: Phase5AlignmentFramePair[] = [];
  let totalCost = 0;
  let pairCount = 0;
  for (const dev of deviations) {
    for (const point of dev.perFrame) {
      if (!seen.has(point.referenceFrameIndex)) {
        seen.add(point.referenceFrameIndex);
        framePairs.push({
          referenceFrameIndex: point.referenceFrameIndex,
          attemptFrameIndex: point.attemptFrameIndex,
        });
        totalCost += point.distance;
        pairCount++;
      }
    }
  }
  if (framePairs.length === 0) return undefined;
  return {
    cost: pairCount > 0 ? totalCost / pairCount : 0,
    framePairs,
  };
}

function deriveAlignmentFromMatches(matches: Phase5Match[]): Phase5Alignment | undefined {
  const framePairs = matches.find((match) => match.alignmentPath?.length)?.alignmentPath;
  if (!framePairs?.length) return undefined;
  return { cost: 0, framePairs };
}

/** Convert the snake_case comparison payload into a stable view model. */
export function normalizePhase5Result(input: Phase5ResultJson): Phase5Result | null {
  if (!input || input.phase !== 5) return null;
  const reference = normalizePhase4Side(input.reference);
  const attempt = normalizePhase4Side(input.attempt);
  if (!reference || !attempt) return null;

  const matches = (Array.isArray(input.matches) ? input.matches : [])
    .map((match) => {
      const referenceTrackId = trackId(match.reference_track_id);
      const attemptTrackId = trackId(match.attempt_track_id);
      return referenceTrackId === null || attemptTrackId === null
        ? null
        : {
            referenceTrackId,
            attemptTrackId,
            alignmentPath: normalizeAlignmentPath(match.alignment_path),
          };
    })
    .filter((match): match is NonNullable<typeof match> => match !== null);

  const deviations = (Array.isArray(input.deviations) ? input.deviations : [])
    .map((deviation) => {
      const referenceTrackId = trackId(deviation.reference_track_id);
      const attemptTrackId = trackId(deviation.attempt_track_id);
      if (referenceTrackId === null || attemptTrackId === null) return null;
      const points = deviation.per_frame ?? deviation.per_frame_aligned_points ?? [];
      return {
        referenceTrackId,
        attemptTrackId,
        meanDistance: Math.max(0, finite(deviation.mean_distance)),
        maxDistance: Math.max(0, finite(deviation.max_distance)),
        perFrame: points.map((point) => ({
          referenceFrameIndex: finite(point.reference_frame_index),
          attemptFrameIndex: finite(point.attempt_frame_index),
          referencePoint: position(point.reference ?? point.reference_point),
          attemptPoint: position(point.attempt ?? point.attempt_point),
          distance: Math.max(0, finite(point.distance)),
        })),
      };
    })
    .filter((deviation): deviation is Phase5Deviation => deviation !== null);

  // Top-level alignment from backend payload; else derive from
  // per-deviation per_frame data (the per-match DTW path).
  const alignment = input.alignment &&
    (input.alignment.frame_pairs ?? []).length > 0
    ? {
        cost: Math.max(0, finite(input.alignment.cost)),
        framePairs: (input.alignment.frame_pairs ?? [])
          .map(normalizeFramePair)
          .filter((pair): pair is Phase5AlignmentFramePair => pair !== null),
      }
    : deviations.length > 0
      ? deriveAlignmentFromDeviations(deviations)
      : undefined;

  return {
    phase: 5,
    reference,
    attempt,
    alignment,
    matches,
    deviations,
    overallScore: Math.max(0, Math.min(1, finite(input.overall_score))),
  };
}

// These imports make the model's relationship to the Phase 4 contract obvious
// to consumers without requiring them to import both model modules.
export type { Phase4Frame, Phase4GridMetadata };
