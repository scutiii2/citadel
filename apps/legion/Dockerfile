# syntax=docker/dockerfile:1
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
WORKDIR /app

# Dependencies first so source edits do not reinstall them. Only the locked
# dependencies go into /opt/venv; the app runs from the /app source below.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
# Keep the public configs path while persisting admin edits in agent_data.
RUN ln -s /app/.data/admin_tuning_overrides.json /app/configs/tuning_overrides.json
EXPOSE 29603
CMD ["python", "-m", "src.supervisor"]
