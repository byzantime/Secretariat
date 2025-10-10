# Secretariat

An open-source AI-powered personal assistant with scheduling, memory, web browsing, and multi-platform support (web UI and Telegram).

Secretariat currently lacks authentication and is ONLY suitable for deploying on your local network.

## Quick Start

### Using Docker (Recommended)

```bash
docker pull ghcr.io/byzantime/secretariat:latest
docker run -d --name secretariat -p 8080:8080 ghcr.io/byzantime/secretariat:latest

# Visit http://localhost:8080 and configure your LLM provider in Settings
```

Data automatically persists in a Docker volume across container restarts and upgrades.

**Upgrading to a new version:**
```bash
docker stop secretariat && docker rm secretariat
docker pull ghcr.io/byzantime/secretariat:latest
docker run -d --name secretariat -p 8080:8080 ghcr.io/byzantime/secretariat:latest
```

**Optional: Direct access to data files**
```bash
# Use a bind mount if you want to access data files directly
docker run -d --name secretariat -p 8080:8080 \
  -v ~/secretariat-data:/data \
  ghcr.io/byzantime/secretariat:latest
```

### Running Locally

```bash
uv sync          # Install dependencies
./local_build.sh # Build CSS, run migrations, and start on http://localhost:5000
```

On first run, you'll be guided to configure an LLM provider (Opencode Zen or OpenRouter) via the Settings page. Additional optional features like Telegram integration, memory system (Qdrant), and browser automation can also be configured through Settings.

**Note:** The application automatically restarts when settings are changed to apply the new configuration. Press Ctrl+C to stop the application completely.

## Development

```bash
uv sync --extra dev  # Install dev dependencies
./local_build.sh     # Build CSS and start the app
```

### Updating Dependencies

```bash
# Add dependency to pyproject.toml [project] dependencies, then:
uv lock
uv sync
```

### Code Quality

```bash
ruff check . --fix --unsafe-fixes  # Lint and format code
black .                            # Format code
pytest                             # Run tests
```
