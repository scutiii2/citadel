# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Zima runs local classifiers on CPU. Install this before Laya so pip does
# not pull the default Linux torch wheel and its CUDA/Triton dependencies.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# Dependencies first so source edits do not reinstall them: install the
# project from a stub package, then drop the stub (the real src/ is copied
# below and wins on sys.path because the app runs from /app).
COPY pyproject.toml ./
RUN mkdir src && touch src/__init__.py     && pip install .     && pip uninstall -y ai-agent     && rm -rf src build
# Fail the build if dependency resolution ever replaces the CPU-only wheel.
RUN python -c "import torch; assert torch.version.cuda is None and torch.version.hip is None, 'Garrison requires CPU-only PyTorch'"

COPY . .
EXPOSE 9100
CMD ["python", "-m", "src.supervisor"]
