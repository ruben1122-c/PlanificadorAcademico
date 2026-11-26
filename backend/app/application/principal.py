from typing import Literal, Protocol

Workflow = Literal["documental", "planificador"]


class Principal(Protocol):
    def delegate(self, workflow: Workflow) -> None: ...
