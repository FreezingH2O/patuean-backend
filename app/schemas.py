"""Pydantic models for the live web features (auth + Live Detector).

Everything serializes camelCase to match fe/src/services/types.ts. Phone-preview
types (calls, settings, family, etc.) live only in the frontend now.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

Role = Literal["elder", "guardian"]


class Schema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


# ---- Auth ----
class SignupPayload(Schema):
    name: str
    phone: str
    email: str


class LoginPayload(Schema):
    phone: Optional[str] = None
    email: Optional[str] = None


class RefreshPayload(Schema):
    refresh_token: Optional[str] = None


class User(Schema):
    id: str
    name: str
    phone: str
    email: str
    role: Role
    consent_recorded: bool


class AuthResponse(Schema):
    access_token: str
    refresh_token: Optional[str] = None
    user: User


class Ok(Schema):
    ok: Literal[True] = True


# ---- Live Detector ----
class LiveTestResponse(Schema):
    spoof_prob: float
    transcript: str
    summary: str
    intents: list[str]
    scam_prob: float
    reasons: list[str]
    latency_ms: int


class DetectorTestRecord(Schema):
    id: str
    spoof_prob: float
    scam_prob: float
    transcript: str
    summary: str
    intents: list[str]
    reasons: list[str]
    latency_ms: int
    created_at: str
