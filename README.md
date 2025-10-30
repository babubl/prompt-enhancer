# PromptOS — V2 (FastAPI)

Privacy-first prompt enhancer with **Free (deterministic/local)** and **Pro (cloud LLM)** modes,
model rotation, retries, rate limiting, and no prompt logging.

## Env Vars

- `OPENROUTER_API_KEY` = your OpenRouter key (for Pro mode)
- `OPENROUTER_MODELS`  = optional CSV override (default includes several `:free` pools)
- `PUBLIC_URL`         = your site URL (used as Referer header)
- `ALLOWED_ORIGINS`    = CSV list for CORS (default `*`)
- `RATE_LIMIT_MAX`     = requests per window (default 30)
- `RATE_LIMIT_WINDOW`  = seconds (default 60)

## Local run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENROUTER_API_KEY=sk-or-...
uvicorn main:app --reload
