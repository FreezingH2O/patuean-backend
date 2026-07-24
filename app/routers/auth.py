from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User
from app.schemas import AuthResponse, LoginPayload, RefreshPayload, SignupPayload
from app.schemas import User as UserSchema
from app.security import (
    REFRESH_COOKIE,
    create_access_token,
    issue_refresh_token,
    new_id,
    read_refresh_cookie,
    rotate_refresh_token,
)

# NOTE (prototype): auth is identity-only (name/phone/email, no password or OTP).
# TODO production: add verification (OTP/email) before issuing a session.

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
        max_age=settings.refresh_token_ttl_days * 86400,
    )


def _session(db: Session, response: Response, user: User) -> AuthResponse:
    access = create_access_token(user.id)
    refresh = issue_refresh_token(db, user.id)
    _set_refresh_cookie(response, refresh)
    return AuthResponse(
        access_token=access, refresh_token=refresh, user=UserSchema.model_validate(user)
    )


@router.post("/signup", response_model=AuthResponse, response_model_by_alias=True)
def signup(payload: SignupPayload, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    exists = (
        db.query(User)
        .filter((User.phone == payload.phone) | (User.email == payload.email))
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="An account with that phone or email already exists.")
    user = User(
        id=new_id("u"),
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        role="elder",
        consent_recorded=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _session(db, response, user)


@router.post("/login", response_model=AuthResponse, response_model_by_alias=True)
def login(payload: LoginPayload, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    if not payload.phone and not payload.email:
        raise HTTPException(status_code=400, detail="Provide a phone or email.")
    query = db.query(User)
    user = None
    if payload.phone:
        user = query.filter(User.phone == payload.phone).first()
    if user is None and payload.email:
        user = db.query(User).filter(User.email == payload.email).first()
    if user is None:
        raise HTTPException(status_code=404, detail="No account found with those details.")
    return _session(db, response, user)


@router.post("/refresh", response_model=AuthResponse, response_model_by_alias=True)
def refresh(
    payload: RefreshPayload,
    response: Response,
    db: Session = Depends(get_db),
    cookie_token: str | None = Depends(read_refresh_cookie),
) -> AuthResponse:
    token = payload.refresh_token or cookie_token
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token provided.")
    rotated = rotate_refresh_token(db, token)
    if rotated is None:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    user_id, new_token = rotated
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account not found.")
    _set_refresh_cookie(response, new_token)
    return AuthResponse(
        access_token=create_access_token(user_id),
        refresh_token=new_token,
        user=UserSchema.model_validate(user),
    )
