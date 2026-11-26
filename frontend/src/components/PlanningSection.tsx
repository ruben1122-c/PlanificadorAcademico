import { useExecutionPolling } from "../hooks/useExecutionPolling";
import { ExecutionStage } from "./ExecutionStage";
import { useState, type FormEvent } from "react";
import {
  getStudyPlan,
  startPlanningRun,
} from "../api/client";
import type {
  Course,
  ExecutionStatus,
  ExtractionExecution,
  StudyPlan,
} from "../types/api";

interface PlanningSectionProps {
  token: string;
  course: Course | null;
  onGoToCourses: () => void;
  onGoToAvailability: () => void;
}

const EXECUTION_STATUS_LABELS: Record<ExecutionStatus, string> = {
  pending: "En cola",
  running: "Generando cronograma",
  completed: "Completado",
  failed: "Con error",
};

function toIsoWithLocalOffset(localValue: string): string | null {
  const trimmed = localValue.trim();
  if (!trimmed) return null;
  const date = new Date(trimmed);
  if (Number.isNaN(date.getTime())) return null;
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMinutes);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${trimmed}:00${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("es", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function PlanningSection({
  token,
  course,
  onGoToCourses,
  onGoToAvailability,
}: PlanningSectionProps) {
  const [horizonStartByCourse, setHorizonStartByCourse] = useState<
    Record<string, string>
  >({});
  const [horizonEndByCourse, setHorizonEndByCourse] = useState<
    Record<string, string>
  >({});
  const [executionsByCourse, setExecutionsByCourse] = useState<
    Record<string, ExtractionExecution>
  >({});
  const [plansByCourse, setPlansByCourse] = useState<Record<string, StudyPlan>>(
    {}
  );
  const [startingByCourse, setStartingByCourse] = useState<
    Record<string, boolean>
  >({});
  const [errorByCourse, setErrorByCourse] = useState<
    Record<string, string | null>
  >({});

  const courseId = course?.id ?? null;
  const horizonStart = courseId ? (horizonStartByCourse[courseId] ?? "") : "";
  const horizonEnd = courseId ? (horizonEndByCourse[courseId] ?? "") : "";
  const planningExecution = courseId
    ? (executionsByCourse[courseId] ?? null)
    : null;
  const studyPlan = courseId ? (plansByCourse[courseId] ?? null) : null;
  const startingPlan = courseId ? Boolean(startingByCourse[courseId]) : false;
  const error = courseId ? (errorByCourse[courseId] ?? null) : null;

  useExecutionPolling(token, planningExecution, async (updated, signal) => {
    if (!courseId) return;
    try {
      if (updated.status === "completed" && updated.plan_id) {
        const plan = await getStudyPlan(token, updated.plan_id, courseId);
        if (signal.aborted) return;
        setPlansByCourse((previous) => ({ ...previous, [courseId]: plan }));
      }
      setErrorByCourse((previous) => ({ ...previous, [courseId]: null }));
    } finally {
      if (!signal.aborted) {
        setExecutionsByCourse((previous) => ({ ...previous, [courseId]: updated }));
      }
    }
  }, (message) => {
    if (courseId) setErrorByCourse((previous) => ({ ...previous, [courseId]: message }));
  });

  if (!course || !courseId) {
    return (
      <div className="card">
        <div className="empty-state">
          <p className="empty-state-title">No hay un curso activo</p>
          <p className="empty-state-text">
            Selecciona o crea un curso para generar su cronograma de estudio.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onGoToCourses}
          >
            Ir a Mis cursos
          </button>
        </div>
      </div>
    );
  }

  async function handleStartPlanning(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!courseId) return;

    setErrorByCourse((prev) => ({ ...prev, [courseId]: null }));

    const startIso = toIsoWithLocalOffset(horizonStart);
    const endIso = toIsoWithLocalOffset(horizonEnd);
    if (!startIso || !endIso) {
      setErrorByCourse((prev) => ({
        ...prev,
        [courseId]: "Selecciona inicio y fin válidos del horizonte.",
      }));
      return;
    }

    setStartingByCourse((prev) => ({ ...prev, [courseId]: true }));
    setPlansByCourse((prev) => {
      const next = { ...prev };
      delete next[courseId];
      return next;
    });

    try {
      const execution = await startPlanningRun(token, {
        course_id: courseId,
        horizon_start: startIso,
        horizon_end: endIso,
      });
      setExecutionsByCourse((prev) => ({
        ...prev,
        [courseId]: execution,
      }));
    } catch (err) {
      setErrorByCourse((prev) => ({
        ...prev,
        [courseId]:
          err instanceof Error
            ? err.message
            : "Error iniciando la generación del plan",
      }));
    } finally {
      setStartingByCourse((prev) => ({ ...prev, [courseId]: false }));
    }
  }

  return (
    <div className="panel-grid">
      <div className="card">
        <div className="card-header">
          <div>
            <span className="badge badge--teal">{course.code}</span>
            <h2 className="card-title" style={{ marginTop: "0.35rem" }}>
              Cronograma de estudio — {course.name}
            </h2>
            <p className="card-subtitle">
              Genera bloques de estudio según tus actividades aprobadas y tu
              disponibilidad registrada.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onGoToAvailability}
          >
            Editar disponibilidad
          </button>
        </div>

        {error && (
          <div className="alert alert--error" role="alert" style={{ marginBottom: "1rem" }}>
            {error}
          </div>
        )}

        <form
          className="form-stack"
          onSubmit={(e) => void handleStartPlanning(e)}
        >
          <div className="form-grid-2">
            <div className="form-field">
              <label className="form-label" htmlFor="horizon-start">
                Inicio del horizonte
              </label>
              <input
                id="horizon-start"
                className="form-input"
                type="datetime-local"
                value={horizonStart}
                onChange={(e) =>
                  setHorizonStartByCourse((prev) => ({
                    ...prev,
                    [courseId]: e.target.value,
                  }))
                }
              />
            </div>

            <div className="form-field">
              <label className="form-label" htmlFor="horizon-end">
                Fin del horizonte
              </label>
              <input
                id="horizon-end"
                className="form-input"
                type="datetime-local"
                value={horizonEnd}
                onChange={(e) =>
                  setHorizonEndByCourse((prev) => ({
                    ...prev,
                    [courseId]: e.target.value,
                  }))
                }
              />
            </div>
          </div>

          <div className="btn-row">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={startingPlan || planningExecution?.status === "pending" || planningExecution?.status === "running"}
            >
              {startingPlan ? "Iniciando..." : "Planificar estudio"}
            </button>
          </div>
        </form>

        {planningExecution && (
          <div
            className={`alert ${
              planningExecution.status === "failed"
                ? "alert--error"
                : planningExecution.status === "completed"
                  ? "alert--success"
                  : "alert--info"
            }`}
            role="status"
            style={{ marginTop: "1rem" }}
          >
            <strong>Estado:</strong>{" "}
            {EXECUTION_STATUS_LABELS[planningExecution.status]}
            <ExecutionStage execution={planningExecution} />
            {planningExecution.error_message && (
              <p style={{ margin: "0.4rem 0 0" }}>
                {planningExecution.error_message}
              </p>
            )}
          </div>
        )}
      </div>

      {studyPlan && (
        <div className="card">
          <div className="card-header">
            <div>
              <h3 className="card-title">Plan generado</h3>
              {studyPlan.planner_summary && (
                <p className="card-subtitle">{studyPlan.planner_summary}</p>
              )}
            </div>
          </div>

          <div className="panel-grid">
            <div>
              <h4 className="section-title">
                Bloques programados ({studyPlan.blocks.length})
              </h4>
              {studyPlan.blocks.length === 0 ? (
                <div className="empty-state">
                  <p className="empty-state-title">Sin bloques asignados</p>
                  <p className="empty-state-text" style={{ marginBottom: 0 }}>
                    No se encontraron franjas compatibles para las actividades
                    en este horizonte.
                  </p>
                </div>
              ) : (
                <ul className="item-list">
                  {[...studyPlan.blocks].sort(
                    (a, b) => Date.parse(a.start_at) - Date.parse(b.start_at),
                  ).map((block) => (
                    <li key={block.id} className="plan-block-row">
                      <div>
                        <strong>
                          {block.activity_title ?? "Actividad de estudio"}
                        </strong>
                        <div className="course-card-meta">
                          {formatDateTime(block.start_at)} →{" "}
                          {formatDateTime(block.end_at)}
                        </div>
                      </div>
                      <span className="badge badge--teal">
                        {block.duration_minutes} min
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <hr className="divider" />

            <div>
              <h4 className="section-title">
                Actividades pendientes ({studyPlan.pending_activities.length})
              </h4>
              {studyPlan.pending_activities.length === 0 ? (
                <div className="alert alert--success">
                  Todas las actividades elegibles quedaron cubiertas en el
                  cronograma.
                </div>
              ) : (
                <ul className="item-list">
                  {studyPlan.pending_activities.map((item) => (
                    <li key={item.id} className="doc-row">
                      <strong>
                        {item.activity_title ?? "Actividad sin título"}
                      </strong>
                      <span className="badge badge--warning">
                        {item.reason === "INSUFFICIENT_AVAILABILITY"
                          ? "Disponibilidad insuficiente"
                          : item.reason}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
