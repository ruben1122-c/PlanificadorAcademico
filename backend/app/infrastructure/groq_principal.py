from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel

from app.application.principal import Workflow
from app.domain.exceptions import ExternalServiceError


class Delegation(BaseModel):
    subagent: Workflow


class GroqPrincipal:
    def __init__(self, api_key: str, model: str) -> None:
        self._model = ChatGroq(
            api_key=api_key, model=model, temperature=0, timeout=15, max_retries=1
        ).with_structured_output(Delegation)

    def delegate(self, workflow: Workflow) -> None:
        goal = (
            "Extraer actividades y evidencias por página de un sílabo."
            if workflow == "documental"
            else "Proponer bloques de estudio para actividades confirmadas."
        )
        try:
            decision = self._model.invoke([
                SystemMessage(content=(
                    "Eres el agente principal. Selecciona el especialista para el objetivo. "
                    "documental extrae actividades y evidencias de PDF. "
                    "planificador propone bloques de estudio para actividades confirmadas."
                )),
                HumanMessage(content=goal),
            ])
        except Exception as exc:
            raise ExternalServiceError("Falló la delegación del agente principal.") from exc
        if not isinstance(decision, Delegation) or decision.subagent != workflow:
            raise ExternalServiceError("La delegación no coincide con la operación autorizada.")
