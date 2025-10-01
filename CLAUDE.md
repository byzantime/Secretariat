# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Search and Code Analysis

- Use `ast_grep` (`sg`) for syntax-aware searches: `sg --lang python -p '<pattern>'`
- Prefer structural matching over text-based tools like `rg` or `grep` for code analysis
- Set `--lang` appropriately for the target language

## Architecture Overview

This is a Quart-based AI personal assistant application with HTMX frontend and SQLite database.

### Key Components

- **Quart Framework**: Async Python web framework (Flask-like API)
- **Database**: SQLite with SQLAlchemy ORM and Alembic migrations
- **Frontend**: HTMX + Tailwind CSS for reactive UI
- **Authentication**: Quart-Auth with session management
- **LLM Integration**: Pydantic AI
- **Tool System**: Extensible tool framework for AI agent capabilities
- **Telegram Bot**: python-telegram-bot with webhook support
- **Scheduling**: APScheduler for recurring tasks
- **Memory System**: Vector embeddings (FastEmbed) with Qdrant client
- **Browser Automation**: browser-use for web interactions
- **Multi-platform**: Docker builds for AMD64, ARM64, ARMv6, ARMv7

## Development Commands

### Environment Setup
```bash
# Install Python dependencies (preferred)
uv sync

# Run commands with uv
uv run python main.py
uv run pytest

# Install Node.js dependencies and build CSS
npm ci
npm run build
```

### Database Operations
```bash
# Run database migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"
```

### Frontend Development
```bash
# Build Tailwind CSS (development)
tailwindcss -i ./src/static/css/input.css -o ./src/static/css/styles.css --watch

# Build Tailwind CSS (production)
npm run build
```

### Running the Application
```bash
# Development server (with auto-reload)
python main.py

# Using uv
uv run python main.py

# Docker (see BUILD.md for platform-specific builds)
docker pull ghcr.io/byzantime/secretariat:latest
docker run -p 8080:8080 ghcr.io/byzantime/secretariat:latest
```

### Code Quality
```bash
# Format code
ruff format

# Lint code
ruff check

# Run tests
pytest
```

## Key Architectural Patterns

### Tool System
- Tools in `src/tools/`: browser_tools, memory_tools, scheduling_tools, todo_tools
- Pydantic AI tools pattern used for LLM integration
- Tools can be platform-conditional (e.g., browser tools unavailable on Alpine builds)

### LLM Provider System
- Custom providers in `src/providers/` (e.g., zen_provider.py)
- Built on Pydantic AI framework
- Agent instructions customizable via `agent_instructions.txt`

### Memory & Vector Search
- Vector embeddings via FastEmbed (with fallback on ARMv6/ARMv7)
- Memory storage and retrieval in `src/modules/memory.py`
- Conversation tracking via `conversation_manager.py`

### Scheduling System
- APScheduler integration for recurring tasks
- Scheduled tasks stored in database (models/scheduled_task.py)
- Event-driven architecture via `event_handler.py`

### Multi-Channel Interface
- Web UI: HTMX + Tailwind CSS
- Telegram Bot: Webhook-based integration
- Templates use `jinja-ui-kit` for consistent components

### Platform Support
- Debian images (AMD64/ARM64): Full features including FastEmbed, browser automation
- Alpine images (ARMv6/ARMv7): Core features with fallbacks
- See BUILD.md for detailed platform guide

## Environment Variables

Required:
- `SECRET_KEY`: Session encryption
- `DATABASE_*`: SQLite connection details

Optional:
- `DEBUG`: Enable debug mode (default: False)
- `SENTRY_DSN`: Error tracking
- `LOG_LEVEL`: Logging level (default: INFO)
- `TELEGRAM_BOT_TOKEN`: Telegram bot integration
- `TELEGRAM_WEBHOOK_URL`: Webhook endpoint for Telegram

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test markers
pytest -m integration
pytest -m stress
```

Configuration:
- Markers: `asyncio`, `integration`, `stress`
- Configuration in `pyproject.toml`
- Async test support via pytest-asyncio

## Project Structure

Key directories:
- `src/blueprints/`: Route handlers (auth, telegram, core)
- `src/models/`: Database models (user, scheduled_task, schedule_config)
- `src/modules/`: Core services (llm_service, memory, scheduling_service, etc.)
- `src/tools/`: AI agent tools (browser, memory, scheduling, todo)
- `src/providers/`: Custom LLM providers
- `migrations/`: Alembic database migrations
- `tests/`: Test suite
