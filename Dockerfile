# Use an official Python runtime as a parent image
FROM debian:testing-slim

# Accept build args for multi-arch support
ARG TARGETARCH
ARG TARGETVARIANT

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential nodejs npm wget \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN wget -qO- https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && chmod +x /usr/local/bin/uv

# Copy project files needed for installation
COPY pyproject.toml uv.lock ./

# Install Python dependencies conditionally based on architecture
# Use minimal dependencies for ARMv6 (original Pi Zero)
RUN if [ "$TARGETARCH" = "arm" ] && [ "$TARGETVARIANT" = "v6" ]; then \
        echo "Building for ARMv6 - using minimal dependencies"; \
        uv pip install --no-deps .[armv6] \
            --system --break-system-packages \
            --index-strategy unsafe-best-match; \
    else \
        echo "Building for $TARGETARCH$TARGETVARIANT - using full dependencies"; \
        uv pip install --no-deps . \
            --system --break-system-packages \
            --index-strategy unsafe-best-match \
            --extra-index-url https://download.pytorch.org/whl/cpu; \
    fi

# Copy rest of project
COPY . .

# Install npm packages and build Tailwind CSS
RUN npm ci && \
    npx tailwindcss -i ./src/static/css/input.css -o ./src/static/css/styles.css --minify && \
    rm -rf node_modules package-lock.json

# Add entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Use custom entrypoint
ENTRYPOINT ["/entrypoint.sh"]
