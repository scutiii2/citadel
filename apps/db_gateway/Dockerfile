# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Dependencies first so source edits do not reinstall them: install the
# project from a stub package, then drop the stub (the real src/ is copied
# below and wins on sys.path because the app runs from /app).
COPY pyproject.toml ./
RUN mkdir src && touch src/__init__.py     && pip install .     && pip uninstall -y db-gateway     && rm -rf src build

COPY . .
EXPOSE 8071
CMD ["python", "-m", "src.run"]
