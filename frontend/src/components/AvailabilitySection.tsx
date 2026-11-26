import { useCallback, useEffect, useState, type FormEvent } from "react";
import { getAvailability, putAvailability } from "../api/client";
import type { AvailabilityIntervalPayload } from "../types/api";

interface AvailabilitySectionProps {
  token: string;
}

interface IntervalDraft {
  startLocal: string;
  endLocal: string;
}

function toDateTimeLocalValue(iso: string): string {
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
  return `${trimmed}:00${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

export function AvailabilitySection({ token }: AvailabilitySectionProps) {
  const [intervals, setIntervals] = useState<IntervalDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadAvailability = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const saved = await getAvailability(token);
      setIntervals(
        saved.map((item) => ({
          startLocal: toDateTimeLocalValue(item.start_at),
          endLocal: toDateTimeLocalValue(item.end_at),
        }))
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Error cargando intervalos de disponibilidad"
      );
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadAvailability();
  }, [loadAvailability]);

  function handleAddInterval() {
    setIntervals((prev) => [...prev, { startLocal: "", endLocal: "" }]);
    setMessage(null);
    setError(null);
  }

  function handleRemoveInterval(index: number) {
    setIntervals((prev) => prev.filter((_, idx) => idx !== index));
    setMessage(null);
  }

  function handleUpdateInterval(
    index: number,
    field: "startLocal" | "endLocal",
    value: string
  ) {
    setIntervals((prev) =>
      prev.map((item, idx) =>
        idx === index ? { ...item, [field]: value } : item
      )
    );
    setMessage(null);
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);

    const payload: AvailabilityIntervalPayload[] = [];
    for (const item of intervals) {
      const startAt = toIsoWithLocalOffset(item.startLocal);
      const endAt = toIsoWithLocalOffset(item.endLocal);
      if (!startAt || !endAt) {
        setError("Completa inicio y fin válidos en todos los intervalos.");
        return;
      }
      payload.push({ start_at: startAt, end_at: endAt });
    }

    setSaving(true);
    try {
      const saved = await putAvailability(token, payload);
      setIntervals(
        saved.map((item) => ({
          startLocal: toDateTimeLocalValue(item.start_at),
          endLocal: toDateTimeLocalValue(item.end_at),
        }))
      );
      setMessage(
        `Disponibilidad guardada correctamente (${saved.length} ${
          saved.length === 1 ? "intervalo" : "intervalos"
        }).`
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Error guardando disponibilidad"
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h2 className="card-title">Disponibilidad de estudio</h2>
          <p className="card-subtitle">
            Los horarios se muestran en {Intl.DateTimeFormat().resolvedOptions().timeZone}.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={handleAddInterval}
          disabled={loading}
        >
          + Agregar intervalo
        </button>
      </div>

      {error && (
        <div className="alert alert--error" role="alert" style={{ marginBottom: "1rem" }}>
          {error}
        </div>
      )}

      {message && (
        <div className="alert alert--success" role="status" style={{ marginBottom: "1rem" }}>
          {message}
        </div>
      )}

      {loading && (
        <div className="loading-state" role="status">
          Cargando disponibilidad...
        </div>
      )}

      {!loading && (
        <form className="form-stack" onSubmit={(e) => void handleSave(e)}>
          {intervals.length === 0 ? (
            <div className="empty-state">
              <p className="empty-state-title">Sin intervalos configurados</p>
              <p className="empty-state-text">
                Agrega al menos una franja horaria para que el planificador
                pueda programar bloques de estudio.
              </p>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleAddInterval}
              >
                + Agregar primer intervalo
              </button>
            </div>
          ) : (
            <div className="form-stack">
              {intervals.map((item, idx) => {
                const startId = `avail-start-${idx}`;
                const endId = `avail-end-${idx}`;
                return (
                  <div key={idx} className="interval-row">
                    <div className="form-field">
                      <label className="form-label" htmlFor={startId}>
                        Inicio
                      </label>
                      <input
                        id={startId}
                        className="form-input"
                        type="datetime-local"
                        value={item.startLocal}
                        onChange={(e) =>
                          handleUpdateInterval(idx, "startLocal", e.target.value)
                        }
                      />
                    </div>
                    <div className="form-field">
                      <label className="form-label" htmlFor={endId}>
                        Fin
                      </label>
                      <input
                        id={endId}
                        className="form-input"
                        type="datetime-local"
                        value={item.endLocal}
                        onChange={(e) =>
                          handleUpdateInterval(idx, "endLocal", e.target.value)
                        }
                      />
                    </div>
                    <button
                      type="button"
                      className="btn btn-danger-outline btn-sm"
                      onClick={() => handleRemoveInterval(idx)}
                    >
                      Quitar
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          <div className="btn-row">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={saving}
            >
              {saving ? "Guardando..." : "Guardar disponibilidad"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
