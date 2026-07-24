"""Contract tests for the live web features (auth + Live Detector).

Run:  .venv/bin/python -m pytest  (from be/)
Uses a throwaway SQLite file and forces detector stubs (no network).
"""

import io
import os
import tempfile
import wave

import pytest

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["ANON_LIVE_TEST_LIMIT"] = "3"
os.environ["ANTISPOOF_API_URL"] = ""
os.environ["ASR_API_URL"] = ""
os.environ["LLM_API_URL"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)


def _tiny_wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)
    return buf.getvalue()


def _signup(phone="+66 90 000 0000", email="a@b.co"):
    r = client.post("/auth/signup", json={"name": "A", "phone": phone, "email": email})
    assert r.status_code == 200, r.text
    return r.json()


def test_signup_returns_camelcase_session():
    body = _signup()
    assert "accessToken" in body and "user" in body
    assert body["user"]["consentRecorded"] is False
    assert body["user"]["role"] == "elder"


def test_signup_duplicate_conflicts():
    _signup(phone="+66 90 000 0009", email="dup@b.co")
    r = client.post("/auth/signup", json={"name": "A", "phone": "+66 90 000 0009", "email": "dup@b.co"})
    assert r.status_code == 409


def test_login_unknown_is_404_detail():
    r = client.post("/auth/login", json={"email": "missing@nope.co"})
    assert r.status_code == 404
    assert r.json()["detail"] == "No account found with those details."


def test_login_by_phone_or_email():
    _signup(phone="+66 90 000 0001", email="login@b.co")
    assert client.post("/auth/login", json={"phone": "+66 90 000 0001"}).status_code == 200
    assert client.post("/auth/login", json={"email": "login@b.co"}).status_code == 200


def test_refresh_rotation():
    body = _signup(phone="+66 90 000 0002", email="ref@b.co")
    r = client.post("/auth/refresh", json={"refreshToken": body["refreshToken"]})
    assert r.status_code == 200 and r.json()["accessToken"]
    # Old token now revoked.
    assert client.post("/auth/refresh", json={"refreshToken": body["refreshToken"]}).status_code == 401


def test_live_test_returns_all_fields():
    # Authenticated so it doesn't consume the anonymous rate-limit quota.
    tok = _signup(phone="+66 90 000 0003", email="lt@b.co")["accessToken"]
    files = {"audio": ("clip.wav", _tiny_wav(), "audio/wav")}
    r = client.post("/demo/live-test", files=files, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("spoofProb", "transcript", "summary", "intents", "scamProb", "reasons", "latencyMs"):
        assert key in body


def test_live_test_anon_rate_limit():
    files = {"audio": ("clip.wav", _tiny_wav(), "audio/wav")}
    codes = [client.post("/demo/live-test", files=files).status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429


def test_detector_history_saves_lists_and_deletes():
    tok = _signup(phone="+66 90 000 0004", email="hist@b.co")["accessToken"]
    hdr = {"Authorization": f"Bearer {tok}"}
    files = {"audio": ("clip.wav", _tiny_wav(), "audio/wav")}

    # Authenticated live-test auto-saves to history.
    assert client.post("/demo/live-test", files=files, headers=hdr).status_code == 200
    listed = client.get("/me/detector-tests", headers=hdr).json()
    assert len(listed) == 1
    rec = listed[0]
    for key in ("id", "spoofProb", "scamProb", "transcript", "summary", "intents", "reasons", "createdAt"):
        assert key in rec

    # View one, then delete it.
    assert client.get(f"/me/detector-tests/{rec['id']}", headers=hdr).status_code == 200
    assert client.delete(f"/me/detector-tests/{rec['id']}", headers=hdr).status_code == 200
    assert client.get("/me/detector-tests", headers=hdr).json() == []


def test_detector_history_requires_auth():
    assert client.get("/me/detector-tests").status_code == 401


def test_anon_live_test_not_saved_to_history():
    # An anonymous test must not create any history rows (nothing to list without auth,
    # and a fresh account sees an empty history).
    files = {"audio": ("clip.wav", _tiny_wav(), "audio/wav")}
    client.post("/demo/live-test", files=files)  # anonymous
    tok = _signup(phone="+66 90 000 0005", email="fresh@b.co")["accessToken"]
    assert client.get("/me/detector-tests", headers={"Authorization": f"Bearer {tok}"}).json() == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
