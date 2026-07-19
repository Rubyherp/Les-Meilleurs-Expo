export enum IssueCategory {
  Timing = "timing",
  Alignment = "alignment",
  Spacing = "spacing",
  Synchronization = "synchronization",
}

export enum IssueSeverity {
  Suggestion = "suggestion",
  Warning = "warning",
  Critical = "critical",
}

export interface DanceIssue {
  id: string;
  category: IssueCategory;
  severity: IssueSeverity;
  message: string;
  timestamp: number; // seconds into video
  participantID?: string;
}
