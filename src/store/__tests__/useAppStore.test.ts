/**
 * Regression tests for useAppStore error handling in seed operations.
 *
 * seedFromBackend and seedComparisonFromBackend must re-throw errors after
 * recording them, so callers (e.g. app/analysis/[id].tsx) can react to
 * failures instead of silently succeeding.
 *
 * Also verifies error-clearing uses type-safe `delete` instead of the
 * `undefined as unknown as string` hack.
 *
 * Run with: npx tsx src/store/__tests__/useAppStore.test.ts
 *
 * These tests rely on EXPO_PUBLIC_API_URL being unset in the shell, so that
 * getRemoteResults() throws synchronously via requireBaseUrl().
 */
import { useAppStore } from "../useAppStore";

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
      `  FAIL: ${label} — expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
    );
    failed++;
  }
}

async function main() {
  // ─── Test 1: seedFromBackend re-throws on failure ────────────────────────
  console.log("\n--- Test 1: seedFromBackend re-throws errors ---");
  {
    const targetId = "seed-rethrow-test-1";
    const backendId = "backend-fake-1";

    try {
      await useAppStore.getState().seedFromBackend(targetId, backendId);
      // If we reach here, the function resolved — the bug!
      assert(false, "seedFromBackend should have thrown");
    } catch {
      assert(true, "seedFromBackend re-throws the error");
    }

    // analyzingSessionId is still cleared (preserving original cleanup)
    assertEqual(
      useAppStore.getState().analyzingSessionId,
      null,
      "analyzingSessionId is null after seedFromBackend error"
    );

    // error is recorded in state
    const errMsg = useAppStore.getState().errorBySession[targetId];
    assert(
      typeof errMsg === "string" && errMsg.length > 0,
      "errorBySession has error message after seedFromBackend failure"
    );
  }

  // ─── Test 2: seedComparisonFromBackend re-throws on failure ──────────────
  console.log('\n--- Test 2: seedComparisonFromBackend re-throws errors ---');
  {
    const targetId = "seed-compare-rethrow-test-1";
    const backendId = "backend-fake-2";

    try {
      await useAppStore.getState().seedComparisonFromBackend(targetId, backendId);
      // If we reach here, the function resolved — the bug!
      assert(false, "seedComparisonFromBackend should have thrown");
    } catch {
      assert(true, "seedComparisonFromBackend re-throws the error");
    }

    // analyzingSessionId is still cleared (preserving original cleanup)
    assertEqual(
      useAppStore.getState().analyzingSessionId,
      null,
      "analyzingSessionId is null after seedComparisonFromBackend error"
    );

    // error is recorded in state
    const errMsg = useAppStore.getState().errorBySession[targetId];
    assert(
      typeof errMsg === "string" && errMsg.length > 0,
      "errorBySession has error message after seedComparisonFromBackend failure"
    );
  }

  // ─── Test 3: error-clearing does not leave undefined in the record ───────
  console.log("\n--- Test 3: errorBySession uses type-safe deletion ---");
  {
    // Call seedFromBackend with a fresh ID to trigger the error-clearing path.
    // After the operation fails, every value in errorBySession must be a real string.
    const targetId = "seed-typecheck-test-1";
    const backendId = "backend-fake-3";

    try {
      await useAppStore.getState().seedFromBackend(targetId, backendId);
    } catch {
      // expected
    }

    const errorValues = Object.values(useAppStore.getState().errorBySession);
    const allStrings = errorValues.every((v) => typeof v === "string");
    assert(allStrings, "all errorBySession values are strings after seed operation");
  }

  // ─── Summary ─────────────────────────────────────────────────────────────
  console.log(`\n=== Results: ${passed} passed, ${failed} failed ===`);
  if (failed > 0) process.exit(1);
}

main().catch((err) => {
  console.error("Test harness error:", err);
  process.exit(1);
});
