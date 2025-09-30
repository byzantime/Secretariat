# Use an official Python runtime as a parent image
FROM debian:testing-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential nodejs npm curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv using standalone installer (supports all platforms including ARM v6/v7)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /bin/ && \
    mv /root/.local/bin/uvx /bin/

# Install dependencies first (separate layer for better caching)
# Environment markers will automatically exclude packages based on platform
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy rest of project
COPY . .

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Install npm packages and build Tailwind CSS
RUN npm ci && \
    npx tailwindcss -i ./src/static/css/input.css -o ./src/static/css/styles.css --minify && \
    rm -rf node_modules package-lock.json

# Add entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Use custom entrypoint
ENTRYPOINT ["/entrypoint.sh"]
