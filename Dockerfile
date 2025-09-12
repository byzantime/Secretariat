# Use an official Python runtime as a parent image
FROM debian:testing-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
	build-essential nodejs npm \
    # Wireguard dependencies
    iproute2 iptables wireguard-tools \
    # PJSIP dependencies
    wget swig python3-dev python3-setuptools \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN wget -qO- https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && chmod +x /usr/local/bin/uv

# Download and build PJSIP.  Needs to be done before installing Python
# dependencies because pjsua is listed in them.
RUN cd /tmp \
    && wget https://github.com/pjsip/pjproject/archive/refs/tags/2.15.1.tar.gz \
    && tar -zxf 2.15.1.tar.gz \
    && cd pjproject-2.15.1 \
    && ./configure --enable-shared --disable-resample --disable-video --disable-opencore-amr CFLAGS="-fPIC" CXXFLAGS="-fPIC" \
    && make dep && make \
    && make install \
    && ldconfig \
    # Build and install PJSUA Python bindings
    && cd pjsip-apps/src/swig/python \
    && make \
    && make install \
    # Cleanup
    && cd / \
    && rm -rf /tmp/pjproject*

# Copy just requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN uv pip install -r requirements.txt \
    --system --break-system-packages \
    --index-strategy unsafe-best-match \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Copy project
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
