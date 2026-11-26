import type { ExtractionExecution } from "../types/api";

const stageLabels: Record<string, string> = {
  claimed: "Preparando ejecución",
  load_metadata: "Preparando sílabo",
  download_pdf: "Leyendo PDF",
  load_inputs: "Reuniendo actividades y disponibilidad",
  principal_delegate: "Agente principal · Delegando",
  extract_syllabus: "Documental · Analizando páginas",
  plan_schedule: "Planificador · Proponiendo bloques",
  persist_results: "Guardando evidencias",
  persist_plan: "Guardando cronograma",
};

export function ExecutionStage({ execution }: { execution: ExtractionExecution }) {
  if (execution.status !== "running" || !execution.stage) return null;
  const label = stageLabels[execution.stage];
  return label ? <span> · {label}</span> : null;
}
