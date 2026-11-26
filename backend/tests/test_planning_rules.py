import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.domain.planning_rules import (
    PlanningActivity,
    StudyBlock,
    StudyWindow,
    validate_study_plan,
)


class PlanningRulesTest(unittest.TestCase):
    def test_rejects_overlap_and_after_deadline_and_reports_pending(self):
        start = datetime(2026, 11, 26, 14, tzinfo=timezone.utc)
        hour = timedelta(hours=1)
        activity = PlanningActivity(uuid4(), start + 2 * hour, 120)
        slot = StudyWindow(start, start + 3 * hour)
        valid = StudyBlock(activity.activity_id, StudyWindow(start, start + hour))
        overlapping = StudyBlock(
            activity.activity_id, StudyWindow(start + hour / 2, start + 2 * hour)
        )
        late = StudyBlock(
            activity.activity_id, StudyWindow(start + 2 * hour, start + 3 * hour)
        )
        blocks, pending = validate_study_plan([activity], [slot], slot, [late, overlapping, valid])
        self.assertEqual(blocks, [valid])
        self.assertEqual(pending, {activity.activity_id: "INSUFFICIENT_AVAILABILITY"})

    def test_full_assignment_has_no_pending_activity(self):
        start = datetime(2026, 11, 26, 14, tzinfo=timezone.utc)
        end = start + timedelta(minutes=30)
        activity = PlanningActivity(uuid4(), end, 30)
        slot = StudyWindow(start, end)
        block = StudyBlock(activity.activity_id, slot)
        self.assertEqual(validate_study_plan([activity], [slot], slot, [block]), ([block], {}))
