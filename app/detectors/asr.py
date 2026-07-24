"""ASR adapter — Typhoon ASR (OpenAI-compatible transcriptions endpoint).

Real API:
  POST {ASR_API_URL}   (e.g. https://api.opentyphoon.ai/v1/audio/transcriptions)
  headers: Authorization: Bearer {ASR_API_KEY}
  multipart: file=<wav>, model={ASR_MODEL}
  response: {"text": "...", "usage": {...}}
"""

import httpx

from app.config import get_settings

settings = get_settings()


async def _call_real(wav_bytes: bytes) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            settings.asr_api_url,
            headers={"Authorization": f"Bearer {settings.asr_api_key}"},
            files={"file": ("clip.wav", wav_bytes, "audio/wav")},
            data={"model": settings.asr_model},
        )
        resp.raise_for_status()
        return str(resp.json().get("text", "")).strip()


def _stub(lang: str) -> str:
    if lang.startswith("th"):
        return "สวัสดีครับ ผมโทรมาจากธนาคาร กรุณาแจ้งรหัส OTP เพื่อยืนยันตัวตน"
    return (
        "Hello, I'm calling from your bank's security department. We've detected a "
        "suspicious transaction. Please read me the one-time passcode to verify your identity."
    )


async def transcribe(wav_bytes: bytes, lang: str = "en-US") -> str:
    if not settings.asr_api_url:
        return _stub(lang)
    return await _call_real(wav_bytes)
