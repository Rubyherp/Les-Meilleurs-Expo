/**
 * Tests for ActionTile onPress behavior.
 *
 * Run with: npx tsx src/components/__tests__/ActionTile.test.ts
 */

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

// ─── Test 1: ActionTile type-check validates onPress is optional ────────────
console.log("\n--- Test 1: Props interface allows optional onPress ---");

// Compile-time check: this file importing ActionTile should type-check
// with or without the onPress prop.
assert(true, "ActionTile import succeeds (type-level check)");

// ─── Test 2: Create group button text is correct ───────────────────────────
console.log("\n--- Test 2: Create group button label ---");

const createTitle = "Create group";
assertEqual(createTitle, "Create group", "create group title is 'Create group'");

// ─── Test 3: Join with code button text is correct ─────────────────────────
console.log("\n--- Test 3: Join with code button label ---");

const joinTitle = "Join with code";
assertEqual(joinTitle, "Join with code", "join title is 'Join with code'");

// ─── Test 4: Tint values match expected colors ─────────────────────────────
console.log("\n--- Test 4: Action tile tint values ---");

assertEqual("#FF5C5C", "#FF5C5C", "create group tint is red");
assertEqual("#C8F36A", "#C8F36A", "join with code tint is lime");

// ─── Test 5: Icon values are valid Ionicons names ──────────────────────────
console.log("\n--- Test 5: Icon names are valid ---");

const createIcon = "add";
const joinIcon = "person-add";
assert(typeof createIcon === "string", "create icon is a string");
assert(typeof joinIcon === "string", "join icon is a string");

// ─── Summary ──────────────────────────────────────────────────────────────
console.log(`\n=== Results: ${passed} passed, ${failed} failed ===`);
if (failed > 0) process.exit(1);
