export type EvidenceCategory = "observation" | "timing" | "formation" | "comparison" | "tracking";

export interface VisualReviewJson {
  provider: "agnes";
  summary: string;
  visible_differences?: string[];
  limitations?: string[];
  confidence: number;
  model?: string | null;
}

export interface EvidenceMomentJson {
  id: string;
  start_seconds: number;
  end_seconds: number;
  primary_timestamp_seconds: number;
  category: EvidenceCategory;
  severity: "low" | "medium" | "high";
  deterministic_reason: string;
  deterministic_metrics?: Record<string, unknown>;
  visual_review?: VisualReviewJson | null;
}

export interface EvidenceMoment {
  id: string;
  startSeconds: number;
  endSeconds: number;
  primaryTimestampSeconds: number;
  category: EvidenceCategory;
  severity: "low" | "medium" | "high";
  deterministicReason: string;
  visualReview: VisualReviewJson | null;
}

export function normalizeEvidenceMoment(value: EvidenceMomentJson): EvidenceMoment | null {
  const timestamp = Number(value.primary_timestamp_seconds);
  if (!Number.isFinite(timestamp) || timestamp < 0) return null;
  if (value.visual_review && (!Number.isFinite(value.visual_review.confidence) || value.visual_review.confidence < 0 || value.visual_review.confidence > 1)) return null;
  return {
    id: value.id,
    startSeconds: Number.isFinite(value.start_seconds) ? value.start_seconds : timestamp,
    endSeconds: Number.isFinite(value.end_seconds) ? value.end_seconds : timestamp,
    primaryTimestampSeconds: timestamp,
    category: value.category,
    severity: value.severity,
    deterministicReason: value.deterministic_reason,
    visualReview: value.visual_review ?? null,
  };
}
