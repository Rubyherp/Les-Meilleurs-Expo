export interface ZoExportRequest {
  visibility: "private" | "unlisted";
  schedule_reminder?: boolean;
  reminder_at?: string;
  timezone?: string;
}

export interface ZoExportResponse {
  session_id: string;
  status: "pending" | "completed" | "failed" | "not_configured";
  export_id?: string | null;
  url?: string | null;
  message: string;
  reminder_id?: string | null;
}
