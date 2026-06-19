from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from auth import hash_password, verify_password
from db import get_connection


class UserPublic(BaseModel):
    user_id: int
    user_name: str
    user_email: EmailStr
    daily_caloric_target: int | None
    created_at: datetime
    updated_at: datetime


class SignupRequest(BaseModel):
    user_name: str = Field(min_length=1, max_length=100)
    user_email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    daily_caloric_target: int | None = Field(default=None, ge=500, le=10000)


class LoginRequest(BaseModel):
    user_email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UpdateUserRequest(BaseModel):
    user_name: str | None = Field(default=None, min_length=1, max_length=100)
    daily_caloric_target: int | None = Field(default=None, ge=500, le=10000)
    password: str | None = Field(default=None, min_length=8, max_length=128)


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
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_user_by_id(user_id: int) -> UserPublic | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, user_name, user_email, daily_caloric_target,
                       created_at, updated_at
                FROM users
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
    return _row_to_user(row) if row else None


def get_user_by_email(user_email: str) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, user_name, user_email, user_password_hash,
                       daily_caloric_target, created_at, updated_at
                FROM users
                WHERE user_email = %s
                """,
                (user_email.lower(),),
            )
            return cur.fetchone()


def create_user(data: SignupRequest) -> UserPublic:
    password_hash = hash_password(data.password)
    email = data.user_email.lower()

    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO users (
                        user_name, user_email, user_password_hash, daily_caloric_target
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING user_id, user_name, user_email, daily_caloric_target,
                              created_at, updated_at
                    """,
                    (data.user_name.strip(), email, password_hash, data.daily_caloric_target),
                )
            except Exception as exc:
                if getattr(exc, "sqlstate", None) == "23505":
                    raise ValueError("An account with this email already exists") from exc
                raise
            row = cur.fetchone()
            conn.commit()

    return _row_to_user(row)


def authenticate_user(data: LoginRequest) -> UserPublic | None:
    row = get_user_by_email(data.user_email)
    if row is None:
        return None
    if not verify_password(data.password, row["user_password_hash"]):
        return None
    return _row_to_user(row)


def update_user(user_id: int, data: UpdateUserRequest) -> UserPublic | None:
    fields: list[str] = []
    values: list[object] = []

    if data.user_name is not None:
        fields.append("user_name = %s")
        values.append(data.user_name.strip())
    if data.daily_caloric_target is not None:
        fields.append("daily_caloric_target = %s")
        values.append(data.daily_caloric_target)
    if data.password is not None:
        fields.append("user_password_hash = %s")
        values.append(hash_password(data.password))

    if not fields:
        return get_user_by_id(user_id)

    values.append(user_id)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE users
                SET {", ".join(fields)}
                WHERE user_id = %s
                RETURNING user_id, user_name, user_email, daily_caloric_target,
                          created_at, updated_at
                """,
                values,
            )
            row = cur.fetchone()
            conn.commit()

    return _row_to_user(row) if row else None
