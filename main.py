# ... (imports & config stay the same)

# --- NEW: simple keyword-based mode inference ---
def infer_mode(text: str) -> str:
    t = (text or "").lower()
    health_kw = ["health", "gut", "diet", "nutrition", "nutrient", "digest", "digestion",
                 "ibs", "microbiome", "food", "coriander", "cilantro", "herb", "spice"]
    tech_kw = ["code", "bug", "api", "deploy", "docker", "python", "javascript", "error", "stack trace"]
    # prioritize health if any match
    if any(k in t for k in health_kw):
        return "health"
    if any(k in t for k in tech_kw):
        return "technical"
    return "analytical"  # general analysis as safe default


def deterministic_enhance(raw: str, mode: str, tone: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    # --- UPDATED: better labels + new 'health' mode ---
    mode_hints = {
        "analytical": "You are a general analyst. Provide structured reasoning, assumptions, risks, and a decision rubric.",
        "technical":  "You are a senior software engineer. Provide step-by-step instructions, examples, edge cases, and complexity notes.",
        "creative":   "You are a creative editor. Provide voice, hook, narrative structure, and audience focus.",
        "health":     "You are a clinician/nutritionist. Provide evidence-aware advice, mechanisms of action, safety, contraindications, and practical guidance."
    }
    tone_hints = {
        "concise":     "Short, direct sentences. No filler.",
        "formal":      "Professional, precise, no slang.",
        "friendly":    "Warm, encouraging, and approachable.",
        "persuasive":  "Benefit-led framing with a soft CTA.",
        "neutral":     "Balanced, objective tone.",
    }

    # --- NEW: auto reroute to health/tech when user left default ---
    if mode not in mode_hints or mode == "auto":
        mode = infer_mode(raw)

    mh = mode_hints.get(mode, mode_hints["analytical"])
    th = tone_hints.get(tone, tone_hints["concise"])

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
- Keep within 250–400 words unless clinical nuance or citations are essential.

# Tone
- {tone.capitalize()}. {th}

# Output Format
- Use headings and bullet points when helpful.
- Conclude with a brief checklist/summary.

# Quality Checks
- Be evidence-aware; mention quality of evidence if applicable (e.g., RCTs vs observational).

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


async def openrouter_enhance(user_input: str, mode: str, tone: str) -> Dict[str, Any]:
    # ... (env/key checks same)

    # --- UPDATED: include health mapping and auto infer if needed ---
    if mode == "auto" or mode not in {"analytical", "technical", "creative", "health"}:
        mode = infer_mode(user_input)

    mode_hint = {
        "analytical": "Focus on analysis structure, assumptions, risks, decision criteria.",
        "technical":  "Focus on steps, examples, edge cases, and code-ready outputs.",
        "creative":   "Focus on voice, hooks, story structure, and audience fit.",
        "health":     "Focus on evidence-aware advice, safety, contraindications, and mechanisms of action.",
    }.get(mode, "Focus on clarity and structure.")

    tone_hint = {
        "concise":    "Short, direct sentences. Remove filler.",
        "formal":     "Professional, precise language.",
        "friendly":   "Warm and approachable, but clear.",
        "persuasive": "Benefit-first framing; conclude with a CTA.",
        "neutral":    "Informative and balanced."
    }.get(tone, "Keep it neutral and clear.")

    system = (
        "You are an expert prompt engineer. Transform the user's raw input into a complete, structured, high-signal prompt "
        "for a large language model. Preserve intent; add role, task, context, constraints, tone, output format, "
        "and quality checks when helpful. Return STRICT JSON as {\"enhanced\": string, \"improvements\": string[]}."
    )

    user = f"Mode: {mode} ({mode_hint})\nTone: {tone} ({tone_hint})\n\nUser Input:\n\"\"\"{user_input.strip()}\"\"\""

    # ... (httpx request/rotation/retry logic unchanged)


@app.post("/enhance", response_class=JSONResponse)
async def enhance(request: Request):
    if rate_limited(request):
        return JSONResponse({"error": "Too many requests, slow down."}, status_code=429)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body."}, status_code=400)

    user_input: str = (body.get("input") or "").strip()
    mode: str = (body.get("mode") or "auto").strip().lower()   # --- DEFAULT NOW 'auto'
    tone: str = (body.get("tone") or "concise").strip().lower()
    tier: str = (body.get("tier") or "free").strip().lower()

    if not user_input:
        return JSONResponse({"error": "input is required"}, status_code=400)

    # --- ensure mode is inferred when needed ---
    if mode == "auto" or mode not in {"analytical","technical","creative","health"}:
        mode = infer_mode(user_input)

    if tier == "free":
        COUNTERS["free_calls"] += 1
        return JSONResponse(deterministic_enhance(user_input, mode, tone))

    if tier == "pro":
        COUNTERS["pro_calls"] += 1
        try:
            obj = await openrouter_enhance(user_input, mode, tone)
            return JSONResponse(obj, status_code=200)
        except Exception as e:
            COUNTERS["fallback_uses"] += 1
            fb = deterministic_enhance(user_input, mode, tone)
            fb["note"] = f"Provider unavailable: {str(e)[:120]}"
            return JSONResponse(fb, status_code=200)

    return JSONResponse({"error": "unknown tier"}, status_code=400)
