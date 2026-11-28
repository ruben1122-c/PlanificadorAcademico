export interface HealthResponse {
  status: string;
}

export interface User {
  id: string;
  email: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number | null;
  refresh_token: string | null;
  user: User;
}

export interface Course {
  id: string;
  owner_id: string;
  code: string;
  name: string;
  term: string | null;
  credits: number | null;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface CourseCreatePayload {
  code: string;
  name: string;
  term?: string | null;
  credits?: number | null;
  description?: string | null;
}

export interface SyllabusDocument {
  id: string;
  owner_id: string;
  course_id: string;
  filename: string;
  content_type: string;
  file_size: number;
  storage_bucket: string;
  storage_path: string;
  sha256: string;
  created_at: string;
}

export interface UploadReservation {
  upload_id: string;
  expires_at: string;
}

export interface ActiveSyllabusUpload extends UploadReservation {
  filename: string;
  status: "reserved" | "receiving";
}

export interface CourseSyllabusStatus {
  upload: ActiveSyllabusUpload | null;
  document: SyllabusDocument | null;
  execution: ExtractionExecution | null;
  active_execution: ExtractionExecution | null;
}

export type ExecutionStatus = "pending" | "running" | "completed" | "failed";

export interface ExtractionExecution {
  id: string;
  owner_id: string;
  execution_type?: "extraction" | "planning";
  document_id: string | null;
  course_id: string | null;
  plan_id?: string | null;
  horizon_start?: string | null;
  horizon_end?: string | null;
  status: ExecutionStatus;
  model_name: string | null;
  total_pages: number | null;
  processed_pages: number;
  activities_count: number;
  conflicts_count: number;
  blocks_count?: number | null;
  pending_count?: number | null;
  error_message: string | null;
  stage?: string | null;
  attempt_count?: number;
  stage_timings?: Record<string, number>;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type ReviewStatus = "pending" | "approved" | "rejected" | "edited";

export type ActivityType =
  | "exam"
  | "assignment"
  | "project"
  | "lab"
  | "reading"
  | "presentation"
  | "other";

export interface ExtractedActivity {
  id: string;
  owner_id: string;
  course_id: string;
  document_id: string;
  execution_id: string;
  title: string;
  activity_type: ActivityType;
  due_date: string | null;
  due_time: string | null;
  weight_percentage: number | null;
  description: string | null;
  estimated_minutes: number | null;
  due_at: string | null;
  source_page: number;
  evidence_quote: string;
  evidence_valid: boolean;
  confidence: number | null;
  review_status: ReviewStatus;
  review_notes: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExtractionConflict {
  id: string;
  owner_id: string;
  course_id: string;
  document_id: string;
  execution_id: string;
  activity_id: string | null;
  conflict_type: string;
  severity: "info" | "warning" | "error";
  message: string;
  source_page: number | null;
  details: Record<string, unknown>;
  resolved: boolean;
  created_at: string;
}

export interface DocumentActivitiesResponse {
  document_id: string;
  activities: ExtractedActivity[];
  conflicts: ExtractionConflict[];
}

export interface ActivityReviewPayload {
  review_status: ReviewStatus;
  title?: string;
  activity_type?: ActivityType;
  due_date?: string | null;
  clear_due_date?: boolean;
  due_time?: string | null;
  weight_percentage?: number | null;
  clear_weight?: boolean;
  description?: string | null;
  review_notes?: string | null;
  estimated_minutes?: number | null;
  clear_estimated_minutes?: boolean;
  due_at?: string | null;
  clear_due_at?: boolean;
}

export interface AvailabilityIntervalPayload {
  start_at: string;
  end_at: string;
}

export interface AvailabilityWindow {
  id: string;
  owner_id: string;
  start_at: string;
  end_at: string;
  created_at: string;
  updated_at: string;
}

export interface PlanningRunPayload {
  course_id: string;
  horizon_start: string;
  horizon_end: string;
}

export interface StudyBlock {
  id: string;
  activity_id: string;
  activity_title: string | null;
  start_at: string;
  end_at: string;
  duration_minutes: number;
}

export interface PlanPendingActivity {
  id: string;
  activity_id: string;
  activity_title: string | null;
  reason: string;
}

export interface StudyPlan {
  id: string;
  owner_id: string;
  course_id?: string | null;
  execution_id: string;
  horizon_start: string;
  horizon_end: string;
  model_name: string | null;
  planner_summary: string | null;
  blocks: StudyBlock[];
  pending_activities: PlanPendingActivity[];
  created_at: string;
}
