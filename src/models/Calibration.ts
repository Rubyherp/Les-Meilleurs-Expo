import { NormalizedTopDownPosition } from "./Phase4Result";

export type CalibrationCorners = [
  NormalizedTopDownPosition,
  NormalizedTopDownPosition,
  NormalizedTopDownPosition,
  NormalizedTopDownPosition,
];

export type CalibrationSource = "human" | "approximate" | "agent";

export const DEFAULT_CALIBRATION_CORNERS: CalibrationCorners = [
  { x: 0.08, y: 0.1 },
  { x: 0.92, y: 0.1 },
  { x: 0.92, y: 0.9 },
  { x: 0.08, y: 0.9 },
];
