"""Orchestrates the three detection models into one LiveTestResponse.

webm/upload -> WAV (once) -> anti-spoof + ASR concurrently -> LLM on the transcript.
"""

import asyncio
import time

from app.detectors import antispoof, asr, intent
from app.detectors.audio import to_wav
from app.schemas import LiveTestResponse


async def run_full_analysis(audio_bytes: bytes, lang: str = "en-US") -> LiveTestResponse:
    started = time.perf_counter()

    # Normalize whatever the browser/user uploaded to 16 kHz mono WAV.
    wav = await asyncio.to_thread(to_wav, audio_bytes)

    # Anti-spoof and ASR are independent — run them together.
    spoof_prob, transcript = await asyncio.gather(
        antispoof.spoof_probability(wav),
        asr.transcribe(wav, lang),
    )

    # Intent needs the transcript. Skip the LLM on empty/no-speech audio so silence
    # never gets hallucinated into a scam.
    if transcript.strip():
        intent_result = await intent.analyze(transcript)
    else:
        intent_result = {
            "summary": "No speech was detected in the audio.",
            "intents": ["none"],
            "scamProb": 0.0,
            "reasons": ["No speech detected to analyze."],
        }

    latency_ms = int((time.perf_counter() - started) * 1000)
    return LiveTestResponse(
        spoof_prob=round(float(spoof_prob), 1),
        transcript=transcript,
        summary=intent_result["summary"],
        intents=intent_result["intents"],
        scam_prob=round(float(intent_result["scamProb"]), 1),
        reasons=intent_result["reasons"],
        latency_ms=latency_ms,
    )
