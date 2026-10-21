# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Video/audio downloads use FFmpeg and FFprobe for local post-processing.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so source edits do not reinstall them: install the
# project from a stub package, then drop the stub (the real src/ is copied
# below and wins on sys.path because the app runs from /app).
COPY pyproject.toml ./
RUN mkdir src && touch src/__init__.py     && pip install .     && pip uninstall -y mcp_server     && rm -rf src build

COPY . .
EXPOSE 8010
CMD ["python", "-m", "src.run"]
