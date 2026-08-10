from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.modules.users.errors import (
    InvalidCredentialsError,
    UserEmailConflictError,
    UserInactiveError,
    UserNotFoundError,
    UserUsernameConflictError,
)
from app.modules.users.public_api import user_public_api
from app.modules.users.schemas import (
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.shared.errors import ConflictError, DomainError, NotFoundError, UnauthorizedError
from app.shared.rate_limiter import limiter
from app.shared.security import get_current_user_id

router = APIRouter(prefix="/users", tags=["Users"])


def _map_user_error(err: DomainError) -> HTTPException:
    """Map domain errors to HTTP responses — presentation layer concern only."""
    if isinstance(err, (UserNotFoundError, NotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err.as_detail())
    if isinstance(err, (UserEmailConflictError, UserUsernameConflictError, ConflictError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err.as_detail())
    if isinstance(err, (InvalidCredentialsError, UserInactiveError, UnauthorizedError)):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err.as_detail())
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.as_detail())


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "Email or username already taken"},
        500: {"description": "Internal server error"},
    },
    summary="Register a new user",
)
@limiter.limit("10/minute")
async def register(request: Request, body: UserRegisterRequest) -> UserResponse:
    result = await user_public_api.register_user(body)
    if result.is_err():
        raise _map_user_error(result.err())
    return UserResponse.model_validate(result.ok())


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"description": "Invalid credentials"},
        500: {"description": "Internal server error"},
    },
    summary="Authenticate and receive a JWT",
)
@limiter.limit("20/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    # OAuth2PasswordRequestForm uses `username` field — we treat it as email
    result = await user_public_api.authenticate_user(form_data.username, form_data.password)
    if result.is_err():
        raise _map_user_error(result.err())
    return TokenResponse(access_token=result.ok())


@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"},
    },
    summary="Get current authenticated user",
)
async def get_me(current_user_id: int = Depends(get_current_user_id)) -> UserResponse:
    result = await user_public_api.get_user_by_id(current_user_id)
    if result.is_err():
        raise _map_user_error(result.err())
    return UserResponse.model_validate(result.ok())


@router.get(
    "/",
    response_model=list[UserResponse],
    responses={
        401: {"description": "Not authenticated"},
        500: {"description": "Internal server error"},
    },
    summary="List all users (authenticated)",
)
async def list_users(
    _: int = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=100, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
) -> list[UserResponse]:
    result = await user_public_api.get_all_users(limit=limit, offset=offset)
    if result.is_err():
        raise _map_user_error(result.err())
    return [UserResponse.model_validate(u) for u in result.ok()]


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"},
    },
    summary="Get a user by ID",
)
async def get_user(user_id: int, _: int = Depends(get_current_user_id)) -> UserResponse:
    result = await user_public_api.get_user_by_id(user_id)
    if result.is_err():
        raise _map_user_error(result.err())
    return UserResponse.model_validate(result.ok())


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "User not found"},
        409: {"description": "Username already taken"},
        500: {"description": "Internal server error"},
    },
    summary="Update a user",
)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    current_user_id: int = Depends(get_current_user_id),
) -> UserResponse:
    result = await user_public_api.update_user(user_id, body)
    if result.is_err():
        raise _map_user_error(result.err())
    return UserResponse.model_validate(result.ok())


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"},
    },
    summary="Delete a user",
)
async def delete_user(user_id: int, _: int = Depends(get_current_user_id)) -> None:
    result = await user_public_api.delete_user(user_id)
    if result.is_err():
        raise _map_user_error(result.err())
