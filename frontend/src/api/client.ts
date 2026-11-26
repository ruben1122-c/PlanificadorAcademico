import type {
  ActivityReviewPayload,
  AvailabilityIntervalPayload,
  AvailabilityWindow,
  Course,
  CourseCreatePayload,
  DocumentActivitiesResponse,
  ExtractedActivity,
  ExtractionExecution,
  HealthResponse,
  LoginResponse,
  PlanningRunPayload,
  StudyPlan,
  SyllabusDocument,
  User,
} from "../types/api";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1"
).replace(/\/+$/, "");

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  token?: string | null;
  body?: unknown;
  signal?: AbortSignal;
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json();
    if (
      typeof data === "object" &&
      data !== null &&
      "detail" in data &&
      typeof (data as { detail: unknown }).detail === "string"
    ) {
      return (data as { detail: string }).detail;
    }
  } catch {
    // Ignore non-JSON error responses and fall back to HTTP status.
  }
  return `HTTP ${response.status}`;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = "GET", token = null, body, signal } = options;
  const headers: Record<string, string> = {};

  const isFormData =
    typeof FormData !== "undefined" && body instanceof FormData;

  if (body !== undefined && !isFormData) {
    headers["Content-Type"] = "application/json";
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    signal,
    body:
      body === undefined
        ? undefined
        : isFormData
          ? (body as FormData)
          : JSON.stringify(body),
  });

  if (!response.ok) {
    const message = await extractErrorMessage(response);
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export function checkHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/health");
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/auth/login", {
    method: "POST",
    body: { email, password },
  });
}

export function getCurrentUser(token: string): Promise<User> {
  return apiRequest<User>("/auth/me", { token });
}

export function listCourses(token: string): Promise<Course[]> {
  return apiRequest<Course[]>("/courses", { token });
}

export function createCourse(
  token: string,
  payload: CourseCreatePayload
): Promise<Course> {
  return apiRequest<Course>("/courses", {
    method: "POST",
    token,
    body: payload,
  });
}

export function getCourseById(token: string, courseId: string): Promise<Course> {
  return apiRequest<Course>(`/courses/${encodeURIComponent(courseId)}`, {
    token,
  });
}

export function uploadCourseDocument(
  token: string,
  courseId: string,
  file: File
): Promise<SyllabusDocument> {
  const formData = new FormData();
  formData.append("course_id", courseId);
  formData.append("file", file);

  return apiRequest<SyllabusDocument>("/documents", {
    method: "POST",
    token,
    body: formData,
  });
}

export function listCourseDocuments(
  token: string,
  courseId: string
): Promise<SyllabusDocument[]> {
  return apiRequest<SyllabusDocument[]>(
    `/documents?course_id=${encodeURIComponent(courseId)}`,
    { token }
  );
}

export function startDocumentExtraction(
  token: string,
  documentId: string
): Promise<ExtractionExecution> {
  return apiRequest<ExtractionExecution>(
    `/documents/${encodeURIComponent(documentId)}/extractions`,
    {
      method: "POST",
      token,
    }
  );
}

export function getExecutionStatus(
  token: string,
  executionId: string,
  signal?: AbortSignal
): Promise<ExtractionExecution> {
  return apiRequest<ExtractionExecution>(
    `/executions/${encodeURIComponent(executionId)}`,
    { token, signal }
  );
}

export function getDocumentActivities(
  token: string,
  documentId: string
): Promise<DocumentActivitiesResponse> {
  return apiRequest<DocumentActivitiesResponse>(
    `/documents/${encodeURIComponent(documentId)}/activities`,
    { token }
  );
}

export function reviewActivity(
  token: string,
  activityId: string,
  payload: ActivityReviewPayload
): Promise<ExtractedActivity> {
  return apiRequest<ExtractedActivity>(
    `/activities/${encodeURIComponent(activityId)}/review`,
    {
      method: "PATCH",
      token,
      body: payload,
    }
  );
}

export function getAvailability(token: string): Promise<AvailabilityWindow[]> {
  return apiRequest<AvailabilityWindow[]>("/availability", { token });
}

export function putAvailability(
  token: string,
  intervals: AvailabilityIntervalPayload[]
): Promise<AvailabilityWindow[]> {
  return apiRequest<AvailabilityWindow[]>("/availability", {
    method: "PUT",
    token,
    body: { intervals },
  });
}

export function startPlanningRun(
  token: string,
  payload: PlanningRunPayload
): Promise<ExtractionExecution> {
  return apiRequest<ExtractionExecution>("/planning-runs", {
    method: "POST",
    token,
    body: payload,
  });
}

export function getStudyPlan(
  token: string,
  planId: string,
  courseId?: string | null
): Promise<StudyPlan> {
  const query = courseId ? `?course_id=${encodeURIComponent(courseId)}` : "";
  return apiRequest<StudyPlan>(`/plans/${encodeURIComponent(planId)}${query}`, {
    token,
  });
}
