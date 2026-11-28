import { useSyllabusStatus } from "../hooks/useSyllabusStatus";
import { ExecutionStage } from "./ExecutionStage";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  getDocumentActivities,
  listCourseDocuments,
  reserveSyllabusUpload,
  reviewActivity,
  startDocumentExtraction,
  uploadCourseDocument,
} from "../api/client";
import type {
  ActivityType,
  ActiveSyllabusUpload,
  Course,
  ExecutionStatus,
  ExtractedActivity,
  ExtractionConflict,
  ReviewStatus,
  SyllabusDocument,
  UploadReservation,
} from "../types/api";

interface SyllabusSectionProps {
  token: string;
  userId: string;
  course: Course | null;
  visible: boolean;
  documentId: string | null;
  onDocumentChange: (courseId: string, documentId: string | null) => void;
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

function saveUploadAttempt(key: string, attempt: UploadReservation | null) {
  try {
    if (attempt) sessionStorage.setItem(key, JSON.stringify(attempt));
    else sessionStorage.removeItem(key);
  } catch {
    // The server can recover the current operation if storage is disabled.
  }
}

function readUploadAttempt(key: string): UploadReservation | null {
  try {
    const saved = sessionStorage.getItem(key);
    if (!saved) return null;
    const attempt: Partial<UploadReservation> | null = JSON.parse(saved);
    if (typeof attempt?.upload_id === "string"
      && typeof attempt.expires_at === "string"
      && Number.isFinite(Date.parse(attempt.expires_at))) {
      return { upload_id: attempt.upload_id, expires_at: attempt.expires_at };
    }
  } catch {
    return null;
  }
  return null;
}

export function SyllabusSection({
  token,
  userId,
  course,
  visible,
  documentId,
  onDocumentChange,
  onGoToCourses,
  onGoToNewCourse,
}: SyllabusSectionProps) {
  const [documents, setDocuments] = useState<SyllabusDocument[]>([]);
  const [documentsLoaded, setDocumentsLoaded] = useState(false);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [startingExtraction, setStartingExtraction] = useState(false);

  const [activities, setActivities] = useState<ExtractedActivity[]>([]);
  const [conflicts, setConflicts] = useState<ExtractionConflict[]>([]);
  const [activityDocumentId, setActivityDocumentId] = useState<string | null>(null);
  const [activitiesError, setActivitiesError] = useState<string | null>(null);

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
  const [notice, setNotice] = useState<string | null>(null);

  const courseId = course?.id ?? null;
  const uploadAttemptKey = `planificador_upload:${userId}:${courseId}`;
  const mounted = useRef(false);
  const previousUpload = useRef<ActiveSyllabusUpload | null>(null);
  const uploadAttempt = useRef<UploadReservation | null>(null);
  const authorizedDocumentId = documents.some((item) => item.id === documentId)
    ? documentId
    : null;
  const { snapshot, statusError, refreshStatus } = useSyllabusStatus(
    token, courseId, authorizedDocumentId, visible,
  );
  const status = snapshot?.status;
  const selectedDocId = authorizedDocumentId ?? (
    documentId && !documentsLoaded ? null : status?.document?.id ?? documents[0]?.id ?? null
  );
  const selectedExecution = status?.execution?.document_id === selectedDocId
    ? status.execution
    : null;
  const completedExecutionId = selectedExecution?.status === "completed"
    ? selectedExecution.id
    : null;
  const execution = status?.active_execution ?? selectedExecution;
  const courseBusy = Boolean(status?.upload || status?.active_execution);
  const canStartOperation = Boolean(status)
    && !statusError && !courseBusy && !uploading && !startingExtraction;
  const activitiesLoading = selectedDocId !== activityDocumentId && !activitiesError;

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    uploadAttempt.current = readUploadAttempt(uploadAttemptKey);
  }, [uploadAttemptKey]);

  useEffect(() => {
    if (!courseId || !visible || documentsLoaded) return;
    const controller = new AbortController();
    const { signal } = controller;
    setDocumentsError(null);

    void listCourseDocuments(token, courseId, signal)
      .then((list) => {
        if (signal.aborted) return;
        setDocuments((current) => [
          ...current.filter((document) => !list.some((item) => item.id === document.id)),
          ...list,
        ]);
        setDocumentsLoaded(true);
      })
      .catch((err) => {
        if (!signal.aborted) {
          setDocumentsError(err instanceof Error ? err.message : "No se pudieron cargar los documentos.");
        }
      });
    return () => controller.abort();
  }, [token, courseId, visible, documentsLoaded]);

  useEffect(() => {
    const latest = snapshot?.latestDocument;
    if (latest) {
      setDocuments((current) => current.some((item) => item.id === latest.id)
        ? current
        : [latest, ...current]);
    }
    if (!snapshot) return;
    const previous = previousUpload.current;
    previousUpload.current = snapshot.status.upload;
    if (snapshot.status.upload || uploading) return;
    const attempt = uploadAttempt.current;
    if (attempt && courseId && latest?.id === attempt.upload_id) {
      uploadAttempt.current = null;
      saveUploadAttempt(uploadAttemptKey, null);
      if (!documentId) onDocumentChange(courseId, latest.id);
      setError(null);
      setNotice("PDF guardado. Puedes iniciar la extracción desde la lista de documentos.");
      return;
    }
    const expiry = attempt?.expires_at ?? previous?.expires_at;
    if (expiry && Date.parse(expiry) <= Date.now()) {
      uploadAttempt.current = null;
      saveUploadAttempt(uploadAttemptKey, null);
      setError(null);
      setNotice("La reserva venció. Si el PDF no aparece en la lista, vuelve a seleccionarlo.");
    }
  }, [snapshot, courseId, uploadAttemptKey, uploading, documentId, onDocumentChange]);

  useEffect(() => {
    if (courseId && documentsLoaded && documentId && !authorizedDocumentId) {
      onDocumentChange(courseId, null);
    }
  }, [courseId, documentsLoaded, documentId, authorizedDocumentId, onDocumentChange]);

  useEffect(() => {
    setEditingActivityId(null);
    setActivitiesError(null);
    setActivityDocumentId(null);
    if (!selectedDocId || !visible) return;
    const controller = new AbortController();
    const { signal } = controller;
    void getDocumentActivities(token, selectedDocId, signal)
      .then((result) => {
        if (signal.aborted) return;
        setActivities(result.activities);
        setConflicts(result.conflicts);
        setActivityDocumentId(selectedDocId);
      })
      .catch((err) => {
        if (!signal.aborted) {
          setActivitiesError(err instanceof Error ? err.message : "No se pudieron cargar las actividades.");
        }
      });
    return () => controller.abort();
  }, [selectedDocId, completedExecutionId, token, visible]);

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
    if (!courseId || !canStartOperation) return;
    const form = event.currentTarget;
    if (!selectedFile) {
      setError("Selecciona un archivo PDF antes de subir.");
      return;
    }

    setUploading(true);
    setError(null);
    setNotice(null);
    try {
      const reservation = await reserveSyllabusUpload(token, courseId, selectedFile.name);
      uploadAttempt.current = reservation;
      saveUploadAttempt(uploadAttemptKey, reservation);
      if (mounted.current) onDocumentChange(courseId, null);
      const uploaded = await uploadCourseDocument(token, courseId, selectedFile, reservation.upload_id);
      uploadAttempt.current = null;
      saveUploadAttempt(uploadAttemptKey, null);
      if (!mounted.current) return;
      setDocuments((current) => [uploaded, ...current.filter((item) => item.id !== uploaded.id)]);
      onDocumentChange(courseId, uploaded.id);
      setSelectedFile(null);
      form.reset();
      setNotice("PDF guardado. Puedes iniciar la extracción desde la lista de documentos.");
    } catch (err) {
      if (!mounted.current) return;
      if (err instanceof ApiError && err.status === 409) {
        setNotice("La carga no pudo continuar. Revisa el estado del curso antes de reintentar.");
      } else {
        if (err instanceof ApiError && [413, 415, 422].includes(err.status)) {
          uploadAttempt.current = null;
          saveUploadAttempt(uploadAttemptKey, null);
          onDocumentChange(courseId, authorizedDocumentId);
        }
        setError(err instanceof Error ? err.message : "No se pudo subir el sílabo.");
      }
    } finally {
      if (mounted.current) {
        refreshStatus();
        setUploading(false);
      }
    }
  }

  async function handleStartExtraction(documentId: string) {
    if (!courseId || !canStartOperation) return;
    onDocumentChange(courseId, documentId);
    setStartingExtraction(true);
    setError(null);
    setNotice(null);
    try {
      await startDocumentExtraction(token, documentId);
    } catch (err) {
      if (!mounted.current) return;
      if (err instanceof ApiError && err.status === 409) {
        setNotice("Ya hay una carga o un análisis en curso. Se actualizó el seguimiento del curso.");
      } else {
        setError(err instanceof Error ? err.message : "No se pudo iniciar la extracción.");
      }
    } finally {
      if (mounted.current) {
        refreshStatus();
        setStartingExtraction(false);
      }
    }
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
              disabled={!canStartOperation}
              onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!canStartOperation || !selectedFile}
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

        {notice && (
          <div className="alert alert--info" role="status" style={{ marginTop: "1rem" }}>
            {notice}
          </div>
        )}
        {!status && !statusError && !uploading && !startingExtraction && (
          <p className="loading-state" role="status">Consultando estado del curso...</p>
        )}
        {statusError && (
          <div className="alert alert--error" role="alert" style={{ marginTop: "1rem" }}>
            No se pudo verificar el estado del curso. {statusError}{" "}
            <button type="button" className="btn btn-secondary btn-sm" onClick={refreshStatus}>
              Actualizar estado
            </button>
          </div>
        )}
        {status?.upload && (
          <div className="alert alert--info" role="status" style={{ marginTop: "1rem" }}>
            <strong>{status.upload.status === "receiving" ? "Recibiendo PDF" : "Carga pendiente"}:</strong>{" "}
            {status.upload.filename}. Si la carga se interrumpió, podrás volver a seleccionar el archivo
            después de las {new Date(status.upload.expires_at).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}.
          </div>
        )}

        <hr className="divider" style={{ margin: "1.25rem 0" }} />

        <h3 className="section-title">Documentos del curso</h3>
        {!documentsLoaded && !documentsError && (
          <div className="loading-state" role="status">
            Cargando documentos...
          </div>
        )}

        {documentsError && <p role="alert" className="alert alert--error">{documentsError}</p>}
        {documentsLoaded && documents.length === 0 && (
          <div className="empty-state">
            <p className="empty-state-title">Sin sílabos cargados</p>
            <p className="empty-state-text" style={{ marginBottom: 0 }}>
              Sube un archivo PDF para comenzar la extracción de actividades.
            </p>
          </div>
        )}

        {documents.length > 0 && (
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
                      onClick={() => onDocumentChange(courseId, doc.id)}
                    >
                      Ver actividades
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      disabled={!canStartOperation}
                      onClick={() => void handleStartExtraction(doc.id)}
                    >
                      {selectedExecution?.document_id === doc.id && selectedExecution.status === "failed"
                        ? "Reintentar análisis"
                        : "Extraer con IA"}
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
            {execution.document_id !== selectedDocId && (
              <span>
                {" · "}
                {documents.find((item) => item.id === execution.document_id)?.filename
                  ?? "Otro documento del curso"}
              </span>
            )}
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

          {activitiesError && <p role="alert" className="alert alert--error">{activitiesError}</p>}

          {activityDocumentId === selectedDocId && conflicts.length > 0 && (
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

          {activityDocumentId === selectedDocId && activities.length === 0 && (
            <div className="empty-state">
              <p className="empty-state-title">Sin actividades extraídas</p>
              <p className="empty-state-text" style={{ marginBottom: 0 }}>
                Ejecuta &ldquo;Extraer con IA&rdquo; sobre el documento para
                identificar evaluaciones y tareas.
              </p>
            </div>
          )}

          {activityDocumentId === selectedDocId && activities.length > 0 && (
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
