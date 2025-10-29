import os, json, logging
from flask import Flask, request, jsonify, render_template
from openai import OpenAI

# ---------- App setup ----------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["JSON_AS_ASCII"] = False

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("prompt-enhancer")

# ---------- Keys & client (OpenRouter) ----------
# IMPORTANT: set this in Render as an environment variable
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    log.warning("OPENROUTER_API_KEY is not set. '/' will work, but '/enhance' will 500.")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# ---------- System prompt ----------
SYSTEM_PROMPT = """You are an expert prompt engineer and instruction optimizer.
Transform a user's raw input into a complete, structured prompt for a large language model.
Rules:
- Preserve user intent; do NOT change the ask.
- Add role, task, context, constraints, output format, and quality checks when useful.
- Keep concise but explicit; avoid fluff.
Return JSON with keys:
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
    # Input validation
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

    try:
        # Use a free model on OpenRouter for zero-cost prototyping
        # You can swap to any other :free model later if you hit limits.
        resp = client.chat.completions.create(
            model="deepseek/deepseek-chat:free",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
            # Optional attribution headers for OpenRouter best practices:
            extra_headers={
                "HTTP-Referer": request.host_url.rstrip("/"),  # e.g., https://your-app.onrender.com
                "X-Title": "Prompt Enhancer",
            },
        )

        content = resp.choices[0].message.content
        payload = json.loads(content) if content else {}
        enhanced = (payload.get("enhanced") or "").strip()
        improvements = payload.get("improvements") or []
        return jsonify({"enhanced": enhanced, "improvements": improvements}), 200

    except Exception as e:
        log.exception("Enhance failed")
        return jsonify({"error": f"Enhance failed: {e.__class__.__name__}: {e}"}), 500


if __name__ == "__main__":
    # Local run (Render will use Gunicorn/Procfile)
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
