"""Anti-spoof adapter — returns P(voice is AI-synthesized) as 0..100.

Real API (AWS API Gateway):
  POST {ANTISPOOF_API_URL}
  headers: x-api-key, Content-Type: audio/wav
  body: raw WAV bytes
  response: {"prediction": "spoof"|"bona_fide", "score": <float>, "is_bona_fide": <bool>}

The `score` is a raw logit: above the decision threshold => bona_fide (real),
below => spoof (fake). We calibrate it with a temperature-scaled sigmoid around the
threshold, then report P(spoof) as 0..100 (higher = more likely fake):

  p_real = 1 / (1 + exp(-(score - 6.19) / 1.86))   # confidence the voice is real
  spoofProb = (1 - p_real) * 100                    # so the UI's "real voice %" == p_real*100
"""

import hashlib
import math

import httpx

from app.config import get_settings

settings = get_settings()

# Calibration of the anti-spoof logit (provided by the model owner).
SPOOF_THRESHOLD = 6.19   # score above this = real (bona_fide); below = fake (spoof)
SPOOF_TEMPERATURE = 1.86


def score_to_spoof_prob(score: float) -> float:
    """Map the raw anti-spoof logit to P(spoof) as a 0..100 percentage."""
    z = (score - SPOOF_THRESHOLD) / SPOOF_TEMPERATURE
    # p_real = sigmoid(z); clamp z to avoid math.exp overflow on extreme scores.
    if z >= 60:
        p_real = 1.0
    elif z <= -60:
        p_real = 0.0
    else:
        p_real = 1.0 / (1.0 + math.exp(-z))
    return float(round((1.0 - p_real) * 100))


async def _call_real(wav_bytes: bytes) -> float:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            settings.antispoof_api_url,
            headers={"x-api-key": settings.antispoof_api_key, "Content-Type": "audio/wav"},
            content=wav_bytes,
        )
        resp.raise_for_status()
        data = resp.json()
    if "score" in data and data["score"] is not None:
        return score_to_spoof_prob(float(data["score"]))
    # Fallback if score is absent: use the boolean verdict.
    return 5.0 if data.get("is_bona_fide") else 95.0


def _stub(audio_bytes: bytes) -> float:
    h = int(hashlib.sha256(audio_bytes).hexdigest(), 16)
    return round((h % 10000) / 100, 1)


async def spoof_probability(wav_bytes: bytes) -> float:
    if not settings.antispoof_api_url:
        return _stub(wav_bytes)
    return await _call_real(wav_bytes)
