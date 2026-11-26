import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_auth_service, get_course_service
from app.application.course_service import CourseService
from app.domain.models import AuthenticatedUser, Course
from app.main import app


class CourseAccessTest(unittest.TestCase):
    def test_cross_account_course_returns_404(self):
        alice, bob, course_id = uuid4(), uuid4(), uuid4()
        now = datetime.now(timezone.utc)
        course = Course(course_id, alice, "ARQ", "Arquitectura", None, None, None, now, now)

        class Auth:
            def get_current_user(self, token):
                return AuthenticatedUser(id={"alice": alice, "bob": bob}[token], email=f"{token}@example.com")

        class CourseRepository:
            def get_by_id_for_owner(self, course_id, owner_id):
                return course if (course.id, course.owner_id) == (course_id, owner_id) else None

        app.dependency_overrides[get_auth_service] = Auth
        app.dependency_overrides[get_course_service] = lambda: CourseService(CourseRepository())
        try:
            client = TestClient(app)
            self.assertEqual(client.get(f"/api/v1/courses/{course_id}").status_code, 401)
            self.assertEqual(client.get(
                f"/api/v1/courses/{course_id}", headers={"Authorization": "Bearer alice"}
            ).status_code, 200)
            response = client.get(
                f"/api/v1/courses/{course_id}", headers={"Authorization": "Bearer bob"}
            )
            self.assertEqual(response.status_code, 404)
        finally:
            app.dependency_overrides.clear()
