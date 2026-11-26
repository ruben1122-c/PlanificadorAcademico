from fastapi import APIRouter, Depends

from app.api.dependencies import get_auth_service, get_current_user
from app.api.schemas import LoginRequest, LoginResponse, UserResponse
from app.application.auth_service import AuthService
from app.domain.models import AuthenticatedUser

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    """Authenticate a user via Supabase Auth and return session tokens."""
    session = auth_service.login(email=payload.email, password=payload.password)
    return LoginResponse.model_validate(session)


@router.get("/me", response_model=UserResponse)
def read_current_user(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UserResponse:
    """Return the authenticated user verified against Supabase Auth."""
    return UserResponse.model_validate(current_user)
