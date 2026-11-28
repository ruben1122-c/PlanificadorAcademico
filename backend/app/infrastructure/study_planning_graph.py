from datetime import datetime
from typing import Any, TypedDict
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.domain.exceptions import ExternalServiceError
from app.domain.planning_rules import (
    PlanningActivity,
    StudyBlock,
    StudyWindow,
    validate_study_plan,
)

_PLANNER_SYSTEM_PROMPT = (
    "Eres un subagente planificador académico experto. "
    "Tu tarea es asignar bloques de estudio concretos para las actividades aprobadas "
    "dentro de los intervalos de disponibilidad y el horizonte proporcionados. "
    "Reglas estrictas:\n"
    "1. Usa exclusivamente los activity_id exactos proporcionados.\n"
    "2. Cada bloque debe estar completamente contenido dentro de uno de los intervalos de disponibilidad "
    "y dentro del horizonte de planificación.\n"
    "3. El fin de cada bloque (end_at) debe ser anterior o igual al vencimiento (due_at) de la actividad.\n"
    "4. Los bloques no pueden solaparse entre sí.\n"
    "5. La suma de minutos asignados a cada actividad no debe superar su estimated_minutes.\n"
    "6. Todas las fechas deben estar en formato ISO-8601 con zona horaria explícita."
)


class ProposedBlockSchema(BaseModel):
    """Structured LLM output for a proposed study block."""

    activity_id: str = Field(description="UUID exacto de la actividad académica.")
    start_at: str = Field(description="Inicio del bloque en formato ISO-8601 con zona horaria.")
    end_at: str = Field(description="Fin del bloque en formato ISO-8601 con zona horaria.")


class StudyPlanOutput(BaseModel):
    """Structured LLM output returned by the Groq Planner subagent."""

    summary: str = Field(
        description="Resumen breve en español de la estrategia de planificación aplicada."
    )
    blocks: list[ProposedBlockSchema] = Field(default_factory=list)


class PlanningGraphState(TypedDict):
    """State passed across LangGraph nodes during study planning."""

    activities: list[PlanningActivity]
    activity_metadata: dict[str, dict[str, Any]]
    availability: list[StudyWindow]
    horizon: StudyWindow
    proposed_blocks: list[StudyBlock]
    accepted_blocks: list[StudyBlock]
    pending: dict[UUID, str]
    planner_summary: str | None


class StudyPlanningPipeline:
    """LangGraph workflow orchestrating Groq structured planning and deterministic validation."""

    def __init__(self, groq_api_key: str, model_name: str) -> None:
        self._model_name = model_name
        llm = ChatGroq(
            api_key=groq_api_key,
            model=model_name,
            temperature=0.0,
            timeout=15,
            max_retries=1,
        )
        self._structured_llm = llm.with_structured_output(
            StudyPlanOutput, method="json_schema"
        )
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        builder = StateGraph(PlanningGraphState)
        builder.add_node("propose_schedule", self._propose_schedule)
        builder.add_node("validate_rules", self._validate_rules)

        builder.add_edge(START, "propose_schedule")
        builder.add_edge("propose_schedule", "validate_rules")
        builder.add_edge("validate_rules", END)
        return builder.compile()

    def _propose_schedule(self, state: PlanningGraphState) -> dict[str, Any]:
        activities = state["activities"]
        availability = state["availability"]
        horizon = state["horizon"]
        metadata = state.get("activity_metadata", {})

        if not activities or not availability:
            return {
                "proposed_blocks": [],
                "planner_summary": (
                    "No hay actividades aprobadas/editadas elegibles o no hay intervalos de disponibilidad."
                ),
            }

        availability_lines = [
            f"- {slot.start.isoformat()} -> {slot.end.isoformat()}"
            for slot in availability
        ]
        activity_lines = []
        for act in activities:
            meta = metadata.get(str(act.activity_id), {})
            title = meta.get("title", str(act.activity_id))
            activity_lines.append(
                f"- activity_id={act.activity_id} | titulo={title} | "
                f"due_at={act.due_at.isoformat()} | estimated_minutes={act.estimated_minutes}"
            )

        user_prompt = (
            f"Horizonte de planificación: {horizon.start.isoformat()} -> {horizon.end.isoformat()}\n\n"
            f"Intervalos de disponibilidad:\n" + "\n".join(availability_lines) + "\n\n"
            f"Actividades a planificar:\n" + "\n".join(activity_lines)
        )

        try:
            result = self._structured_llm.invoke(
                [
                    SystemMessage(content=_PLANNER_SYSTEM_PROMPT),
                    HumanMessage(content=user_prompt),
                ]
            )
        except Exception as exc:
            raise ExternalServiceError(
                "Error al invocar el subagente Planificador Groq."
            ) from exc

        proposed_blocks: list[StudyBlock] = []
        if isinstance(result, StudyPlanOutput):
            for item in result.blocks:
                try:
                    activity_id = UUID(item.activity_id.strip())
                    start_dt = datetime.fromisoformat(item.start_at.strip())
                    end_dt = datetime.fromisoformat(item.end_at.strip())
                    window = StudyWindow(start=start_dt, end=end_dt)
                    proposed_blocks.append(
                        StudyBlock(activity_id=activity_id, window=window)
                    )
                except ValueError:
                    continue
            summary = result.summary.strip() or None
        else:
            summary = None

        return {
            "proposed_blocks": proposed_blocks,
            "planner_summary": summary,
        }

    @staticmethod
    def _validate_rules(state: PlanningGraphState) -> dict[str, Any]:
        accepted_blocks, pending = validate_study_plan(
            activities=state["activities"],
            availability=state["availability"],
            horizon=state["horizon"],
            proposed_blocks=state.get("proposed_blocks", []),
        )
        return {
            "accepted_blocks": accepted_blocks,
            "pending": pending,
        }

    def run(
        self,
        *,
        activities: list[PlanningActivity],
        availability: list[StudyWindow],
        horizon: StudyWindow,
        activity_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Execute the LangGraph + Groq planner and deterministic validation."""
        initial_state: PlanningGraphState = {
            "activities": activities,
            "activity_metadata": activity_metadata or {},
            "availability": availability,
            "horizon": horizon,
            "proposed_blocks": [],
            "accepted_blocks": [],
            "pending": {},
            "planner_summary": None,
        }
        final_state = self._graph.invoke(initial_state)
        return {
            "accepted_blocks": final_state.get("accepted_blocks", []),
            "pending": final_state.get("pending", {}),
            "planner_summary": final_state.get("planner_summary"),
            "model_name": self._model_name,
        }
