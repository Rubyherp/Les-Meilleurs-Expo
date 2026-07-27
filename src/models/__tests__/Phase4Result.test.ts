/**
 * Tests for Phase 4 result normalization, focusing on aspect-ratio clamping.
 *
 * Run with: npx tsx src/models/__tests__/Phase4Result.test.ts
 */
import { normalizePhase4Result, Phase4ResultJson } from "../Phase4Result";

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
    console.error(
      `  FAIL: ${label} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
    );
    failed++;
  }
}

function assertNear(actual: number, expected: number, tolerance: number, label: string): void {
  if (Math.abs(actual - expected) <= tolerance) {
    passed++;
  } else {
    console.error(
      `  FAIL: ${label} — expected ${expected} ± ${tolerance}, got ${actual}`,
    );
    failed++;
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────

function makeGrid(width: number, height: number, aspectRatio?: number) {
  const grid: Record<string, unknown> = {
    width,
    height,
    columns: 10,
    rows: 10,
    x_labels: [],
    y_labels: [],
    calibrated: false,
  };
  if (aspectRatio !== undefined) grid.aspect_ratio = aspectRatio;
  return grid;
}

function normalize(grid: Record<string, unknown> | null): ReturnType<typeof normalizePhase4Result> {
  return normalizePhase4Result({ grid } as unknown as Phase4ResultJson);
}

// ─── Test 1: Explicit aspect_ratio lower bound (existing behaviour) ─────────
console.log("\n--- Test 1: Explicit aspect_ratio lower bound ---");

{
  const r = normalize(makeGrid(10, 10, 0.1));
  assert(r !== null, "result is non-null");
  if (r) {
    assert(r.grid.aspectRatio >= 0.5, `explicit 0.1 clamped to ${r.grid.aspectRatio}`);
  }
}

{
  const r = normalize(makeGrid(10, 10, 0.5));
  assert(r !== null, "result is non-null");
  if (r) {
    assertNear(r.grid.aspectRatio, 0.5, 0.001, "explicit 0.5 preserved");
  }
}

{
  const r = normalize(makeGrid(10, 10, 4 / 3));
  assert(r !== null, "result is non-null");
  if (r) {
    assertNear(r.grid.aspectRatio, 4 / 3, 0.001, "explicit 1.33 preserved");
  }
}

// ─── Test 2: Fallback width/height should be clamped ───────────────────────
console.log("\n--- Test 2: Fallback width/height clamping ---");

// Extremely wide: width >> height
{
  const r = normalize(makeGrid(1000, 1));
  assert(r !== null, "result is non-null for wide grid");
  if (r) {
    // width/height = 1000 — should be clamped down
    assert(
      r.grid.aspectRatio <= 2.0,
      `wide fallback 1000:1 clamped to ${r.grid.aspectRatio} (expected ≤ 2.0)`,
    );
    assert(
      r.grid.aspectRatio >= 0.5,
      `wide fallback clamped above 0.5, got ${r.grid.aspectRatio}`,
    );
  }
}

// Extremely tall: height >> width
{
  const r = normalize(makeGrid(1, 1000));
  assert(r !== null, "result is non-null for tall grid");
  if (r) {
    // width/height = 0.001 — should be clamped up
    assert(
      r.grid.aspectRatio >= 0.5,
      `tall fallback 1:1000 clamped to ${r.grid.aspectRatio} (expected ≥ 0.5)`,
    );
    assert(
      r.grid.aspectRatio <= 2.0,
      `tall fallback clamped below 2.0, got ${r.grid.aspectRatio}`,
    );
  }
}

// ─── Test 3: Normal proportions pass through ───────────────────────────────
console.log("\n--- Test 3: Normal proportions pass through ---");

{
  const r = normalize(makeGrid(16, 9));
  assert(r !== null, "result is non-null for 16:9");
  if (r) {
    assertNear(r.grid.aspectRatio, 16 / 9, 0.001, "16:9 fallback ≈ 1.778");
  }
}

{
  const r = normalize(makeGrid(4, 3));
  assert(r !== null, "result is non-null for 4:3");
  if (r) {
    assertNear(r.grid.aspectRatio, 4 / 3, 0.001, "4:3 fallback ≈ 1.333");
  }
}

{
  const r = normalize(makeGrid(1, 1));
  assert(r !== null, "result is non-null for 1:1");
  if (r) {
    assertNear(r.grid.aspectRatio, 1.0, 0.001, "1:1 fallback = 1.0");
  }
}

// ─── Test 4: Explicit aspect_ratio also respects upper bound (future-proof) ─
console.log("\n--- Test 4: Explicit aspect_ratio extreme values ---");

{
  const r = normalize(makeGrid(10, 10, 100));
  assert(r !== null, "result is non-null for extreme explicit ratio");
  if (r) {
    // Currently code uses Math.max(0.5, ...) — no upper bound for explicit.
    // This test documents current behaviour; the task focuses on fallback only.
    assert(r.grid.aspectRatio >= 0.5, "extreme explicit ratio has lower bound");
  }
}

// ─── Test 5: Missing / null grid ───────────────────────────────────────────
console.log("\n--- Test 5: Missing / null grid ---");

assert(normalize(null) === null, "null grid returns null");

{
  const r = normalizePhase4Result({} as unknown as Phase4ResultJson);
  assert(r === null, "empty input returns null");
}

// ─── Summary ──────────────────────────────────────────────────────────────
console.log(`\n=== Results: ${passed} passed, ${failed} failed ===`);
if (failed > 0) process.exit(1);
