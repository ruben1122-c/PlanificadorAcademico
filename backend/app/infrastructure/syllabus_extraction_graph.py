import re
import time
from datetime import date
from typing import Any, Literal, TypedDict

import pymupdf
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.domain.exceptions import ExternalServiceError

_WHITESPACE_RE = re.compile(r"\s+")
_SPANISH_DATE_RE = re.compile(r"(\d{1,2}) de ([a-z]+) de (\d{4})")
_SPANISH_MONTHS = {
    name: number
    for number, name in enumerate(
        "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
        start=1,
    )
}

_SYSTEM_PROMPT = (
    "Eres un asistente académico experto en extracción de sílabos universitarios. "
    "Analiza únicamente el texto de la página proporcionada y extrae todas las "
    "actividades evaluables, entregas, exámenes, laboratorios, proyectos, lecturas "
    "o presentaciones con fecha o ponderación explícita o implícita. "
    "No inventes datos que no estén en el texto. "
    "Para cada actividad incluye una cita textual exacta (`evidence_quote`) "
    "copiada literalmente del texto de la página."
)


class ExtractedActivitySchema(BaseModel):
    """Structured LLM output for a single activity extracted from a syllabus page."""

    title: str = Field(description="Nombre claro de la actividad o evaluación.")
    activity_type: Literal[
        "exam",
        "assignment",
        "project",
        "lab",
        "reading",
        "presentation",
        "other",
    ] = Field(description="Categoría de la actividad académica.")
    due_date: str | None = Field(
        default=None,
        description="Fecha de entrega o examen en formato ISO YYYY-MM-DD si aparece.",
    )
    due_time: str | None = Field(
        default=None,
        description="Hora de entrega o examen si aparece (ej. 23:59 o 14:00).",
    )
    weight_percentage: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Porcentaje de la nota final (0 a 100) si aparece.",
    )
    description: str | None = Field(
        default=None,
        description="Breve descripción o alcance de la actividad.",
    )
    evidence_quote: str = Field(
        description="Cita textual exacta tomada de esta página que respalda la extracción."
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Nivel de confianza entre 0.0 y 1.0.",
    )


class PageExtractionOutput(BaseModel):
    """Structured LLM output for a single syllabus page."""

    activities: list[ExtractedActivitySchema] = Field(default_factory=list)


class ExtractionGraphState(TypedDict):
    """State passed across LangGraph nodes during syllabus extraction."""

    pdf_bytes: bytes
    course_code: str
    course_name: str
    pages: list[dict[str, Any]]
    current_page_index: int
    raw_extractions: list[dict[str, Any]]
    validated_activities: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    deadline_monotonic: float


def _normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip().lower()


def _parse_iso_date(raw_date: str | None) -> date | None:
    if not raw_date:
        return None
    cleaned = raw_date.strip()
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        match = _SPANISH_DATE_RE.fullmatch(_normalize_text(cleaned))
        if match is None:
            return None
        day, month, year = match.groups()
        try:
            return date(int(year), _SPANISH_MONTHS[month], int(day))
        except (KeyError, ValueError):
            return None


def _is_quote_present_in_page(quote: str, page_text: str) -> bool:
    norm_quote = _normalize_text(quote)
    norm_page = _normalize_text(page_text)
    return bool(norm_quote) and norm_quote in norm_page


class SyllabusExtractionPipeline:
    """LangGraph workflow orchestrating PyMuPDF per-page extraction and Groq structured output."""

    def __init__(
        self,
        groq_api_key: str,
        model_name: str,
        job_timeout_seconds: int = 120,
    ) -> None:
        self._model_name = model_name
        self._job_timeout_seconds = job_timeout_seconds
        llm = ChatGroq(
            api_key=groq_api_key,
            model=model_name,
            temperature=0.0,
            timeout=15,
            max_retries=1,
        )
        self._structured_llm = llm.with_structured_output(
            PageExtractionOutput, method="json_schema"
        )
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        builder = StateGraph(ExtractionGraphState)
        builder.add_node("extract_pdf_pages", self._extract_pdf_pages)
        builder.add_node("extract_page_activities", self._extract_page_activities)
        builder.add_node("validate_evidence", self._validate_evidence)
        builder.add_node("detect_conflicts", self._detect_conflicts)

        builder.add_edge(START, "extract_pdf_pages")
        builder.add_conditional_edges(
            "extract_pdf_pages",
            self._route_after_pdf_load,
            {
                "extract_page": "extract_page_activities",
                "finish": "validate_evidence",
            },
        )
        builder.add_conditional_edges(
            "extract_page_activities",
            self._route_next_page,
            {
                "next_page": "extract_page_activities",
                "validate": "validate_evidence",
            },
        )
        builder.add_edge("validate_evidence", "detect_conflicts")
        builder.add_edge("detect_conflicts", END)
        return builder.compile()

    def _extract_pdf_pages(self, state: ExtractionGraphState) -> dict[str, Any]:
        pages: list[dict[str, Any]] = []
        conflicts = list(state.get("conflicts", []))

        try:
            with pymupdf.open(stream=state["pdf_bytes"], filetype="pdf") as doc:
                if len(doc) > 25:
                    raise ValueError("PDF excede 25 páginas.")
                for idx, page in enumerate(doc, start=1):
                    text = page.get_text("text") or ""
                    pages.append({"page_number": idx, "text": text})
        except Exception as exc:
            raise ExternalServiceError(
                "No se pudo leer el archivo PDF con PyMuPDF."
            ) from exc

        if not pages or all(len(p["text"].strip()) < 10 for p in pages):
            conflicts.append(
                {
                    "conflict_type": "empty_pdf_text",
                    "severity": "error",
                    "message": (
                        "El PDF no contiene texto extraíble (posiblemente es un documento escaneado)."
                    ),
                    "source_page": 1 if pages else None,
                    "details": {"total_pages": len(pages)},
                }
            )

        return {
            "pages": pages,
            "current_page_index": 0,
            "conflicts": conflicts,
        }

    @staticmethod
    def _route_after_pdf_load(state: ExtractionGraphState) -> str:
        pages = state.get("pages", [])
        if not pages:
            return "finish"
        return "extract_page"

    def _extract_page_activities(
        self, state: ExtractionGraphState
    ) -> dict[str, Any]:
        if time.monotonic() > state["deadline_monotonic"]:
            raise TimeoutError("La extracción superó el tiempo límite acotado.")

        idx = state["current_page_index"]
        pages = state["pages"]
        page = pages[idx]
        page_number = page["page_number"]
        page_text = page["text"]

        raw_extractions = list(state.get("raw_extractions", []))
        conflicts = list(state.get("conflicts", []))

        if len(page_text.strip()) >= 20:
            user_prompt = (
                f"Curso: {state['course_code']} - {state['course_name']}\n"
                f"Página {page_number} de {len(pages)}:\n\n"
                f"{page_text[:12000]}"
            )
            try:
                result = self._structured_llm.invoke(
                    [
                        SystemMessage(content=_SYSTEM_PROMPT),
                        HumanMessage(content=user_prompt),
                    ]
                )
                extracted_items = (
                    result.activities
                    if isinstance(result, PageExtractionOutput)
                    else []
                )
                for item in extracted_items:
                    raw_extractions.append(
                        {
                            "title": item.title.strip(),
                            "activity_type": item.activity_type,
                            "raw_due_date": item.due_date,
                            "due_date": _parse_iso_date(item.due_date),
                            "due_time": item.due_time.strip()
                            if item.due_time
                            else None,
                            "weight_percentage": item.weight_percentage,
                            "description": item.description.strip()
                            if item.description
                            else None,
                            "source_page": page_number,
                            "evidence_quote": item.evidence_quote.strip()
                            or item.title.strip(),
                            "confidence": item.confidence,
                        }
                    )
            except Exception as exc:
                raise ExternalServiceError(
                    f"No se pudo analizar la página {page_number} con Groq."
                ) from exc

        return {
            "current_page_index": idx + 1,
            "raw_extractions": raw_extractions,
            "conflicts": conflicts,
        }

    @staticmethod
    def _route_next_page(state: ExtractionGraphState) -> str:
        if state["current_page_index"] < len(state["pages"]):
            return "next_page"
        return "validate"

    @staticmethod
    def _validate_evidence(state: ExtractionGraphState) -> dict[str, Any]:
        page_map = {p["page_number"]: p["text"] for p in state.get("pages", [])}
        validated_activities: list[dict[str, Any]] = []
        conflicts = list(state.get("conflicts", []))

        for raw in state.get("raw_extractions", []):
            page_num = raw["source_page"]
            page_text = page_map.get(page_num, "")
            quote = raw.get("evidence_quote", "")
            evidence_valid = _is_quote_present_in_page(quote, page_text)

            activity_idx = len(validated_activities)
            validated_activities.append(
                {
                    "title": raw["title"],
                    "activity_type": raw["activity_type"],
                    "due_date": raw.get("due_date"),
                    "due_time": raw.get("due_time"),
                    "weight_percentage": raw.get("weight_percentage"),
                    "description": raw.get("description"),
                    "source_page": page_num,
                    "evidence_quote": quote,
                    "evidence_valid": evidence_valid,
                    "confidence": raw.get("confidence"),
                    "raw_due_date": raw.get("raw_due_date"),
                }
            )

            if not evidence_valid:
                conflicts.append(
                    {
                        "activity_index": activity_idx,
                        "conflict_type": "unverified_evidence",
                        "severity": "warning",
                        "message": (
                            f"La cita de evidencia para '{raw['title']}' no se encontró "
                            f"literalmente en la página {page_num}."
                        ),
                        "source_page": page_num,
                        "details": {"evidence_quote": quote},
                    }
                )

            if raw.get("raw_due_date") and raw.get("due_date") is None:
                conflicts.append(
                    {
                        "activity_index": activity_idx,
                        "conflict_type": "invalid_due_date_format",
                        "severity": "warning",
                        "message": (
                            f"No se pudo interpretar la fecha '{raw['raw_due_date']}' "
                            f"para '{raw['title']}'."
                        ),
                        "source_page": page_num,
                        "details": {"raw_due_date": raw["raw_due_date"]},
                    }
                )

            confidence = raw.get("confidence")
            if confidence is not None and confidence < 0.6:
                conflicts.append(
                    {
                        "activity_index": activity_idx,
                        "conflict_type": "low_confidence",
                        "severity": "info",
                        "message": (
                            f"Confianza baja ({confidence:.2f}) en la extracción de '{raw['title']}'."
                        ),
                        "source_page": page_num,
                        "details": {"confidence": confidence},
                    }
                )

        return {
            "validated_activities": validated_activities,
            "conflicts": conflicts,
        }

    @staticmethod
    def _detect_conflicts(state: ExtractionGraphState) -> dict[str, Any]:
        activities = state.get("validated_activities", [])
        conflicts = list(state.get("conflicts", []))

        seen_keys: dict[tuple[str, str], int] = {}
        first_dated_activity: dict[str, dict[str, Any]] = {}
        total_weight = 0.0

        for idx, act in enumerate(activities):
            due_key = act["due_date"].isoformat() if act.get("due_date") else ""
            title_key = _normalize_text(act["title"])
            dedup_key = (title_key, due_key)
            if due_key and act["evidence_valid"]:
                first = first_dated_activity.setdefault(title_key, act)
                if first["due_date"] != act["due_date"]:
                    conflicts.append(
                        {
                            "activity_index": idx,
                            "conflict_type": "contradictory_due_dates",
                            "severity": "warning",
                            "message": (
                                f"{act['title']}: {first['due_date']} (página "
                                f"{first['source_page']}) y {due_key} (página "
                                f"{act['source_page']}). Confirma una fecha."
                            ),
                            "source_page": act["source_page"],
                            "details": {"pages": [first["source_page"], act["source_page"]]},
                        }
                    )
            if dedup_key in seen_keys:
                conflicts.append(
                    {
                        "activity_index": idx,
                        "conflict_type": "duplicate_activity",
                        "severity": "warning",
                        "message": (
                            f"Posible actividad duplicada: '{act['title']}' "
                            f"(páginas {activities[seen_keys[dedup_key]]['source_page']} y {act['source_page']})."
                        ),
                        "source_page": act["source_page"],
                        "details": {
                            "first_index": seen_keys[dedup_key],
                            "duplicate_index": idx,
                        },
                    }
                )
            else:
                seen_keys[dedup_key] = idx

            weight = act.get("weight_percentage")
            if weight is not None:
                total_weight += float(weight)

            if act.get("due_date") is None:
                conflicts.append(
                    {
                        "activity_index": idx,
                        "conflict_type": "missing_due_date",
                        "severity": "info",
                        "message": (
                            f"La actividad '{act['title']}' no tiene fecha de entrega definida."
                        ),
                        "source_page": act["source_page"],
                        "details": {},
                    }
                )

        if total_weight > 100.01:
            conflicts.append(
                {
                    "conflict_type": "weight_overflow",
                    "severity": "warning",
                    "message": (
                        f"La suma de ponderaciones extraídas es {total_weight:.2f}%, "
                        "lo cual supera el 100%."
                    ),
                    "source_page": None,
                    "details": {"total_weight": round(total_weight, 2)},
                }
            )

        return {"conflicts": conflicts}

    def run(
        self, pdf_bytes: bytes, course_code: str, course_name: str
    ) -> dict[str, Any]:
        """Execute the LangGraph extraction pipeline synchronously for a PDF."""
        initial_state: ExtractionGraphState = {
            "pdf_bytes": pdf_bytes,
            "course_code": course_code,
            "course_name": course_name,
            "pages": [],
            "current_page_index": 0,
            "raw_extractions": [],
            "validated_activities": [],
            "conflicts": [],
            "deadline_monotonic": time.monotonic() + self._job_timeout_seconds,
        }
        # Estimate generous recursion limit for multi-page syllabi
        final_state = self._graph.invoke(
            initial_state,
            config={"recursion_limit": 50},
        )
        return {
            "total_pages": len(final_state.get("pages", [])),
            "activities": final_state.get("validated_activities", []),
            "conflicts": final_state.get("conflicts", []),
            "model_name": self._model_name,
        }
