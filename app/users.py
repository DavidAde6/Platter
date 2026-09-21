"""User service: request/response models, password handling, transactions.

The SQL lives in repositories/users.py. This module owns the shapes the API
speaks and the rules that are not the database's job.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator

from auth import hash_password, verify_password
from repositories import users as users_repo
from repositories.base import tx


def _validate_timezone(value: str | None) -> str | None:
    """Reject anything Postgres will not accept as a time zone.

    This has to happen before the write, not after. v_meal_local_time does
    `created_at AT TIME ZONE users.timezone`, and Postgres raises on an
    unrecognised zone at query time -- so one bad row would break the meal
    list for that user with an error pointing at the view rather than at the
    value that caused it.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown time zone: {value!r}") from exc
    return value


class UserPublic(BaseModel):
    user_id: int
    user_name: str
    user_email: EmailStr
    daily_caloric_target: int | None
    timezone: str | None = None
    created_at: datetime
    updated_at: datetime


class SignupRequest(BaseModel):
    user_name: str = Field(min_length=1, max_length=100)
    user_email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    daily_caloric_target: int | None = Field(default=None, ge=500, le=10000)
    # The browser knows this (Intl.DateTimeFormat().resolvedOptions().timeZone),
    # and it is what makes meal-type inference work for photos whose EXIF
    # capture time was stripped -- the common case for web uploads.
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str | None) -> str | None:
        return _validate_timezone(value)


class LoginRequest(BaseModel):
    user_email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UpdateUserRequest(BaseModel):
    user_name: str | None = Field(default=None, min_length=1, max_length=100)
    daily_caloric_target: int | None = Field(default=None, ge=500, le=10000)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str | None) -> str | None:
        return _validate_timezone(value)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


def _row_to_user(row: dict) -> UserPublic:
    return UserPublic(
        user_id=row["user_id"],
        user_name=row["user_name"],
        user_email=row["user_email"],
        daily_caloric_target=row["daily_caloric_target"],
        timezone=row["timezone"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_user_by_id(user_id: int) -> UserPublic | None:
    with tx() as cur:
        row = users_repo.get_by_id(cur, user_id)
    return _row_to_user(row) if row else None


def create_user(data: SignupRequest) -> UserPublic:
    """Create a user. Raises ValueError if the email is taken.

    The repository translates the unique violation, so this layer never sees
    a psycopg error code.
    """
    with tx() as cur:
        row = users_repo.insert_user(
            cur,
            user_name=data.user_name,
            user_email=data.user_email,
            password_hash=hash_password(data.password),
            daily_caloric_target=data.daily_caloric_target,
            timezone=data.timezone,
        )
    return _row_to_user(row)


def authenticate_user(data: LoginRequest) -> UserPublic | None:
    with tx() as cur:
        row = users_repo.get_by_email_with_hash(cur, data.user_email)
    if row is None:
        return None
    if not verify_password(data.password, row["user_password_hash"]):
        return None
    return _row_to_user(row)


def update_user(user_id: int, data: UpdateUserRequest) -> UserPublic | None:
    """Apply whichever fields were supplied.

    Note that `timezone` cannot be cleared through this route: None means
    "not supplied", the same as every other field here. Clearing it needs an
    explicit sentinel, which nothing asks for yet.
    """
    changes: dict[str, object] = {}
    if data.user_name is not None:
        changes["user_name"] = data.user_name.strip()
    if data.daily_caloric_target is not None:
        changes["daily_caloric_target"] = data.daily_caloric_target
    if data.password is not None:
        changes["user_password_hash"] = hash_password(data.password)
    if data.timezone is not None:
        changes["timezone"] = data.timezone

    with tx() as cur:
        row = users_repo.update_user(cur, user_id, changes)
    return _row_to_user(row) if row else None
