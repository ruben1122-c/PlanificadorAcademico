import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  checkHealth,
  getCurrentUser,
  listCourses,
} from "./api/client";
import { AvailabilitySection } from "./components/AvailabilitySection";
import { CoursesSection } from "./components/CoursesSection";
import { LoginForm } from "./components/LoginForm";
import { NewCourseSection } from "./components/NewCourseSection";
import { PlanningSection } from "./components/PlanningSection";
import { SyllabusSection } from "./components/SyllabusSection";
import type { Course, LoginResponse, User } from "./types/api";

export type AppTab =
  | "courses"
  | "new-course"
  | "syllabus"
  | "availability"
  | "schedule";

const TOKEN_STORAGE_KEY = "planificador_access_token";

const NAV_ITEMS: Array<{ id: AppTab; label: string }> = [
  { id: "courses", label: "Mis cursos" },
  { id: "new-course", label: "Nuevo curso" },
  { id: "syllabus", label: "Sílabo y revisión" },
  { id: "availability", label: "Disponibilidad" },
  { id: "schedule", label: "Cronograma" },
];

interface WorkspaceLocation {
  tab: AppTab;
  courseId: string | null;
  documentId: string | null;
}

function readWorkspaceLocation(): WorkspaceLocation {
  const query = new URLSearchParams(window.location.search);
  const tab = NAV_ITEMS.find((item) => item.id === query.get("section"));
  return {
    tab: tab?.id ?? "courses",
    courseId: query.get("course"),
    documentId: query.get("course") ? query.get("document") : null,
  };
}

function replaceWorkspaceLocation(location: WorkspaceLocation): void {
  const url = new URL(window.location.href);
  url.searchParams.set("section", location.tab);
  if (location.courseId) url.searchParams.set("course", location.courseId);
  else url.searchParams.delete("course");
  if (location.documentId) url.searchParams.set("document", location.documentId);
  else url.searchParams.delete("document");
  if (url.href !== window.location.href) {
    window.history.replaceState(window.history.state, "", url);
  }
}

export function App() {
  const [healthOnline, setHealthOnline] = useState<boolean>(false);
  const [healthLoading, setHealthLoading] = useState<boolean>(true);
  const [healthError, setHealthError] = useState<string | null>(null);

  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem(TOKEN_STORAGE_KEY)
  );
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState<boolean>(
    Boolean(localStorage.getItem(TOKEN_STORAGE_KEY))
  );

  const [workspace, setWorkspace] = useState(readWorkspaceLocation);
  const { tab: activeTab, courseId: activeCourseId, documentId } = workspace;
  const [courses, setCourses] = useState<Course[]>([]);
  const [coursesLoading, setCoursesLoading] = useState<boolean>(false);
  const [coursesError, setCoursesError] = useState<string | null>(null);
  const [coursesVerified, setCoursesVerified] = useState(false);
  const courseRequest = useRef(0);

  const verifyHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);

    try {
      await checkHealth();
      setHealthOnline(true);
    } catch {
      setHealthOnline(false);
      setHealthError("No se pudo conectar con el servicio.");
    } finally {
      setHealthLoading(false);
    }
  }, []);

  useEffect(() => {
    void verifyHealth();
  }, [verifyHealth]);

  useEffect(() => {
    if (!token) {
      setUser(null);
      setAuthLoading(false);
      return;
    }

    let cancelled = false;
    setAuthLoading(true);

    getCurrentUser(token)
      .then((currentUser) => {
        if (!cancelled) {
          setUser(currentUser);
        }
      })
      .catch(() => {
        if (!cancelled) {
          localStorage.removeItem(TOKEN_STORAGE_KEY);
          setToken(null);
          setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setAuthLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  const loadCourses = useCallback(async () => {
    if (!token) return;
    const request = ++courseRequest.current;
    setCoursesLoading(true);
    setCoursesError(null);
    try {
      const data = await listCourses(token);
      if (request !== courseRequest.current) return;
      setCourses(data);
      setWorkspace((previous) => {
        if (previous.courseId && data.some((course) => course.id === previous.courseId)) {
          return previous;
        }
        return {
          tab: previous.courseId ? "courses" : previous.tab,
          courseId: data[0]?.id ?? null,
          documentId: null,
        };
      });
      setCoursesVerified(true);
    } catch (err) {
      if (request !== courseRequest.current) return;
      setCoursesError(
        err instanceof Error ? err.message : "Error cargando cursos"
      );
    } finally {
      if (request === courseRequest.current) setCoursesLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!token || !user) {
      setCourses([]);
      setCoursesVerified(false);
      setCoursesError(null);
      return;
    }
    void loadCourses();
  }, [token, user, loadCourses]);

  const activeCourse = useMemo(
    () => courses.find((course) => course.id === activeCourseId) ?? null,
    [courses, activeCourseId]
  );

  useEffect(() => {
    if (user && coursesVerified) replaceWorkspaceLocation(workspace);
  }, [user, coursesVerified, workspace]);

  function setActiveTab(tab: AppTab) {
    setWorkspace((previous) => ({ ...previous, tab }));
  }

  const handleDocumentChange = useCallback((courseId: string, documentId: string | null) => {
    setWorkspace((previous) =>
      previous.courseId === courseId && previous.documentId !== documentId
        ? { ...previous, documentId }
        : previous
    );
  }, []);

  function handleLoginSuccess(session: LoginResponse) {
    courseRequest.current += 1;
    localStorage.setItem(TOKEN_STORAGE_KEY, session.access_token);
    setCourses([]);
    setCoursesVerified(false);
    setCoursesError(null);
    setToken(session.access_token);
    setUser(session.user);
  }

  function handleLogout() {
    courseRequest.current += 1;
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUser(null);
    setCourses([]);
    setCoursesVerified(false);
    setCoursesError(null);
    const initial: WorkspaceLocation = { tab: "courses", courseId: null, documentId: null };
    setWorkspace(initial);
    replaceWorkspaceLocation(initial);
  }

  function handleSelectCourse(courseId: string) {
    setWorkspace((previous) =>
      previous.courseId === courseId ? previous : { ...previous, courseId, documentId: null }
    );
  }

  function handleCourseCreated(created: Course) {
    setCourses((prev) => [created, ...prev]);
    setWorkspace({ tab: "courses", courseId: created.id, documentId: null });
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="brand-block">
            <h1 className="brand-title">Planificador Académico</h1>
            <p className="brand-subtitle">
              Gestión de cursos, sílabos y cronograma de estudio
            </p>
          </div>

          <div className="header-actions">
            <span className="user-pill" aria-live="polite">
              <span
                className={`status-dot ${
                  healthLoading
                    ? "status-dot--loading"
                    : healthOnline
                      ? "status-dot--ok"
                      : "status-dot--error"
                }`}
                aria-hidden="true"
              />
              <span>
                {healthLoading
                  ? "Verificando servicio..."
                  : healthOnline
                    ? "Servicio en línea"
                    : "Sin conexión"}
              </span>
            </span>

            {healthError && !healthLoading && (
              <button
                type="button"
                className="btn btn-ghost-light btn-sm"
                onClick={() => void verifyHealth()}
              >
                Reintentar
              </button>
            )}

            {!authLoading && token && user && (
              <>
                <span className="user-pill" title={user.email}>
                  <strong>{user.email}</strong>
                </span>
                <button
                  type="button"
                  className="btn btn-ghost-light btn-sm"
                  onClick={handleLogout}
                >
                  Cerrar sesión
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      {!authLoading && token && user && (
        <div key={user.id}>
          <div className="workspace-nav-wrap">
            <div className="workspace-nav-inner">
              <nav className="nav-tabs" aria-label="Navegación principal">
                {NAV_ITEMS.map((item) => {
                  const isActive = activeTab === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`nav-tab${isActive ? " is-active" : ""}`}
                      aria-current={isActive ? "page" : undefined}
                      onClick={() => setActiveTab(item.id)}
                    >
                      {item.label}
                    </button>
                  );
                })}
              </nav>

              <div className="active-course-bar">
                <label
                  htmlFor="active-course-switcher"
                  className="active-course-label"
                >
                  Curso activo:
                </label>
                {courses.length > 0 ? (
                  <select
                    id="active-course-switcher"
                    className="active-course-select"
                    value={activeCourseId ?? ""}
                    onChange={(e) => void handleSelectCourse(e.target.value)}
                  >
                    {courses.map((course) => (
                      <option key={course.id} value={course.id}>
                        {course.code} — {course.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="active-course-empty">
                    {coursesLoading ? "Cargando..." : "Sin cursos"}
                  </span>
                )}
              </div>
            </div>
          </div>

          <main className="app-main">
            <section
              aria-label="Mis cursos"
              hidden={activeTab !== "courses"}
            >
              <CoursesSection
                courses={courses}
                activeCourse={activeCourse}
                loading={coursesLoading}
                error={coursesError}
                onRefresh={() => void loadCourses()}
                onSelectCourse={(id) => {
                  handleSelectCourse(id);
                  setActiveTab("syllabus");
                }}
                onNavigate={setActiveTab}
              />
            </section>

            <section
              aria-label="Nuevo curso"
              hidden={activeTab !== "new-course"}
            >
              <NewCourseSection
                token={token}
                onCourseCreated={handleCourseCreated}
                onCancel={() => setActiveTab("courses")}
              />
            </section>

            <section
              aria-label="Sílabo y revisión"
              hidden={activeTab !== "syllabus"}
            >
              <SyllabusSection
                key={activeCourse?.id ?? "no-course"}
                token={token}
                userId={user.id}
                course={activeCourse}
                visible={activeTab === "syllabus"}
                documentId={documentId}
                onDocumentChange={handleDocumentChange}
                onGoToCourses={() => setActiveTab("courses")}
                onGoToNewCourse={() => setActiveTab("new-course")}
              />
            </section>

            <section
              aria-label="Disponibilidad"
              hidden={activeTab !== "availability"}
            >
              <AvailabilitySection token={token} />
            </section>

            <section
              aria-label="Cronograma"
              hidden={activeTab !== "schedule"}
            >
              <PlanningSection
                token={token}
                course={activeCourse}
                onGoToCourses={() => setActiveTab("courses")}
                onGoToAvailability={() => setActiveTab("availability")}
              />
            </section>
          </main>
        </div>
      )}

      {(authLoading || !token || !user) && (
        <main className="app-main">
          {authLoading ? (
            <div className="loading-state" role="status">
              Verificando sesión...
            </div>
          ) : (
            <div className="auth-container">
              <LoginForm onLoginSuccess={handleLoginSuccess} />
            </div>
          )}
        </main>
      )}
    </div>
  );
}

export default App;
