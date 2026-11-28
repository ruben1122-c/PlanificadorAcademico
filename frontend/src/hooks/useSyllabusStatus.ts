import { useCallback, useEffect, useRef, useState } from "react";
import { getCourseSyllabusStatus, getExecutionStatus } from "../api/client";
import type {
  CourseSyllabusStatus,
  ExtractionExecution,
  SyllabusDocument,
} from "../types/api";

interface SyllabusSnapshot {
  status: CourseSyllabusStatus;
  latestDocument: SyllabusDocument | null;
}

export function useSyllabusStatus(
  token: string,
  courseId: string | null,
  documentId: string | null,
  visible: boolean,
) {
  const [snapshot, setSnapshot] = useState<SyllabusSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const activePoll = useRef<AbortController | null>(null);
  const refresh = useCallback(() => {
    activePoll.current?.abort();
    setSnapshot(null);
    setError(null);
    setVersion((previous) => previous + 1);
  }, []);

  useEffect(() => {
    if (!visible || !courseId) return;
    const targetCourseId = courseId;
    const controller = new AbortController();
    activePoll.current = controller;
    const { signal } = controller;
    let timer: number | undefined;
    let activeExecution: ExtractionExecution | null = null;

    async function poll() {
      if (signal.aborted) return;
      try {
        if (activeExecution) {
          const updated = await getExecutionStatus(token, activeExecution.id, signal);
          if (signal.aborted) return;
          if (updated.status === "pending" || updated.status === "running") {
            activeExecution = updated;
            setSnapshot((previous) => previous && ({
              ...previous,
              status: {
                ...previous.status,
                active_execution: updated,
                execution: previous.status.document?.id === updated.document_id
                  ? updated
                  : previous.status.execution,
              },
            }));
            setError(null);
            return;
          }
          activeExecution = null;
        }

        const current = await getCourseSyllabusStatus(token, targetCourseId, null, signal);
        const status = documentId && current.document?.id !== documentId
          ? await getCourseSyllabusStatus(token, targetCourseId, documentId, signal)
          : current;
        if (signal.aborted) return;
        activeExecution = status.active_execution;
        setSnapshot({ status, latestDocument: current.document });
        setError(null);
      } catch (error) {
        if (!signal.aborted) {
          setError(error instanceof Error ? error.message : "No se pudo consultar el estado del sílabo.");
        }
      } finally {
        if (!signal.aborted) timer = window.setTimeout(poll, 2000);
      }
    }

    void poll();
    return () => {
      controller.abort();
      if (activePoll.current === controller) activePoll.current = null;
      window.clearTimeout(timer);
    };
  }, [courseId, documentId, token, version, visible]);

  return { snapshot, statusError: error, refreshStatus: refresh };
}
