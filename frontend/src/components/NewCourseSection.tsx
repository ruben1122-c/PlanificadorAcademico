import { useState, type FormEvent } from "react";
import { createCourse } from "../api/client";
import type { Course } from "../types/api";

interface NewCourseSectionProps {
  token: string;
  onCourseCreated: (course: Course) => void;
  onCancel: () => void;
}

export function NewCourseSection({
  token,
  onCourseCreated,
  onCancel,
}: NewCourseSectionProps) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [term, setTerm] = useState("");
  const [credits, setCredits] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const parsedCredits =
      credits.trim() === "" ? null : Number.parseInt(credits, 10);

    try {
      const created = await createCourse(token, {
        code: code.trim(),
        name: name.trim(),
        term: term.trim() || null,
        credits: Number.isNaN(parsedCredits) ? null : parsedCredits,
        description: description.trim() || null,
      });
      setCode("");
      setName("");
      setTerm("");
      setCredits("");
      setDescription("");
      onCourseCreated(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error creando curso");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="card card--narrow">
      <div className="card-header">
        <div>
          <h2 className="card-title">Nuevo curso</h2>
          <p className="card-subtitle">
            Registra una asignatura para comenzar a extraer sus actividades.
          </p>
        </div>
      </div>

      <form className="form-stack" onSubmit={(e) => void handleSubmit(e)}>
        <div className="form-grid-2">
          <div className="form-field">
            <label className="form-label" htmlFor="new-course-code">
              Código *
            </label>
            <input
              id="new-course-code"
              className="form-input"
              type="text"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Ej. CS101"
            />
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="new-course-term">
              Periodo académico (opcional)
            </label>
            <input
              id="new-course-term"
              className="form-input"
              type="text"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Ej. 2026-2"
            />
          </div>
        </div>

        <div className="form-grid-2">
          <div className="form-field">
            <label className="form-label" htmlFor="new-course-name">
              Nombre del curso *
            </label>
            <input
              id="new-course-name"
              className="form-input"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ej. Arquitectura de Software"
            />
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="new-course-credits">
              Créditos (opcional)
            </label>
            <input
              id="new-course-credits"
              className="form-input"
              type="number"
              min={0}
              max={30}
              value={credits}
              onChange={(e) => setCredits(e.target.value)}
              placeholder="Ej. 4"
            />
          </div>
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="new-course-description">
            Descripción (opcional)
          </label>
          <textarea
            id="new-course-description"
            className="form-textarea"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Objetivos o notas generales del curso..."
          />
        </div>

        {error && (
          <div className="alert alert--error" role="alert">
            {error}
          </div>
        )}

        <div className="btn-row">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting}
          >
            {submitting ? "Guardando..." : "Crear curso"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={submitting}
            onClick={onCancel}
          >
            Cancelar
          </button>
        </div>
      </form>
    </div>
  );
}
