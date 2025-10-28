# Secretariat

An open-source AI-powered personal assistant with scheduling, memory, web browsing, and multi-platform support (web UI and Telegram).

Secretariat currently lacks authentication and is ONLY suitable for deploying on your local network.

## Quick Start

### Using Docker (Recommended)

```bash
docker pull ghcr.io/byzantime/secretariat:latest
docker run -d --name secretariat -p 8080:8080 \
  --restart always \
  -v secretariat-data:/data \
  ghcr.io/byzantime/secretariat:latest

# Visit http://localhost:8080 and configure your LLM provider in Settings
```
Data persists in the `secretariat-data` volume across container restarts and upgrades.

The app will always restart automatically after reboot (change to `--restart unless-stopped` if you'd like it to stay down once stopped).  Before auto-restart will work, you also need to ensure Docker itself starts on boot. On most Linux systems:

```bash
# Enable Docker daemon to start on boot
sudo systemctl enable docker
sudo systemctl start docker
```

**Upgrading to a new version:**
```bash
docker stop secretariat && docker rm secretariat
docker pull ghcr.io/byzantime/secretariat:latest
docker run -d --name secretariat -p 8080:8080 \
  -v secretariat-data:/data \
  ghcr.io/byzantime/secretariat:latest
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
./local_build.sh # Build CSS, run migrations, and start on http://localhost:8080
```

On first run, you'll be guided to configure an LLM provider (Opencode Zen or OpenRouter) via the Settings page. Additional optional features like Telegram integration (with built-in ngrok tunnel support), memory system (Qdrant), and browser automation can also be configured through Settings.

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

### Debugging and Logs

Logs are written to `logs/app.log` with automatic rotation (10MB per file, keeps last 5 backups):

```bash
tail -f logs/app.log               # Real-time log streaming
tail -50 logs/app.log              # View last 50 lines
grep ERROR logs/app.log            # Search for errors
grep -i browser logs/app.log       # Case-insensitive search (e.g., browser-use issues)
ls -lh logs/                       # View all log files
```

Logs are written to both console and file, useful for debugging long-running processes.
