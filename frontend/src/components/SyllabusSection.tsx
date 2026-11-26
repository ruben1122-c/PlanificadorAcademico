import { useExecutionPolling } from "../hooks/useExecutionPolling";
import { ExecutionStage } from "./ExecutionStage";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  getDocumentActivities,
  listCourseDocuments,
  reviewActivity,
  startDocumentExtraction,
  uploadCourseDocument,
} from "../api/client";
import type {
  ActivityType,
  Course,
  ExecutionStatus,
  ExtractedActivity,
  ExtractionConflict,
  ExtractionExecution,
  ReviewStatus,
  SyllabusDocument,
} from "../types/api";

interface SyllabusSectionProps {
  token: string;
  course: Course | null;
  onGoToCourses: () => void;
  onGoToNewCourse: () => void;
}

const ACTIVITY_TYPE_LABELS: Record<ActivityType, string> = {
  exam: "Examen",
  assignment: "Tarea",
  project: "Proyecto",
  lab: "Laboratorio",
  reading: "Lectura",
  presentation: "Presentación",
  other: "Otro",
};

const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  pending: "Pendiente",
  approved: "Aprobada",
  rejected: "Rechazada",
  edited: "Editada",
};

const EXECUTION_STATUS_LABELS: Record<ExecutionStatus, string> = {
  pending: "En cola",
  running: "Analizando sílabo",
  completed: "Completado",
  failed: "Con error",
};

const SEVERITY_LABELS: Record<ExtractionConflict["severity"], string> = {
  info: "Información",
  warning: "Advertencia",
  error: "Crítico",
};

function toDateTimeLocalValue(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function toIsoWithLocalOffset(localValue: string): string | null {
  const trimmed = localValue.trim();
  if (!trimmed) return null;
  const date = new Date(trimmed);
  if (Number.isNaN(date.getTime())) return null;
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMinutes);
  const pad = (n: number) => String(n).padStart(2, "0");
  const hh = pad(Math.floor(abs / 60));
  const mm = pad(abs % 60);
  return `${trimmed}:00${sign}${hh}:${mm}`;
}

function getReviewBadgeClass(status: ReviewStatus): string {
  if (status === "approved") return "badge badge--success";
  if (status === "rejected") return "badge badge--danger";
  if (status === "edited") return "badge badge--info";
  return "badge badge--neutral";
}

export function SyllabusSection({
  token,
  course,
  onGoToCourses,
  onGoToNewCourse,
}: SyllabusSectionProps) {
  const [documents, setDocuments] = useState<SyllabusDocument[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [docsLoading, setDocsLoading] = useState(false);

  const [executionByCourse, setExecutionByCourse] = useState<
    Record<string, ExtractionExecution>
  >({});
  const [startingExtraction, setStartingExtraction] = useState(false);

  const [activities, setActivities] = useState<ExtractedActivity[]>([]);
  const [conflicts, setConflicts] = useState<ExtractionConflict[]>([]);
  const [activitiesLoading, setActivitiesLoading] = useState(false);

  const [editingActivityId, setEditingActivityId] = useState<string | null>(
    null
  );
  const [editTitle, setEditTitle] = useState("");
  const [editType, setEditType] = useState<ActivityType>("assignment");
  const [editDueDate, setEditDueDate] = useState("");
  const [editWeight, setEditWeight] = useState("");
  const [editEstimatedMinutes, setEditEstimatedMinutes] = useState("");
  const [editDueAt, setEditDueAt] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [reviewDecision, setReviewDecision] = useState<"approved" | "edited">("edited");
  const [savingReviewId, setSavingReviewId] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);

  const courseId = course?.id ?? null;
  const activeCourseRef = useRef<string | null>(courseId);
  activeCourseRef.current = courseId;

  const execution = courseId ? (executionByCourse[courseId] ?? null) : null;

  const activityRequest = useRef(0);
  const loadActivities = useCallback(
    async (docId: string, expectedCourseId: string) => {
      const request = ++activityRequest.current;
      setActivitiesLoading(true);
      setError(null);
      try {
        const data = await getDocumentActivities(token, docId);
        if (request !== activityRequest.current || activeCourseRef.current !== expectedCourseId) return;
        setActivities(data.activities);
        setConflicts(data.conflicts);
      } catch (err) {
        if (request !== activityRequest.current || activeCourseRef.current !== expectedCourseId) return;
        setError(
          err instanceof Error
            ? err.message
            : "Error cargando actividades extraídas"
        );
      } finally {
        if (request === activityRequest.current && activeCourseRef.current === expectedCourseId) {
          setActivitiesLoading(false);
        }
      }
    },
    [token]
  );

  useEffect(() => {
    activityRequest.current += 1;
    setActivitiesLoading(false);
    setDocuments([]);
    setSelectedDocId(null);
    setSelectedFile(null);
    setActivities([]);
    setConflicts([]);
    setEditingActivityId(null);
    setError(null);

    if (!courseId) {
      setDocsLoading(false);
      return;
    }

    let cancelled = false;
    const targetCourseId = courseId;
    setDocsLoading(true);

    void listCourseDocuments(token, targetCourseId)
      .then(async (docs) => {
        if (cancelled || activeCourseRef.current !== targetCourseId) return;
        setDocuments(docs);
        if (docs.length > 0) {
          const firstId = docs[0].id;
          setSelectedDocId(firstId);
          await loadActivities(firstId, targetCourseId);
        }
      })
      .catch((err) => {
        if (cancelled || activeCourseRef.current !== targetCourseId) return;
        setError(
          err instanceof Error
            ? err.message
            : "Error cargando documentos del curso"
        );
      })
      .finally(() => {
        if (!cancelled && activeCourseRef.current === targetCourseId) {
          setDocsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token, courseId, loadActivities]);

  useExecutionPolling(token, execution, async (updated, signal) => {
    if (!courseId) return;
    setError(null);
    if (updated.status === "completed" && updated.document_id === selectedDocId && selectedDocId) {
      await loadActivities(selectedDocId, courseId);
    }
    if (!signal.aborted) {
      setExecutionByCourse((previous) => ({ ...previous, [courseId]: updated }));
    }
  }, setError);

  if (!course || !courseId) {
    return (
      <div className="card">
        <div className="empty-state">
          <p className="empty-state-title">No hay un curso activo</p>
          <p className="empty-state-text">
            Selecciona o crea un curso para subir su sílabo y revisar las
            actividades extraídas.
          </p>
          <div className="btn-row" style={{ justifyContent: "center" }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={onGoToCourses}
            >
              Ir a Mis cursos
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onGoToNewCourse}
            >
              Crear curso
            </button>
          </div>
        </div>
      </div>
    );
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!courseId || docsLoading) return;
    const form = event.currentTarget;
    if (!selectedFile) {
      setError("Selecciona un archivo PDF antes de subir.");
      return;
    }

    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadCourseDocument(token, courseId, selectedFile);
      if (activeCourseRef.current !== courseId) return;
      setDocuments((prev) => [uploaded, ...prev]);
      setSelectedDocId(uploaded.id);
      setSelectedFile(null);
      form.reset();
      setActivities([]);
      setConflicts([]);
      setExecutionByCourse((prev) => {
        const next = { ...prev };
        delete next[courseId];
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error subiendo sílabo");
    } finally {
      setUploading(false);
    }
  }

  async function handleStartExtraction(documentId: string) {
    if (!courseId) return;
    setStartingExtraction(true);
    setError(null);
    try {
      const started = await startDocumentExtraction(token, documentId);
      setExecutionByCourse((prev) => ({
        ...prev,
        [courseId]: started,
      }));
      if (activeCourseRef.current === courseId) setSelectedDocId(documentId);
    } catch (err) {
      if (activeCourseRef.current === courseId) {
        setError(err instanceof Error ? err.message : "Error iniciando extracción");
      }
    } finally {
      setStartingExtraction(false);
    }
  }

  async function handleSelectDocument(documentId: string) {
    if (!courseId) return;
    setSelectedDocId(documentId);
    setEditingActivityId(null);
    await loadActivities(documentId, courseId);
  }

  function startEditing(activity: ExtractedActivity, decision: "approved" | "edited") {
    setEditingActivityId(activity.id);
    setReviewDecision(decision);
    setEditTitle(activity.title);
    setEditType(activity.activity_type);
    setEditDueDate(activity.due_date ?? "");
    setEditWeight(
      activity.weight_percentage !== null
        ? String(activity.weight_percentage)
        : ""
    );
    setEditEstimatedMinutes(
      activity.estimated_minutes !== null
        ? String(activity.estimated_minutes)
        : ""
    );
    const extractedTime = activity.due_time?.match(/^([01]\d|2[0-3]):[0-5]\d/)?.[0];
    setEditDueAt(
      toDateTimeLocalValue(activity.due_at) ||
      (activity.due_date ? `${activity.due_date}T${extractedTime ?? "23:59"}` : ""),
    );
    setEditNotes(activity.review_notes ?? "");
  }

  async function handleQuickReview(
    activityId: string,
    reviewStatus: ReviewStatus
  ) {
    setSavingReviewId(activityId);
    setError(null);
    try {
      const updated = await reviewActivity(token, activityId, {
        review_status: reviewStatus,
      });
      setActivities((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item))
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Error guardando revisión"
      );
    } finally {
      setSavingReviewId(null);
    }
  }

  async function handleSaveEdit(activityId: string) {
    setSavingReviewId(activityId);
    setError(null);

    const parsedWeight =
      editWeight.trim() === "" ? null : Number.parseFloat(editWeight);
    const parsedEstimatedMinutes =
      editEstimatedMinutes.trim() === ""
        ? null
        : Number.parseInt(editEstimatedMinutes, 10);
    const parsedDueAt = toIsoWithLocalOffset(editDueAt);
    if (!parsedDueAt || !parsedEstimatedMinutes || parsedEstimatedMinutes <= 0) {
      setError("Confirma el vencimiento e indica una duración mayor a cero.");
      setSavingReviewId(null);
      return;
    }

    try {
      const updated = await reviewActivity(token, activityId, {
        review_status: reviewDecision,
        title: editTitle,
        activity_type: editType,
        due_date: editDueDate.trim() ? editDueDate.trim() : null,
        clear_due_date: editDueDate.trim() === "",
        weight_percentage:
          parsedWeight !== null && !Number.isNaN(parsedWeight)
            ? parsedWeight
            : null,
        clear_weight: editWeight.trim() === "",
        estimated_minutes:
          parsedEstimatedMinutes !== null && !Number.isNaN(parsedEstimatedMinutes)
            ? parsedEstimatedMinutes
            : null,
        clear_estimated_minutes: editEstimatedMinutes.trim() === "",
        due_at: parsedDueAt,
        clear_due_at: editDueAt.trim() === "",
        review_notes: editNotes.trim() || null,
      });
      setActivities((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item))
      );
      setEditingActivityId(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Error editando la actividad"
      );
    } finally {
      setSavingReviewId(null);
    }
  }

  return (
    <div className="panel-grid">
      <div className="card">
        <div className="card-header">
          <div>
            <span className="badge badge--teal">{course.code}</span>
            <h2 className="card-title" style={{ marginTop: "0.35rem" }}>
              Sílabo y revisión — {course.name}
            </h2>
            <p className="card-subtitle">
              Sube el sílabo en PDF, extrae las actividades y valida su
              evidencia antes de planificar.
            </p>
          </div>
        </div>

        <form className="btn-row" onSubmit={(e) => void handleUpload(e)}>
          <div className="form-field" style={{ flex: "1 1 260px" }}>
            <label className="form-label" htmlFor="syllabus-pdf-upload">
              Archivo de sílabo (PDF)
            </label>
            <input
              key={courseId}
              id="syllabus-pdf-upload"
              className="file-input"
              type="file"
              accept="application/pdf,.pdf"
              onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={docsLoading || uploading || !selectedFile}
            style={{ alignSelf: "flex-end" }}
          >
            {uploading ? "Subiendo PDF..." : "Subir sílabo PDF"}
          </button>
        </form>

        {error && (
          <div className="alert alert--error" role="alert" style={{ marginTop: "1rem" }}>
            {error}
          </div>
        )}

        <hr className="divider" style={{ margin: "1.25rem 0" }} />

        <h3 className="section-title">Documentos del curso</h3>
        {docsLoading && (
          <div className="loading-state" role="status">
            Cargando documentos...
          </div>
        )}

        {!docsLoading && documents.length === 0 && (
          <div className="empty-state">
            <p className="empty-state-title">Sin sílabos cargados</p>
            <p className="empty-state-text" style={{ marginBottom: 0 }}>
              Sube un archivo PDF para comenzar la extracción de actividades.
            </p>
          </div>
        )}

        {!docsLoading && documents.length > 0 && (
          <ul className="item-list">
            {documents.map((doc) => {
              const isSelected = selectedDocId === doc.id;
              return (
                <li
                  key={doc.id}
                  className={`doc-row${isSelected ? " is-selected" : ""}`}
                >
                  <div>
                    <strong>{doc.filename}</strong>{" "}
                    <span className="course-card-meta">
                      ({(doc.file_size / 1024).toFixed(1)} KB)
                    </span>
                  </div>
                  <div className="btn-row">
                    <button
                      type="button"
                      className={`btn btn-sm ${
                        isSelected ? "btn-navy" : "btn-secondary"
                      }`}
                      onClick={() => void handleSelectDocument(doc.id)}
                    >
                      Ver actividades
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      disabled={startingExtraction || execution?.status === "pending" || execution?.status === "running"}
                      onClick={() => void handleStartExtraction(doc.id)}
                    >
                      Extraer con IA
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {execution && (
          <div
            className={`alert ${
              execution.status === "failed"
                ? "alert--error"
                : execution.status === "completed"
                  ? "alert--success"
                  : "alert--info"
            }`}
            role="status"
            style={{ marginTop: "1rem" }}
          >
            <strong>Estado de extracción:</strong>{" "}
            {EXECUTION_STATUS_LABELS[execution.status]}
            <ExecutionStage execution={execution} />
            {execution.total_pages !== null && (
              <span>
                {" "}
                — {execution.processed_pages}/{execution.total_pages} páginas,{" "}
                {execution.activities_count} actividades,{" "}
                {execution.conflicts_count} conflictos
              </span>
            )}
            {execution.error_message && (
              <p style={{ margin: "0.4rem 0 0" }}>{execution.error_message}</p>
            )}
          </div>
        )}
      </div>

      {selectedDocId && (
        <div className="card">
          {activitiesLoading && (
            <div className="loading-state" role="status">
              Cargando actividades y conflictos...
            </div>
          )}

          {!activitiesLoading && conflicts.length > 0 && (
            <div className="alert alert--warning" style={{ marginBottom: "1.25rem" }}>
              <h3 className="section-title" style={{ color: "inherit" }}>
                Conflictos y advertencias ({conflicts.length})
              </h3>
              <ul className="item-list">
                {conflicts.map((conflict) => (
                  <li key={conflict.id}>
                    <span
                      className={`badge ${
                        conflict.severity === "error"
                          ? "badge--danger"
                          : conflict.severity === "warning"
                            ? "badge--warning"
                            : "badge--info"
                      }`}
                    >
                      {SEVERITY_LABELS[conflict.severity]}
                    </span>{" "}
                    {conflict.message}
                    {conflict.source_page !== null &&
                      ` (Pág. ${conflict.source_page})`}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!activitiesLoading && activities.length === 0 && (
            <div className="empty-state">
              <p className="empty-state-title">Sin actividades extraídas</p>
              <p className="empty-state-text" style={{ marginBottom: 0 }}>
                Ejecuta &ldquo;Extraer con IA&rdquo; sobre el documento para
                identificar evaluaciones y tareas.
              </p>
            </div>
          )}

          {!activitiesLoading && activities.length > 0 && (
            <div className="panel-grid">
              <div className="card-header" style={{ marginBottom: 0 }}>
                <h3 className="card-title">
                  Revisión de actividades ({activities.length})
                </h3>
              </div>

              {activities.map((act) => {
                const isEditing = editingActivityId === act.id;
                const isSaving = savingReviewId === act.id;

                return (
                  <article key={act.id} className="activity-card">
                    <div className="activity-header">
                      <div>
                        <h4 className="activity-title">{act.title}</h4>
                        <span className="course-card-meta">
                          {ACTIVITY_TYPE_LABELS[act.activity_type]}
                        </span>
                      </div>

                      <div className="btn-row">
                        <span className={getReviewBadgeClass(act.review_status)}>
                          {REVIEW_STATUS_LABELS[act.review_status]}
                        </span>
                        <span
                          className={`badge ${
                            act.evidence_valid
                              ? "badge--success"
                              : "badge--warning"
                          }`}
                        >
                          {act.evidence_valid
                            ? "Evidencia verificada"
                            : "Evidencia no verificada"}
                        </span>
                      </div>
                    </div>

                    <div className="activity-meta">
                      <span>
                        <strong>Fecha:</strong> {act.due_date ?? "Sin fecha"}
                        {act.due_time ? ` (${act.due_time})` : ""}
                      </span>
                      <span>
                        <strong>Ponderación:</strong>{" "}
                        {act.weight_percentage !== null
                          ? `${act.weight_percentage}%`
                          : "N/A"}
                      </span>
                      <span>
                        <strong>Estimación:</strong>{" "}
                        {act.estimated_minutes !== null
                          ? `${act.estimated_minutes} min`
                          : "Sin estimación"}
                      </span>
                      <span>
                        <strong>Vencimiento:</strong>{" "}
                        {act.due_at
                          ? new Date(act.due_at).toLocaleString("es", {
                              dateStyle: "short",
                              timeStyle: "short",
                            })
                          : "Sin definir"}
                      </span>
                      <span>
                        <strong>Página:</strong> {act.source_page}
                      </span>
                    </div>

                    <blockquote className="evidence-quote">
                      &ldquo;{act.evidence_quote}&rdquo;
                    </blockquote>

                    {act.review_notes && (
                      <div className="course-card-meta">
                        <strong>Notas de revisión:</strong> {act.review_notes}
                      </div>
                    )}

                    {!isEditing && (
                      <div className="btn-row">
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          disabled={isSaving}
                          onClick={() => startEditing(act, "approved")}
                        >
                          Confirmar
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger-outline btn-sm"
                          disabled={isSaving}
                          onClick={() =>
                            void handleQuickReview(act.id, "rejected")
                          }
                        >
                          Excluir
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled={isSaving}
                          onClick={() => startEditing(act, "edited")}
                        >
                          Corregir
                        </button>
                      </div>
                    )}

                    {isEditing && (
                      <div className="edit-box">
                        <div className="form-grid-2">
                          <div className="form-field">
                            <label
                              className="form-label"
                              htmlFor={`edit-title-${act.id}`}
                            >
                              Título
                            </label>
                            <input
                              id={`edit-title-${act.id}`}
                              className="form-input"
                              type="text"
                              value={editTitle}
                              onChange={(e) => setEditTitle(e.target.value)}
                            />
                          </div>

                          <div className="form-field">
                            <label
                              className="form-label"
                              htmlFor={`edit-type-${act.id}`}
                            >
                              Tipo
                            </label>
                            <select
                              id={`edit-type-${act.id}`}
                              className="form-select"
                              value={editType}
                              onChange={(e) =>
                                setEditType(e.target.value as ActivityType)
                              }
                            >
                              {Object.entries(ACTIVITY_TYPE_LABELS).map(
                                ([value, label]) => (
                                  <option key={value} value={value}>
                                    {label}
                                  </option>
                                )
                              )}
                            </select>
                          </div>

                          <div className="form-field">
                            <label
                              className="form-label"
                              htmlFor={`edit-date-${act.id}`}
                            >
                              Fecha límite
                            </label>
                            <input
                              id={`edit-date-${act.id}`}
                              className="form-input"
                              type="date"
                              value={editDueDate}
                              onChange={(e) => setEditDueDate(e.target.value)}
                            />
                          </div>

                          <div className="form-field">
                            <label
                              className="form-label"
                              htmlFor={`edit-weight-${act.id}`}
                            >
                              Ponderación (%)
                            </label>
                            <input
                              id={`edit-weight-${act.id}`}
                              className="form-input"
                              type="number"
                              min={0}
                              max={100}
                              step="0.1"
                              value={editWeight}
                              onChange={(e) => setEditWeight(e.target.value)}
                            />
                          </div>

                          <div className="form-field">
                            <label
                              className="form-label"
                              htmlFor={`edit-minutes-${act.id}`}
                            >
                              Estimación (minutos)
                            </label>
                            <input
                              id={`edit-minutes-${act.id}`}
                              className="form-input"
                              type="number"
                              min={1}
                              max={10080}
                              value={editEstimatedMinutes}
                              onChange={(e) =>
                                setEditEstimatedMinutes(e.target.value)
                              }
                              placeholder="Ej. 120"
                            />
                          </div>

                          <div className="form-field">
                            <label
                              className="form-label"
                              htmlFor={`edit-due-at-${act.id}`}
                            >
                              Vencimiento con zona horaria
                            </label>
                            <input
                              id={`edit-due-at-${act.id}`}
                              className="form-input"
                              type="datetime-local"
                              value={editDueAt}
                              onChange={(e) => setEditDueAt(e.target.value)}
                            />
                          </div>
                        </div>

                        <div className="form-field">
                          <label
                            className="form-label"
                            htmlFor={`edit-notes-${act.id}`}
                          >
                            Notas de revisión
                          </label>
                          <input
                            id={`edit-notes-${act.id}`}
                            className="form-input"
                            type="text"
                            value={editNotes}
                            onChange={(e) => setEditNotes(e.target.value)}
                          />
                        </div>

                        <div className="btn-row">
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            disabled={isSaving}
                            onClick={() => void handleSaveEdit(act.id)}
                          >
                            {isSaving ? "Guardando..." : "Guardar cambios"}
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            disabled={isSaving}
                            onClick={() => setEditingActivityId(null)}
                          >
                            Cancelar
                          </button>
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
