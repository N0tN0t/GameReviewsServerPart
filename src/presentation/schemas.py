from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterSchema(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginSchema(BaseModel):
    email: EmailStr
    password: str


class TokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GameCreateSchema(BaseModel):
    slug: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    developer: str = Field(min_length=1, max_length=150)
    release_date: date | None = None
    genres: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)


class GameCardSchema(BaseModel):
    id: UUID
    slug: str
    title: str
    description: str
    developer: str
    release_date: date | None
    genres: list[str]
    platforms: list[str]
    raw_avg_rating: float
    bayesian_rating: float
    reviews_count: int
    under_review_bombing: bool


class ReviewUpsertSchema(BaseModel):
    rating: int = Field(ge=1, le=10)
    text: str = Field(min_length=20, max_length=5000)


class ReviewResponseSchema(BaseModel):
    id: UUID
    game_id: UUID
    user_id: UUID
    rating: int
    body: str
    status: str
    is_anomalous: bool
    helpful_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class VoteSchema(BaseModel):
    is_helpful: bool


class ModerationPatchSchema(BaseModel):
    status: Literal["approved", "pending_review", "rejected"]
    is_anomalous: bool = False
    reason: str = Field(default="manual_moderator_review", min_length=3, max_length=100)
