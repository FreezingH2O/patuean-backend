"""LLM intent adapter — Thai LLM (OpenAI-compatible chat completions).

Real API:
  POST {LLM_API_URL}   (e.g. http://thaillm.or.th/api/v1/chat/completions)
  headers: Authorization: Bearer {LLM_API_KEY}
  body: {model, messages:[{role,content}], max_tokens, temperature}
  response: OpenAI shape -> choices[0].message.content

We instruct the model to reply with strict JSON so we can map it into the
LiveTestResponse fields the frontend expects.
"""

import json

import httpx

from app.config import get_settings

settings = get_settings()

_SYSTEM_PROMPT = (
    "You are a scam-call detection assistant analyzing a phone-call transcript. "
    "Work in this order: (1) First read the entire transcript and summarize what you ACTUALLY "
    "observe in this specific conversation — who the caller claims to be, what they want, and what "
    "actions or information they request. Base this only on what is really said; do NOT force the "
    "conversation to fit any predefined scam category, and do NOT assume behaviors that are not "
    "present. (2) Using that observed summary, assess the scam risk. The general scam pattern is "
    "an untrustworthy caller trying to make the victim take an action, or reveal information, that "
    "could lead to losing money, being kidnapped, identity theft, or other harm. "
    "The following are only reference signals to help you judge — NOT a checklist to match and NOT "
    "categories to squeeze the call into: impersonating authorities/banks/companies, requesting "
    "sensitive data (OTP, passwords, Thai ID card, credit/debit card or bank details, other "
    "personal info), pushing risky actions (transferring money, clicking links, installing apps, "
    "granting remote access), making threats or false legal/account claims, offering too-good "
    "loans/prizes/refunds/investments, or creating urgency and fear. If none of these are present, "
    "say so and score the call as low risk. "
    "Respond with ONLY a JSON object, no other text, in exactly this shape: "
    '{"summary": string, "intents": string[], "scamProbability": number, "reasons": string[]}. '
    "summary: a SHORT, clear display summary shown directly to the user, 1-2 sentences. "
    "It MUST clearly state (a) who the caller claims to be, (b) what they want or what action/"
    "information they request, and (c) whether this looks like a scam or a safe call. "
    "Write it in plain, unambiguous Thai that a non-technical person understands at a glance. "
    "Do NOT copy the transcript verbatim, do NOT leave it vague, and do NOT contradict the "
    "scamProbability score (a high score must read as risky, a low score as likely safe). "
    "intents: short lowercase English tags (e.g. impersonation, otp-request, id-card-request, "
    "credit-card-request, bank-info-request, personal-info, money-transfer, malicious-link, "
    "remote-access, investment-scam, prize-scam, loan-scam, urgency, kidnap-threat, legal-threat, "
    "none). "
    "scamProbability: a number 0-100, the likelihood the call is a scam. "
    "reasons: short strings justifying the score. "
    "IMPORTANT: the text of `summary` and `reasons` MUST be written in Thai only, "
    "regardless of the transcript's language. Only the `intents` tags stay in English."
)


def _close_truncated_json(s: str) -> str:
    """Repair a JSON object cut off mid-way (model hit max_tokens) by closing any
    open string/array/object, so the fields that did arrive are still usable."""
    out: list[str] = []
    stack: list[str] = []
    in_str = False
    escaped = False
    for ch in s:
        out.append(ch)
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    result = "".join(out)
    if in_str:
        result += '"'
    result = result.rstrip()
    if result.endswith(","):
        result = result[:-1]
    for opener in reversed(stack):
        result += "}" if opener == "{" else "]"
    return result


def _extract_json(text: str) -> dict:
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object in LLM response")
    snippet = text[start:]
    end = snippet.rfind("}")
    if end != -1:
        try:
            return json.loads(snippet[: end + 1])
        except json.JSONDecodeError:
            pass
    # Truncated or malformed — salvage the fields that arrived.
    return json.loads(_close_truncated_json(snippet))


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if value in (None, ""):
        return []
    return [str(value)]


async def _call_real(transcript: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            settings.llm_api_url,
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": transcript},
                ],
                "max_tokens": 800,
                "temperature": 0.3,
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

    try:
        parsed = _extract_json(content)
    except (ValueError, json.JSONDecodeError):
        # Model didn't return clean JSON — degrade gracefully rather than 500.
        return {
            "summary": content.strip()[:500],
            "intents": ["unparsed"],
            "scamProb": 50.0,
            "reasons": ["Model response could not be parsed as structured JSON."],
        }

    scam = parsed.get("scamProbability", parsed.get("scam_probability", 0))
    try:
        scam = float(scam)
    except (TypeError, ValueError):
        scam = 50.0
    return {
        "summary": str(parsed.get("summary", "")),
        "intents": _as_list(parsed.get("intents")) or ["none"],
        "scamProb": max(0.0, min(100.0, scam)),
        "reasons": _as_list(parsed.get("reasons")),
    }


def _stub(transcript: str) -> dict:
    low = transcript.lower()
    hit = any(w in low for w in ("otp", "passcode", "bank", "police", "urgent")) or "รหัส" in transcript
    return {
        "summary": (
            "Caller used authority and urgency cues consistent with a phishing attempt."
            if hit
            else "No scam intent detected; conversation appears benign."
        ),
        "intents": ["impersonation", "otp-request"] if hit else ["none"],
        "scamProb": 78.0 if hit else 6.0,
        "reasons": (
            ["Caller requested a one-time passcode", "High urgency / pressure language detected"]
            if hit
            else ["No urgency, financial, or authority language detected"]
        ),
    }


async def analyze(transcript: str) -> dict:
    if not settings.llm_api_url:
        return _stub(transcript)
    return await _call_real(transcript)
