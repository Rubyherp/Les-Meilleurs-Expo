/**
 * Tests for the hex-with-alpha helper extracted from InlineStatus.
 *
 * Run with: npx tsx src/components/__tests__/InlineStatus.test.ts
 */
import { toHexWithAlpha } from "../../utils/color";

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

// ─── Test 1: 6-digit hex gets alpha suffix ─────────────────────────────────
console.log("\n--- Test 1: 6-digit hex gets alpha suffix ---");

{
  const result = toHexWithAlpha("#17171D", "8C");
  assertEqual(result, "#17171D8C", "#17171D + 8C = #17171D8C");
}

{
  const result = toHexWithAlpha("#FF0000", "80");
  assertEqual(result, "#FF000080", "#FF0000 + 80 = #FF000080");
}

{
  const result = toHexWithAlpha("#00ff00", "33");
  assertEqual(result, "#00ff0033", "lowercase hex preserved");
}

// ─── Test 2: Non-hex strings fall back to tint ─────────────────────────────
console.log("\n--- Test 2: Non-hex / unexpected color strings ---");

{
  // Named color
  const result = toHexWithAlpha("red", "8C");
  assertEqual(result, "red", "named color falls back to itself");
}

{
  // rgb() string
  const result = toHexWithAlpha("rgb(255,0,0)", "8C");
  assertEqual(result, "rgb(255,0,0)", "rgb() falls back to itself");
}

{
  // rgba() string
  const result = toHexWithAlpha("rgba(255,0,0,0.5)", "8C");
  assertEqual(result, "rgba(255,0,0,0.5)", "rgba() falls back to itself");
}

{
  // Short hex (3-digit)
  const result = toHexWithAlpha("#FFF", "8C");
  assertEqual(result, "#FFF", "3-digit hex falls back to itself");
}

{
  // 8-digit hex (already has alpha)
  const result = toHexWithAlpha("#17171D8C", "8C");
  assertEqual(result, "#17171D8C", "8-digit hex falls back to itself");
}

{
  // Empty string
  const result = toHexWithAlpha("", "8C");
  assertEqual(result, "", "empty string falls back to itself");
}

// ─── Test 3: Preserves case of input hex ───────────────────────────────────
console.log("\n--- Test 3: Case preservation ---");

{
  const result = toHexWithAlpha("#aAbBcC", "8C");
  assertEqual(result, "#aAbBcC8C", "mixed case hex preserved");
}

// ─── Test 4: Transparent / special values ──────────────────────────────────
console.log("\n--- Test 4: Special values ---");

{
  const result = toHexWithAlpha("transparent", "8C");
  assertEqual(result, "transparent", "'transparent' falls back to itself");
}

// ─── Summary ──────────────────────────────────────────────────────────────
console.log(`\n=== Results: ${passed} passed, ${failed} failed ===`);
if (failed > 0) process.exit(1);
