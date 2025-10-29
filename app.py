import os, json, logging, time, random
from collections import deque
from flask import Flask, request, jsonify, render_template
from openai import OpenAI

# ---------- Flask setup ----------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["JSON_AS_ASCII"] = False

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("prompt-enhancer")

# ---------- OpenRouter client ----------
# Set this in Render > Environment: OPENROUTER_API_KEY = sk-or-...
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    log.warning("OPENROUTER_API_KEY is not set. '/' will work; '/enhance' will 500.")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# ---------- System Prompt ----------
SYSTEM_PROMPT = """You are an expert prompt engineer and instruction optimizer.
Transform the user's raw input into a complete, structured, high-signal prompt for a large language model.
Rules:
- Preserve the user's intent; do NOT change the ask.
- Add role, task, context, constraints, tone, output format, and quality checks when helpful.
- Be concise but explicit; avoid fluff.
Return STRICT JSON with keys:
- enhanced: string
- improvements: array of short bullets
"""

# ---------- Routes ----------
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/health", methods=["GET"])
def health():
    return "ok", 200

@app.route("/enhance", methods=["POST"])
def enhance():
    # ---- Parse input ----
    try:
        data = request.get_json(force=True, silent=False) or {}
    except Exception as e:
        log.exception("Invalid JSON body")
        return jsonify({"error": f"Invalid JSON body: {e}"}), 400

    user_input = (data.get("input") or "").strip()
    domain = (data.get("domain") or "auto").strip().lower()
    tone = (data.get("tone") or "auto").strip().lower()

    if not user_input:
        return jsonify({"error": "Missing 'input'"}), 400
    if not OPENROUTER_API_KEY:
        return jsonify({"error": "Server misconfigured: OPENROUTER_API_KEY not set"}), 500

    user_prompt = (
        f"Domain hint: {domain if domain != 'auto' else 'auto-detect'}.\n"
        f"Tone hint: {tone if tone != 'auto' else 'auto-select (clear, helpful)'}.\n"
        "User Input:\n"
        f"\"\"\"{user_input}\"\"\""
    )

    # ---- Simple in-memory rate limit: 10 req/min per instance ----
    # Prevents bursts that cause 429 on free pools
    if not hasattr(app, "recent_calls"):
        app.recent_calls = deque()
    now = time.time()
    window = 60
    limit = 10
    app.recent_calls.append(now)
    while app.recent_calls and now - app.recent_calls[0] > window:
        app.recent_calls.popleft()
    if len(app.recent_calls) > limit:
        return jsonify({
            "error": "Too many requests from this app right now. Please try again in a few seconds."
        }), 429

    # ---- Free model rotation (first is a steady default) ----
    free_models = [
        "openai/gpt-oss-20b:free",
        "qwen/qwen3-8b:free",
        "qwen/qwen3-coder:free",
        "deepseek/deepseek-r1-0528:free",
        "deepseek/deepseek-r1:free",
    ]

    last_err = None

    for model_id in free_models:
        for attempt in range(3):  # up to 3 retries per model on transient errors
            try:
                resp = client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                    # Optional attribution headers recommended by OpenRouter
                    extra_headers={
                        "HTTP-Referer": request.host_url.rstrip("/"),
                        "X-Title": "Prompt Enhancer",
                    },
                )

                content = resp.choices[0].message.content
                payload = json.loads(content) if content else {}
                enhanced = (payload.get("enhanced") or "").strip()
                improvements = payload.get("improvements") or []
                if not enhanced:
                    raise ValueError("Upstream returned empty/malformed JSON")

                return jsonify({
                    "enhanced": enhanced,
                    "improvements": improvements,
                    "model_used": model_id
                }), 200

            except Exception as e:
                msg = str(e)
                # Retry on free-pool saturation / transient errors
                transient = (
                    "429" in msg
                    or "rate" in msg.lower()
                    or "temporarily" in msg.lower()
                    or "timeout" in msg.lower()
                    or "5" == msg[:1]  # generic 5xx string-start
                )
                if transient and attempt < 2:
                    backoff = (2 ** attempt) + random.random()
                    log.warning(f"{model_id} attempt {attempt+1} -> {e}; retrying in {backoff:.2f}s")
                    time.sleep(backoff)
                    last_err = e
                    continue

                # If the route doesn’t exist (404), move to next model
                if "No endpoints found" in msg or "404" in msg:
                    log.warning(f"{model_id} not available: {e}")
                    last_err = e
                    break

                # Non-retryable; try next model
                log.exception(f"Non-retryable error on {model_id}")
                last_err = e
                break

    # Exhausted all models
    log.exception("All free models unavailable", exc_info=last_err)
    return jsonify({
        "error": "All free models are busy right now.",
        "hint": "Please try again in a minute — pools refill quickly."
    }), 503


if __name__ == "__main__":
    # Local dev only; Render will use Gunicorn/Procfile
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
