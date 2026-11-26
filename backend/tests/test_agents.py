import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pymupdf

from app.domain.exceptions import ExternalServiceError
from app.infrastructure.groq_principal import Delegation, GroqPrincipal
from app.domain.planning_rules import PlanningActivity, StudyWindow
from app.infrastructure.study_planning_graph import (
    ProposedBlockSchema,
    StudyPlanningPipeline,
    StudyPlanOutput,
)

from app.infrastructure.syllabus_extraction_graph import (
    ExtractedActivitySchema,
    PageExtractionOutput,
    SyllabusExtractionPipeline,
)


class PrincipalTest(unittest.TestCase):
    def test_accepts_authorized_route_and_rejects_wrong_specialist(self):
        with patch("app.infrastructure.groq_principal.ChatGroq") as groq:
            model = groq.return_value.with_structured_output.return_value
            principal = GroqPrincipal("test", "test")
            model.invoke.return_value = Delegation(subagent="documental")
            principal.delegate("documental")
            with self.assertRaises(ExternalServiceError):
                principal.delegate("planificador")
            self.assertEqual(model.invoke.call_count, 2)


class DocumentalTest(unittest.TestCase):
    @staticmethod
    def syllabus_pdf() -> bytes:
        with pymupdf.open() as pdf:
            for day in (18, 20):
                pdf.new_page().insert_text(
                    (54, 72),
                    f"Proyecto final: entrega el {day} de diciembre de 2026",
                )
            return pdf.tobytes()

    def test_conflicting_dates_keep_both_pages(self):
        with patch("app.infrastructure.syllabus_extraction_graph.ChatGroq") as groq:
            llm = groq.return_value.with_structured_output.return_value
            llm.invoke.side_effect = [
                PageExtractionOutput(activities=[
                    ExtractedActivitySchema(
                        title="Proyecto final", activity_type="project",
                        due_date=f"{day} de diciembre de 2026",
                        evidence_quote=f"Proyecto final: entrega el {day} de diciembre de 2026",
                    )
                ])
                for day in (18, 20)
            ]
            result = SyllabusExtractionPipeline("test", "test").run(
                self.syllabus_pdf(), "ARQ", "Arquitectura"
            )
        self.assertEqual([a["source_page"] for a in result["activities"]], [1, 2])
        self.assertTrue(all(a["evidence_valid"] for a in result["activities"]))
        self.assertIn("contradictory_due_dates", {c["conflict_type"] for c in result["conflicts"]})

    def test_provider_failure_is_reported_as_extraction_error(self):
        with patch("app.infrastructure.syllabus_extraction_graph.ChatGroq") as groq:
            groq.return_value.with_structured_output.return_value.invoke.side_effect = TimeoutError
            with self.assertRaises(ExternalServiceError):
                SyllabusExtractionPipeline("test", "test").run(
                    self.syllabus_pdf(), "ARQ", "Arquitectura"
                )
        self.assertEqual(groq.call_args.kwargs["max_retries"], 1)


class PlannerTest(unittest.TestCase):
    def test_graph_validates_provider_blocks(self):
        start = datetime(2026, 12, 15, 14, tzinfo=timezone.utc)
        end = start + timedelta(hours=1)
        item = PlanningActivity(uuid4(), end, 90)
        slot = StudyWindow(start, end)
        with patch("app.infrastructure.study_planning_graph.ChatGroq") as groq:
            llm = groq.return_value.with_structured_output.return_value
            llm.invoke.return_value = StudyPlanOutput(
                summary="Bloque de estudio",
                blocks=[
                    ProposedBlockSchema(
                        activity_id=str(item.activity_id),
                        start_at=start.isoformat(),
                        end_at=proposed_end.isoformat(),
                    )
                    for proposed_end in (end, end + timedelta(minutes=30))
                ],
            )
            result = StudyPlanningPipeline("test", "test").run(
                activities=[item], availability=[slot], horizon=slot
            )
        self.assertEqual(len(result["accepted_blocks"]), 1)
        self.assertEqual(result["pending"], {item.activity_id: "INSUFFICIENT_AVAILABILITY"})
