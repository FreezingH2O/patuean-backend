from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.detectors.pipeline import run_full_analysis
from app.models import AnonLiveTest, User
from app.routers.me import save_detector_test
from app.schemas import LiveTestResponse
from app.security import get_optional_user

# The scripted demo scenarios/debriefs stay client-side (see fe/src/services/api.ts);
# the backend only serves the real Live Detector Test.

router = APIRouter(prefix="/demo", tags=["demo"])
settings = get_settings()


def _client_ip(request: Request) -> str:
    # Behind Vercel/proxies the real client IP is the first X-Forwarded-For entry.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_anon_limit(db: Session, ip: str) -> None:
    row = db.get(AnonLiveTest, ip)
    if row is None:
        row = AnonLiveTest(ip=ip, count=0)
        db.add(row)
    if row.count >= settings.anon_live_test_limit:
        raise HTTPException(status_code=429, detail="Sign up to keep testing.")
    row.count += 1
    db.commit()


@router.post("/live-test", response_model=LiveTestResponse, response_model_by_alias=True)
async def live_test(
    request: Request,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> LiveTestResponse:
    if user is None:
        _enforce_anon_limit(db, _client_ip(request))

    # ASR auto-detects language; the hint only matters to the stub fallback.
    lang = "th-TH"

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio upload.")
    result = await run_full_analysis(audio_bytes, lang)

    # Signed-in users get the result saved to their history (drives the home page).
    if user is not None:
        save_detector_test(db, user.id, result)
    return result
