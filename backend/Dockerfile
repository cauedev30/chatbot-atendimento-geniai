# The backend service: python -m geniai on 0.0.0.0:8000. It migrates the database on start.
# One process, one worker (see the README, "Deploy notes"). Build context: backend/.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY geniai ./geniai
RUN pip install . && rm -rf build *.egg-info

# The FAQ file, for `python -m geniai.db.cli load-faq faq/faq.json` inside the container.
COPY faq ./faq

RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin geniai
USER geniai

ENV HOST=0.0.0.0 \
    PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/api/health\", timeout=4)"]

CMD ["python", "-m", "geniai"]
