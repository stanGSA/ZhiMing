# Hugging Face Spaces — Pure Offline Demo Container for ZhiMing (知命)
# Zero LLM API keys required: BaZi, Western Natal Chart, Kangxi Name Strokes,
# Daily Almanac, and deterministic Tarot Demo all run locally inside the container.
#
# Build from the repository root:
#   docker build -f deploy/hf-space/Dockerfile -t zhiming-hf-demo .
# Run locally on port 7860:
#   docker run --rm -p 7860:7860 zhiming-hf-demo

FROM ghcr.io/astral-sh/uv:0.13.0 AS uv-bin

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    HOME=/home/user \
    PATH="/home/user/app/.venv/bin:/usr/local/bin:$PATH"

COPY --from=uv-bin /uv /uvx /usr/local/bin/

# Hugging Face Spaces runs containers as non-root UID 1000.
RUN useradd -m -u 1000 user

WORKDIR /home/user/app

# 1. Install locked Python dependencies (web runtime only; no paid LLM SDK needed).
COPY --chown=user:user pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --extra web

# 2. Copy application source and static assets (preserving AGPL-3.0 LICENSE & NOTICE).
COPY --chown=user:user LICENSE NOTICE config.yaml app.py cli.py web.py ./
COPY --chown=user:user harness ./harness
COPY --chown=user:user agents ./agents
COPY --chown=user:user common ./common
COPY --chown=user:user plugins ./plugins
COPY --chown=user:user knowledge ./knowledge
COPY --chown=user:user memory ./memory
COPY --chown=user:user signals ./signals
COPY --chown=user:user scripts ./scripts
COPY --chown=user:user web_static ./web_static

# 3. Pre-fetch SHA256-verified ephemeris/GeoNames/Unihan data and build read-only SQLite KB.
RUN mkdir -p data runs && chown -R user:user /home/user/app
USER user

RUN uv run --no-sync python -m scripts.fetch_data \
    && uv run --no-sync python -m knowledge.build \
    && uv run --no-sync python -m scripts.doctor

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/healthz', timeout=3)" || exit 1

CMD ["python", "web.py", \
     "--host", "0.0.0.0", \
     "--port", "7860", \
     "--demo-only", \
     "--allow-host", "*.hf.space", \
     "--embed-ancestor", "https://huggingface.co", \
     "--embed-ancestor", "https://*.hf.space", \
     "--forwarded-allow-ips", "*"]
