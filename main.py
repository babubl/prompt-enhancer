import os
import time
import json
import ipaddress
from typing import Dict, Any, List, Optional

import httpx
from fastapi import FastAPI, Request, Response, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ------------ Config ------------

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
# Comma-separated model list overrideable via env
DEFAULT_MODELS = [
    # You can override via env: OPENROUTER_MODELS="deepseek/deepseek-r1:free,qwen/qwen2.5:free"
    "deepseek/deepseek-r1:free",
    "openai/gpt-oss-20b:free",
    "qwen/qwen2.5:free",
    "mistralai/mixtral-8x7b-instruct:free",
]
OPENROUTER_MODELS = [
    m.strip() for m in os.getenv("OPENROUTER_MODELS", ",".join(DEFAULT_MODELS)).split(",") if m.strip()
]

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30"))
RETRY_BACKOFFS = [0.5, 1.0, 2.0]  # seconds

# Simple per-IP rate limit (sliding window per minute)
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "30"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds

# CORS (allow your frontends)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# ------------ App ------------

app = FastAPI(title="PromptOS V2", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS] if ALLOWED_ORIGINS else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# In-memory counters (non-persistent; good enough for MVP)
COUNTERS = {
    "free_calls": 0,
    "pro_calls": 0,
    "fallback_uses": 0,
    "blocked_rate": 0,
    "since": int(time.time()),
}

# Very simple in-memory rate limiter
_IP_BUCKET: Dict[str, List[float]] = {}


def get_client_ip(request: Request) -> str:
    # Try X-Forwarded-For (Render/Proxies), fallback to client.host
    fwd = request.headers.get("x-forwarded-for", "") or request.client.host
    ip = fwd.split(",")[0].strip()
    # sanitize
    try:
        ipaddress.ip_address(ip)
    except Exception:
        ip = "0.0.0.0"
    return ip


def rate_limited(request: Request) -> bool:
    ip = get_client_ip(request)
    now = time.time()
    bucket = _IP_BUCKET.get(ip, [])
    # purge old
    bucket = [t for t in bucket if now - t < RATE_LIMIT_WINDOW]
    if len(bucket) >= RATE_LIMIT_MAX:
        _IP_BUCKET[ip] = bucket
        COUNTERS["blocked_rate"] += 1
        return True
    bucket.append(now)
    _IP_BUCKET[ip] = bucket
    return False


# ------------ Deterministic fallback (always returns) ------------

def deterministic_enhance(raw: str, mode: str, tone: str) -> Dict[str, Any]:
    # lightweight, non-AI rules to ensure a usable enhancement if providers fail
    raw = (raw or "").strip()
    mode_hints = {
        "analytical": "You are a business/finance analyst. Provide structured reasoning, assumptions, risks, and a decision rubric.",
        "technical": "You are a senior software engineer. Provide step-by-step instructions, examples, edge cases, and complexity notes.",
        "creative": "You are a creative editor. Provide voice, hook, narrative structure, and audience focus.",
    }
    tone_hints = {
        "concise": "Short, direct sentences. No filler.",
        "formal": "Professional, precise, no slang.",
        "friendly": "Warm, encouraging, and approachable.",
        "persuasive": "Benefit-led framing with a soft CTA.",
        "neutral": "Balanced, objective tone.",
    }
    mh = mode_hints.get(mode, mode_hints["analytical"])
    th = tone_hints.get(tone, tone_hints["concise"])

    # naive entity extraction
    import re
    toks = re.findall(r"[A-Za-z0-9\-]{3,}", raw)
    ents = ", ".join(sorted(set(toks)))[:300] or "N/A"

    enhanced = f"""# Role
{mh}

# Task
Write a clear, structured response that directly fulfills the user's intent.

# User Intent (verbatim)
\"\"\"{raw}\"\"\"

# Constraints
- Avoid hallucinations; if uncertain, explicitly state assumptions and ask up to 2 clarifying questions.
- Keep within 250–400 words unless code or calculations are essential.

# Tone
- {tone}. {th}

# Output Format
- Use headings and bullet points when helpful.
- Conclude with a brief checklist/summary.

# Quality Checks
- Provide factual care; show formulas, pseudocode, or steps when relevant.

# Context Hints
- Entities detected: {ents}
"""
    improvements = [
        f"Mode preset applied: {mode}",
        f"Tone guidance applied: {tone}",
        "Added structure: Role, Task, Intent, Constraints, Tone, Output, Checks",
        "Added anti-hallucination guidance & clarifying-question allowance",
        "Included naive entity/context hints",
    ]
    return {"enhanced": enhanced, "improvements": improvements, "model_used": "deterministic-fallback"}


# ------------ OpenRouter call w/ rotation & retries ------------

async def openrouter_enhance(user_input: str, mode: str, tone: str) -> Dict[str, Any]:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not configured")

    system = (
        "You are an expert prompt engineer. Transform the user's raw input into a complete, structured, high-signal prompt "
        "for a large language model. Preserve the user's intent; add role, task, context, constraints, tone, output format, "
        "and quality checks when helpful. Return STRICT JSON as {\"enhanced\": string, \"improvements\": string[]}."
    )
    mode_hint = {
        "analytical": "Focus on analysis structure, assumptions, risks, decision criteria.",
        "technical": "Focus on steps, examples, edge cases, and code-ready outputs.",
        "creative": "Focus on voice, hooks, story structure, and audience fit.",
    }.get(mode, "Focus on clarity and structure.")
    tone_hint = {
        "concise": "Short, direct sentences. Remove filler.",
        "formal": "Professional, precise language.",
        "friendly": "Warm and approachable, but clear.",
        "persuasive": "Benefit-first framing; conclude with a CTA.",
        "neutral": "Informative and balanced."
    }.get(tone, "Keep it neutral and clear.")

    user = f"Mode: {mode} ({mode_hint})\nTone: {tone} ({tone_hint})\n\nUser Input:\n\"\"\"{user_input.strip()}\"\"\""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        # Recommended headers per OpenRouter
        "HTTP-Referer": os.getenv("PUBLIC_URL", "https://example.com"),
        "X-Title": "PromptOS-Public",
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        last_error = None
        for model in OPENROUTER_MODELS:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            }
            for backoff in [0.0] + RETRY_BACKOFFS:
                if backoff:
                    await _sleep(backoff)
                try:
                    r = await client.post(OPENROUTER_BASE_URL, headers=headers, json=payload)
                    if r.status_code == 200:
                        data = r.json()
                        content = (
                            data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )
                        # Extract JSON strictly; tolerate wrappers
                        obj = None
                        try:
                            obj = json.loads(content)
                        except Exception:
                            import re
                            m = re.search(r"\{[\s\S]*\}", content)
                            if m:
                                try:
                                    obj = json.loads(m.group(0))
                                except Exception:
                                    obj = None
                        if not obj or "enhanced" not in obj:
                            raise ValueError("Non-JSON or invalid JSON from model")
                        obj["model_used"] = model
                        return obj
                    # Non-200 — store message & continue
                    last_error = f"{r.status_code} - {r.text[:200]}"
                    # 404/429/5xx rotate or retry
                    if r.status_code in (404, 409, 422, 429, 500, 502, 503, 504):
                        continue
                except Exception as e:
                    last_error = str(e)
                    continue
        raise RuntimeError(f"All model attempts failed. Last error: {last_error}")


async def _sleep(seconds: float):
    # Tiny awaitable sleep without importing asyncio at top-level
    import asyncio
    await asyncio.sleep(seconds)


# ------------ Routes ------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    # No prompt logging; we just render the template
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health", response_class=PlainTextResponse)
def health():
    return PlainTextResponse("ok", status_code=200)


@app.get("/metrics", response_class=JSONResponse)
def metrics():
    # minimal telemetry without storing prompt content
    return JSONResponse(COUNTERS)


@app.post("/enhance", response_class=JSONResponse)
async def enhance(request: Request):
    if rate_limited(request):
        return JSONResponse({"error": "Too many requests, slow down."}, status_code=429)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body."}, status_code=400)

    # Inputs (no server logging beyond this point)
    user_input: str = (body.get("input") or "").strip()
    mode: str = (body.get("mode") or "analytical").strip().lower()
    tone: str = (body.get("tone") or "concise").strip().lower()
    tier: str = (body.get("tier") or "free").strip().lower()  # "free" | "pro"

    if not user_input:
        return JSONResponse({"error": "input is required"}, status_code=400)

    # Free path -> deterministic (never fails)
    if tier == "free":
        COUNTERS["free_calls"] += 1
        return JSONResponse(deterministic_enhance(user_input, mode, tone))

    # Pro path -> OpenRouter rotation + fallback
    if tier == "pro":
        COUNTERS["pro_calls"] += 1
        try:
            obj = await openrouter_enhance(user_input, mode, tone)
            return JSONResponse(obj, status_code=200)
        except Exception as e:
            # Always fallback to deterministic to guarantee a result
            COUNTERS["fallback_uses"] += 1
            fallback = deterministic_enhance(user_input, mode, tone)
            fallback["note"] = f"Provider unavailable: {str(e)[:120]}"
            return JSONResponse(fallback, status_code=200)

    return JSONResponse({"error": "unknown tier"}, status_code=400)
