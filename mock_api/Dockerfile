# syntax=docker/dockerfile:1
# Container for the Training Mock API. Replace the <PLACEHOLDERS> first (see ../PLACEHOLDERS.md).
#   <PYTHON_IMAGE_TAG>, <PYTHON_IMAGE_DIGEST>, <UV_IMAGE_TAG>
FROM python:<PYTHON_IMAGE_TAG>@sha256:<PYTHON_IMAGE_DIGEST>

# uv installs the libraries from uv.lock (run `uv lock` once and commit the file).
COPY --from=ghcr.io/astral-sh/uv:<UV_IMAGE_TAG> /uv /bin/uv

RUN useradd --create-home --uid 1000 --shell /bin/sh appuser
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY app.py ./
ENV PATH="/app/.venv/bin:$PATH" MOCK_VARIANT=1
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
