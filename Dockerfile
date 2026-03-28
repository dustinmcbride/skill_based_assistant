FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no editable install, no dev deps)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY . .

ENV PORT=5055
EXPOSE 5055

CMD ["uv", "run", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "5055"]
