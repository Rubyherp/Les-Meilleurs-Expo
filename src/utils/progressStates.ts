/**
 * Pure helper to compute progress row states for the analysis processing view.
 *
 * Each row maps to a phase in order:
 *   Row 0: "Preparing videos"     → "preparing"
 *   Row 1: "Comparing movement"   → "uploading"
 *   Row 2: "Writing suggestions"   → "analyzing"
 *
 * @returns Array of { isComplete, isCurrent } for rows 0, 1, 2.
 */
export function getProgressRowStates(phase: string) {
  const phaseOrder = ["preparing", "uploading", "analyzing"] as const;
  const currentIndex = phaseOrder.indexOf(phase as typeof phaseOrder[number]);
  const isFailed = phase === "failed";
  const isCompleted = phase === "completed";

  if (isFailed) {
    return [
      { isComplete: false, isCurrent: false },
      { isComplete: false, isCurrent: false },
      { isComplete: false, isCurrent: false },
    ];
  }

  if (isCompleted) {
    return [
      { isComplete: true, isCurrent: false },
      { isComplete: true, isCurrent: false },
      { isComplete: true, isCurrent: false },
    ];
  }

  // Unknown phase (not in phaseOrder) — all inactive
  if (currentIndex === -1) {
    return [
      { isComplete: false, isCurrent: false },
      { isComplete: false, isCurrent: false },
      { isComplete: false, isCurrent: false },
    ];
  }

  return [
    // Row 0: complete if past preparing
    { isComplete: currentIndex > 0, isCurrent: currentIndex === 0 },
    // Row 1: complete if past uploading
    { isComplete: currentIndex > 1, isCurrent: currentIndex === 1 },
    // Row 2: complete only when all done
    { isComplete: currentIndex > 2, isCurrent: currentIndex === 2 },
  ];
}
