from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DetectorTest, User
from app.schemas import DetectorTestRecord, LiveTestResponse, Ok
from app.security import get_current_user, new_id

router = APIRouter(prefix="/me", tags=["detector-history"])


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _out(t: DetectorTest) -> DetectorTestRecord:
    return DetectorTestRecord(
        id=t.id,
        spoof_prob=t.spoof_prob,
        scam_prob=t.scam_prob,
        transcript=t.transcript,
        summary=t.summary,
        intents=t.intents or [],
        reasons=t.reasons or [],
        latency_ms=t.latency_ms,
        created_at=_iso(t.created_at),
    )


def save_detector_test(db: Session, user_id: str, result: LiveTestResponse) -> DetectorTest:
    """Persist a Live Detector result to a user's history (called on live-test)."""
    row = DetectorTest(
        id=new_id("dt"),
        user_id=user_id,
        spoof_prob=result.spoof_prob,
        scam_prob=result.scam_prob,
        transcript=result.transcript,
        summary=result.summary,
        intents=result.intents,
        reasons=result.reasons,
        latency_ms=result.latency_ms,
    )
    db.add(row)
    db.commit()
    return row


@router.get("/detector-tests", response_model=list[DetectorTestRecord], response_model_by_alias=True)
def list_detector_tests(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[DetectorTestRecord]:
    rows = (
        db.query(DetectorTest)
        .filter(DetectorTest.user_id == user.id)
        .order_by(desc(DetectorTest.created_at))
        .all()
    )
    return [_out(r) for r in rows]


@router.get("/detector-tests/{test_id}", response_model=DetectorTestRecord, response_model_by_alias=True)
def get_detector_test(
    test_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DetectorTestRecord:
    row = db.get(DetectorTest, test_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Test not found.")
    return _out(row)


@router.delete("/detector-tests/{test_id}", response_model=Ok, response_model_by_alias=True)
def delete_detector_test(
    test_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Ok:
    row = db.get(DetectorTest, test_id)
    if row is not None and row.user_id == user.id:
        db.delete(row)
        db.commit()
    return Ok()
