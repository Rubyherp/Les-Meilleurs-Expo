/** The two coordinates are always normalized to 0...1. They are not grid cells. */
export interface NormalizedTopDownPosition {
  x: number;
  y: number;
}

export interface Phase4TopDownPosition extends NormalizedTopDownPosition {
  raw_x?: number;
  raw_y?: number;
  row?: number;
  column?: number;
  label?: string;
  source?: Phase4TrackSource;
  status?: Phase4TrackStatus;
}

export type Phase4TrackId = string | number;
export type Phase4TrackStatus = "active" | "occluded" | "lost";
export type Phase4TrackSource = "observed" | "predicted" | "none";
export type Phase4CoordinateOrigin = "top_left" | "bottom_left";

export interface Phase4PoseLandmark {
  index?: number;
  x: number;
  y: number;
  z?: number;
  visibility?: number;
  presence?: number;
  name?: string;
  [key: string]: unknown;
}

export interface Phase4Pose {
  landmarks: Phase4PoseLandmark[];
  worldLandmarks?: Phase4PoseLandmark[];
  world_landmarks?: Phase4PoseLandmark[];
}

export interface Phase4CalibrationMetadata {
  status: "calibrated" | "not_calibrated" | "pending";
  corners?: [NormalizedTopDownPosition, NormalizedTopDownPosition, NormalizedTopDownPosition, NormalizedTopDownPosition];
}

/** Normalized, display-independent grid metadata returned by Phase 4. */
export interface Phase4GridMetadata {
  width: number;
  height: number;
  aspectRatio: number;
  columns: number;
  rows: number;
  xLabels: string[];
  yLabels: string[];
  unit?: string;
  calibrated: boolean;
  calibration?: Phase4CalibrationMetadata;
  coordinateOrigin?: Phase4CoordinateOrigin;
}

export interface Phase4ProjectionMetadata {
  calibration_available: boolean;
  calibration_required: boolean;
  grid_columns: number;
  grid_rows: number;
}

export interface Phase4Track {
  id: Phase4TrackId;
  status: Phase4TrackStatus;
  source: Phase4TrackSource;
  position: NormalizedTopDownPosition | null;
  pose?: Phase4Pose | null;
}

export interface Phase4Frame {
  index: number;
  timestampSeconds: number;
  tracks: Phase4Track[];
}

export interface Phase4Result {
  phase: 4;
  grid: Phase4GridMetadata;
  frames: Phase4Frame[];
  frameRate?: number;
}

/**
 * Wire format for the Phase 4 endpoint. Keeping this separate from the view
 * model means the UI can stay camelCase while accepting the backend's JSON.
 */
export interface Phase4ResultJson {
  phase?: 4;
  video?: {
    width?: number;
    height?: number;
    fps?: number;
  };
  sampling?: {
    target_fps?: number | null;
  };
  projection?: Phase4ProjectionMetadata;
  grid?: {
    width: number;
    height: number;
    aspect_ratio?: number;
    columns?: number;
    rows?: number;
    x_labels?: string[];
    y_labels?: string[];
    unit?: string;
    calibrated?: boolean;
    calibration?: {
      status: "calibrated" | "not_calibrated" | "pending";
      corners?: [NormalizedTopDownPosition, NormalizedTopDownPosition, NormalizedTopDownPosition, NormalizedTopDownPosition];
    };
    coordinate_origin?: Phase4CoordinateOrigin;
  };
  frame_rate?: number;
  frames?: Phase4FrameJson[];
  sampled_frames?: Phase4FrameJson[];
}

export interface Phase4FrameJson {
  frame_index: number;
  timestamp_seconds: number;
  tracks: Phase4TrackJson[];
}

export interface Phase4TrackJson {
  track_id: Phase4TrackId;
  status: Phase4TrackStatus;
  source?: Phase4TrackSource;
  bbox_source?: Phase4TrackSource;
  top_down?: Phase4TopDownPosition | null;
  top_down_position?: Phase4TopDownPosition | null;
  pose?: Phase4Pose | null;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function normalizedPosition(value: unknown): NormalizedTopDownPosition | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as { x?: unknown; y?: unknown };
  if (!isFiniteNumber(candidate.x) || !isFiniteNumber(candidate.y)) return null;
  return {
    x: Math.max(0, Math.min(1, candidate.x)),
    y: Math.max(0, Math.min(1, candidate.y)),
  };
}

/** Convert the JSON contract into the small, predictable model used by views. */
export function normalizePhase4Result(input: Phase4ResultJson): Phase4Result | null {
  if (!input?.grid && !input?.projection) {
    return null;
  }

  const rawWidth = input.grid?.width ?? 1;
  const rawHeight = input.grid?.height ?? 1;
  if (!isFiniteNumber(rawWidth) || !isFiniteNumber(rawHeight)) return null;
  const width = Math.max(0.01, rawWidth);
  const height = Math.max(0.01, rawHeight);
  const frames = input.frames ?? input.sampled_frames ?? [];
  const aspectRatio = isFiniteNumber(input.grid?.aspect_ratio)
    ? Math.max(0.5, input.grid!.aspect_ratio!)
    : input.grid ? width / height : 1;
  const calibration = input.grid?.calibration;
  const projection = input.projection;

  return {
    phase: 4,
    grid: {
      width,
      height,
      aspectRatio,
      columns: Math.max(1, Math.round(input.grid?.columns ?? projection?.grid_columns ?? 10)),
      rows: Math.max(1, Math.round(input.grid?.rows ?? projection?.grid_rows ?? 10)),
      xLabels: input.grid?.x_labels ?? [],
      yLabels: input.grid?.y_labels ?? [],
      unit: input.grid?.unit,
      calibrated: input.grid?.calibrated ?? projection?.calibration_available ?? calibration?.status === "calibrated",
      calibration,
      coordinateOrigin: input.grid?.coordinate_origin ?? "top_left",
    },
    frameRate: isFiniteNumber(input.frame_rate)
      ? input.frame_rate
      : isFiniteNumber(input.sampling?.target_fps)
        ? input.sampling!.target_fps!
        : isFiniteNumber(input.video?.fps)
          ? input.video!.fps!
          : undefined,
    frames: frames.map((frame) => ({
      index: frame.frame_index,
      timestampSeconds: frame.timestamp_seconds,
      tracks: frame.tracks.map((track) => ({
        id: track.track_id,
        status: track.status,
        source: track.source ?? track.bbox_source ?? "none",
        position: normalizedPosition(track.top_down ?? track.top_down_position),
        pose: track.pose,
      })),
    })),
  };
}
