from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class StudyWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.utcoffset() is None or self.end.utcoffset() is None:
            raise ValueError("El intervalo requiere zona horaria.")
        if self.start >= self.end:
            raise ValueError("El inicio debe ser anterior al fin.")

    def contains(self, other: "StudyWindow") -> bool:
        return self.start <= other.start and other.end <= self.end


@dataclass(frozen=True)
class PlanningActivity:
    activity_id: UUID
    due_at: datetime
    estimated_minutes: int


@dataclass(frozen=True)
class StudyBlock:
    activity_id: UUID
    window: StudyWindow


def validate_study_plan(
    activities: list[PlanningActivity],
    availability: list[StudyWindow],
    horizon: StudyWindow,
    proposed_blocks: list[StudyBlock],
) -> tuple[list[StudyBlock], dict[UUID, str]]:
    """Accept only valid blocks and identify activities still needing study time."""
    by_id = {activity.activity_id: activity for activity in activities}
    assigned = dict.fromkeys(by_id, 0.0)
    accepted: list[StudyBlock] = []
    for block in sorted(proposed_blocks, key=lambda item: item.window.start):
        activity = by_id.get(block.activity_id)
        window = block.window
        if activity is None or window.end > activity.due_at or not horizon.contains(window):
            continue
        if not any(slot.contains(window) for slot in availability):
            continue
        if accepted and window.start < accepted[-1].window.end:
            continue
        minutes = (window.end - window.start).total_seconds() / 60
        if assigned[block.activity_id] + minutes > activity.estimated_minutes:
            continue
        accepted.append(block)
        assigned[block.activity_id] += minutes

    pending = {
        activity.activity_id: "INSUFFICIENT_AVAILABILITY"
        for activity in activities
        if assigned[activity.activity_id] < activity.estimated_minutes
    }
    return accepted, pending
