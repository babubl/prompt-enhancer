# 🧠 Prompt Enhancer (Flask)

A tiny web app that takes a raw user query and returns an **enhanced, structured prompt** that LLMs follow better.

## Quick start (local)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set OPENAI_API_KEY
python app.py
