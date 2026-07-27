import assert from "node:assert/strict";
import { getProgressRowStates } from "./src/utils/progressStates";

function test(
  phase: string,
  expectedRow0: ReturnType<typeof getProgressRowStates>[number],
  expectedRow1: ReturnType<typeof getProgressRowStates>[number],
  expectedRow2: ReturnType<typeof getProgressRowStates>[number]
) {
  const [row0, row1, row2] = getProgressRowStates(phase);
  assert.deepEqual(row0, expectedRow0, `Row 0 mismatch for phase "${phase}"`);
  assert.deepEqual(row1, expectedRow1, `Row 1 mismatch for phase "${phase}"`);
  assert.deepEqual(row2, expectedRow2, `Row 2 mismatch for phase "${phase}"`);
}

test(
  "preparing",
  { isComplete: false, isCurrent: true },
  { isComplete: false, isCurrent: false },
  { isComplete: false, isCurrent: false }
);
test(
  "uploading",
  { isComplete: true, isCurrent: false },
  { isComplete: false, isCurrent: true },
  { isComplete: false, isCurrent: false }
);
test(
  "analyzing",
  { isComplete: true, isCurrent: false },
  { isComplete: true, isCurrent: false },
  { isComplete: false, isCurrent: true }
);
test(
  "completed",
  { isComplete: true, isCurrent: false },
  { isComplete: true, isCurrent: false },
  { isComplete: true, isCurrent: false }
);
test(
  "failed",
  { isComplete: false, isCurrent: false },
  { isComplete: false, isCurrent: false },
  { isComplete: false, isCurrent: false }
);

console.log("Progress row state tests passed.");
