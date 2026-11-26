import type { AppTab } from "../App";
import type { Course } from "../types/api";

interface CoursesSectionProps {
  courses: Course[];
  activeCourse: Course | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onSelectCourse: (courseId: string) => void;
  onNavigate: (tab: AppTab) => void;
}

export function CoursesSection({
  courses,
  activeCourse,
  loading,
  error,
  onRefresh,
  onSelectCourse,
  onNavigate,
}: CoursesSectionProps) {
  return (
    <div className="panel-grid">
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Mis cursos</h2>
            <p className="card-subtitle">
              Selecciona un curso activo para gestionar su sílabo y cronograma.
            </p>
          </div>
          <div className="btn-row">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onRefresh}
              disabled={loading}
            >
              {loading ? "Actualizando..." : "Actualizar"}
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => onNavigate("new-course")}
            >
              + Nuevo curso
            </button>
          </div>
        </div>

        {error && (
          <div className="alert alert--error" role="alert">
            {error}
          </div>
        )}

        {loading && courses.length === 0 && (
          <div className="loading-state" role="status">
            Cargando tus cursos...
          </div>
        )}

        {!loading && courses.length === 0 && (
          <div className="empty-state">
            <p className="empty-state-title">No tienes cursos registrados</p>
            <p className="empty-state-text">
              Crea tu primer curso para subir su sílabo y planificar tus sesiones
              de estudio.
            </p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onNavigate("new-course")}
            >
              Crear primer curso
            </button>
          </div>
        )}

        {courses.length > 0 && (
          <div className="courses-grid">
            {courses.map((course) => {
              const isSelected = activeCourse?.id === course.id;
              return (
                <article
                  key={course.id}
                  className={`course-card${isSelected ? " is-selected" : ""}`}
                >
                  <div>
                    <div className="btn-row" style={{ justifyContent: "space-between" }}>
                      <span className="course-card-code">{course.code}</span>
                      {isSelected && (
                        <span className="badge badge--teal">Curso activo</span>
                      )}
                    </div>
                    <h3 className="course-card-name">{course.name}</h3>
                    <p className="course-card-meta">
                      {course.term ? `Periodo: ${course.term}` : "Sin periodo"}
                      {course.credits !== null
                        ? ` · ${course.credits} créditos`
                        : ""}
                    </p>
                  </div>

                  <div className="btn-row">
                    <button
                      type="button"
                      className={`btn btn-sm ${
                        isSelected ? "btn-navy" : "btn-secondary"
                      }`}
                      onClick={() => onSelectCourse(course.id)}
                      aria-pressed={isSelected}
                    >
                      {isSelected ? "Seleccionado" : "Seleccionar"}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>

      {activeCourse && (
        <div className="card">
          <div className="card-header">
            <div>
              <span className="badge badge--neutral">{activeCourse.code}</span>
              <h3 className="card-title" style={{ marginTop: "0.4rem" }}>
                {activeCourse.name}
              </h3>
            </div>
            <div className="btn-row">
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => onNavigate("syllabus")}
              >
                Ir a Sílabo y revisión
              </button>
              <button
                type="button"
                className="btn btn-navy btn-sm"
                onClick={() => onNavigate("schedule")}
              >
                Ir a Cronograma
              </button>
            </div>
          </div>

          <div className="activity-meta">
            <span>
              <strong>Periodo:</strong>{" "}
              {activeCourse.term ?? "No especificado"}
            </span>
            <span>
              <strong>Créditos:</strong>{" "}
              {activeCourse.credits ?? "No especificado"}
            </span>
          </div>
          <p className="card-subtitle" style={{ marginTop: "0.65rem" }}>
            {activeCourse.description ?? "Sin descripción registrada."}
          </p>
        </div>
      )}
    </div>
  );
}
