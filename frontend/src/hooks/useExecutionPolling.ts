import { useEffect, useRef } from "react";
import { getExecutionStatus } from "../api/client";
import type { ExtractionExecution } from "../types/api";

export function useExecutionPolling(
  token: string,
  execution: ExtractionExecution | null,
  onUpdate: (result: ExtractionExecution, signal: AbortSignal) => void | Promise<void>,
  onError: (message: string) => void,
) {
  const handlers = useRef({ onUpdate, onError });
  useEffect(() => {
    handlers.current = { onUpdate, onError };
  }, [onUpdate, onError]);

  const activeId = execution?.status === "pending" || execution?.status === "running"
    ? execution.id
    : null;

  useEffect(() => {
    if (!activeId) return;
    const executionId = activeId;
    const controller = new AbortController();
    const { signal } = controller;
    let timer: number | undefined;
    let finished = false;

    async function poll() {
      try {
        const result = await getExecutionStatus(token, executionId, signal);
        if (signal.aborted) return;
        finished = result.status === "completed" || result.status === "failed";
        await handlers.current.onUpdate(result, signal);
      } catch (error) {
        if (!signal.aborted) {
          handlers.current.onError(
            error instanceof Error ? error.message : "No se pudo consultar la ejecución.",
          );
        }
      }
      if (!finished && !signal.aborted) timer = window.setTimeout(poll, 2000);
    }

    timer = window.setTimeout(poll, 1000);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [activeId, token]);
}
