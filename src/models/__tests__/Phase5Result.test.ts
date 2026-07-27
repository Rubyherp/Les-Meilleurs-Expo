/**
 * Regression tests for Phase 5 result normalization.
 *
 * These tests verify that normalizePhase5Result correctly handles
 * realistic backend payloads including per-match DTW alignment paths.
 *
 * Run with: npx tsx src/models/__tests__/Phase5Result.test.ts
 */
import { normalizePhase5Result, Phase5ResultJson } from "../Phase5Result";

let passed = 0;
let failed = 0;

function assert(condition: boolean, label: string): void {
  if (condition) {
    passed++;
  } else {
    console.error(`  FAIL: ${label}`);
    failed++;
  }
}

function assertEqual<T>(actual: T, expected: T, label: string): void {
  if (actual === expected) {
    passed++;
  } else {
    console.error(`  FAIL: ${label} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    failed++;
  }
}

function assertNear(actual: number, expected: number, tolerance: number, label: string): void {
  if (Math.abs(actual - expected) <= tolerance) {
    passed++;
  } else {
    console.error(`  FAIL: ${label} — expected ${expected} ± ${tolerance}, got ${actual}`);
    failed++;
  }
}

// ─── Backend-shaped Phase 5 payload ────────────────────────────────────────
// This payload mimics what the real backend returns: no top-level alignment,
// but per-deviation per_frame_aligned_points containing the DTW path.
// The reference and attempt are valid Phase 4 sub-payloads.
const DTW_REF_FRAMES = [0, 1, 2, 2, 3, 4, 5, 6, 7];
const DTW_ATT_FRAMES = [0, 1, 1, 2, 3, 4, 5, 6, 7];

function makePhase4Json(trackIds: (string | number)[]): Record<string, unknown> {
  return {
    grid: {
      width: 8,
      height: 6,
      aspect_ratio: 4 / 3,
      columns: 8,
      rows: 6,
      x_labels: ["0m", "1m", "2m", "3m", "4m", "5m", "6m", "7m"],
      y_labels: ["0m", "1m", "2m", "3m", "4m", "5m"],
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
      coordinate_origin: "top_left",
    },
    frame_rate: 30,
    frames: Array.from({ length: 8 }, (_, fi) => ({
      frame_index: fi,
      timestamp_seconds: fi * 0.5,
      tracks: trackIds.map((tid) => ({
        track_id: tid,
        status: "active",
        source: "observed",
        top_down_position: { x: 0.3 + fi * 0.01, y: 0.5 + fi * 0.005 },
      })),
    })),
  };
}

function makeDeviationPerFrame(): Record<string, unknown>[] {
  return DTW_REF_FRAMES.map((refIdx, i) => ({
    reference_frame_index: refIdx,
    attempt_frame_index: DTW_ATT_FRAMES[i],
    reference_point: { x: 0.3 + refIdx * 0.01, y: 0.5 + refIdx * 0.005 },
    attempt_point: { x: 0.31 + DTW_ATT_FRAMES[i] * 0.01, y: 0.49 + DTW_ATT_FRAMES[i] * 0.005 },
    distance: 0.02 + i * 0.005,
  }));
}

const BACKEND_PAYLOAD: Phase5ResultJson = {
  phase: 5,
  reference: makePhase4Json(["dancer-A"]) as Phase5ResultJson["reference"],
  attempt: makePhase4Json(["dancer-A"]) as Phase5ResultJson["attempt"],
  overall_score: 0.87,
  matches: [
    {
      reference_track_id: "dancer-A",
      attempt_track_id: "dancer-A",
      alignment_path: [[0, 0], [1, 1], [2, 1], [2, 2]],
    },
  ],
  deviations: [
    {
      reference_track_id: "dancer-A",
      attempt_track_id: "dancer-A",
      mean_distance: 0.12,
      max_distance: 0.35,
      per_frame_aligned_points: makeDeviationPerFrame(),
    },
  ],
};

// ─── Test 1: Full normalization ───────────────────────────────────────────
console.log("\n--- Test 1: Full Phase 5 normalization ---");

const result = normalizePhase5Result(BACKEND_PAYLOAD);
assert(result !== null, "normalizePhase5Result returns non-null for valid payload");
if (result) {
  assertEqual(result.phase, 5, "phase is 5");
  assert(result.reference.frames.length > 0, "reference frames exist");
  assert(result.attempt.frames.length > 0, "attempt frames exist");
  assertNear(result.overallScore, 0.87, 0.001, "overallScore ≈ 0.87");
  assertEqual(result.matches.length, 1, "one match");
  assertEqual(result.matches[0]!.referenceTrackId, "dancer-A", "match referenceTrackId");
  assertEqual(result.matches[0]!.attemptTrackId, "dancer-A", "match attemptTrackId");
  assertEqual(
    result.matches[0]!.alignmentPath?.[2]?.attemptFrameIndex,
    1,
    "match alignment_path is preserved"
  );
}

// ─── Test 2: Alignment populated from deviation DTW paths ─────────────────
console.log("\n--- Test 2: Alignment from deviation DTW paths ---");

if (result) {
  // Even without a top-level alignment field, the deviation per_frame data
  // should produce a usable alignment.framePairs
  assert(result.alignment !== undefined, "alignment is derived from deviation data");
  if (result.alignment) {
    assert(result.alignment.framePairs.length > 0, "framePairs is non-empty");
    // Verify the DTW path is preserved (not just linear mapping)
    const pairs = result.alignment.framePairs;
    // Frame 2 reference maps to frame 1 attempt (from DTW)
    const pair2 = pairs.find((p) => p.referenceFrameIndex === 2);
    assert(pair2 !== undefined, "reference frame 2 is mapped");
    if (pair2) {
      assertEqual(pair2.attemptFrameIndex, 1, "reference frame 2 → attempt frame 1 (DTW path preserved)");
    }
    // Frame 3 reference maps to frame 3 attempt (from DTW: ref[4]=3 → att[4]=3)
    const pair3 = pairs.find((p) => p.referenceFrameIndex === 3);
    assert(pair3 !== undefined, "reference frame 3 is mapped");
    if (pair3) {
      assertEqual(pair3.attemptFrameIndex, 3, "reference frame 3 → attempt frame 3 (DTW path preserved)");
    }
    // No duplicate reference frames in the derived alignment
    const refIndices = pairs.map((p) => p.referenceFrameIndex);
    const uniqueRefs = new Set(refIndices);
    assertEqual(uniqueRefs.size, refIndices.length, "no duplicate reference frame indices in alignment");
  }
}

// ─── Test 3: Deviation per-frame data preserved ───────────────────────────
console.log("\n--- Test 3: Deviation per-frame DTW data preserved ---");

if (result) {
  assertEqual(result.deviations.length, 1, "one deviation");
  const dev = result.deviations[0]!;
  assertEqual(dev.referenceTrackId, "dancer-A", "deviation referenceTrackId");
  assertEqual(dev.attemptTrackId, "dancer-A", "deviation attemptTrackId");
  assertNear(dev.meanDistance, 0.12, 0.001, "meanDistance ≈ 0.12");
  assertNear(dev.maxDistance, 0.35, 0.001, "maxDistance ≈ 0.35");
  assertEqual(dev.perFrame.length, DTW_REF_FRAMES.length, "perFrame length matches DTW path");
  // Verify first few aligned points
  if (dev.perFrame.length >= 3) {
    assertEqual(dev.perFrame[0]!.referenceFrameIndex, 0, "point[0] ref frame 0");
    assertEqual(dev.perFrame[0]!.attemptFrameIndex, 0, "point[0] att frame 0");
    assertEqual(dev.perFrame[1]!.referenceFrameIndex, 1, "point[1] ref frame 1");
    assertEqual(dev.perFrame[1]!.attemptFrameIndex, 1, "point[1] att frame 1");
    // The DTW path repeats frame 2 (reference frames: [0,1,2,2,3,...])
    assertEqual(dev.perFrame[2]!.referenceFrameIndex, 2, "point[2] ref frame 2");
    assertEqual(dev.perFrame[2]!.attemptFrameIndex, 1, "point[2] att frame 1 (DTW repeat)");
    assertEqual(dev.perFrame[3]!.referenceFrameIndex, 2, "point[3] ref frame 2 again");
    assertEqual(dev.perFrame[3]!.attemptFrameIndex, 2, "point[3] att frame 2");
  }
}

// ─── Test 4: Top-level alignment takes precedence ─────────────────────────
console.log("\n--- Test 4: Top-level alignment takes precedence ---");

const payloadWithAlignment: Phase5ResultJson = {
  ...BACKEND_PAYLOAD,
  alignment: {
    cost: 0.5,
    frame_pairs: [
      { reference_frame_index: 0, attempt_frame_index: 0 },
      { reference_frame_index: 1, attempt_frame_index: 2 }, // intentionally different from deviation
    ],
  },
};

const resultWithAlignment = normalizePhase5Result(payloadWithAlignment);
if (resultWithAlignment) {
  assert(resultWithAlignment.alignment !== undefined, "alignment is present");
  if (resultWithAlignment.alignment) {
    assertNear(resultWithAlignment.alignment.cost, 0.5, 0.001, "alignment cost from top-level");
    assertEqual(
      resultWithAlignment.alignment.framePairs.length,
      2,
      "alignment framePairs from top-level (not derived from deviations)"
    );
    // The top-level says frame 1 → 2, not the DTW 1 → 1
    const pair1 = resultWithAlignment.alignment.framePairs.find(
      (p) => p.referenceFrameIndex === 1
    );
    if (pair1) {
      assertEqual(pair1.attemptFrameIndex, 2, "top-level alignment frame 1 → 2 (not DTW 1 → 1)");
    }
  }
}

// ─── Test 5: Null / invalid input ─────────────────────────────────────────
console.log("\n--- Test 5: Edge cases ---");

assert(normalizePhase5Result(null as unknown as Phase5ResultJson) === null, "null returns null");
assert(
  normalizePhase5Result({ phase: 4 } as unknown as Phase5ResultJson) === null,
  "phase 4 returns null"
);

// ─── Summary ──────────────────────────────────────────────────────────────
console.log(`\n=== Results: ${passed} passed, ${failed} failed ===`);
if (failed > 0) process.exit(1);
