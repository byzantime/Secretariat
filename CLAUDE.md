# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Search and Code Analysis

- Use `ast_grep` (`sg`) for syntax-aware searches: `sg --lang python -p '<pattern>'`
- Prefer structural matching over text-based tools like `rg` or `grep` for code analysis
- Set `--lang` appropriately for the target language

## Architecture Overview

This is a Quart-based AI agent application with HTMX frontend, PostgreSQL database, and Anthropic Claude integration. Built as a foundation for AI-powered web applications.

### Key Components

- **Quart Framework**: Async Python web framework (Flask-like API)
- **Database**: PostgreSQL with SQLAlchemy ORM and Alembic migrations
- **Frontend**: HTMX + Tailwind CSS for reactive UI
- **Authentication**: Quart-Auth with session management
- **LLM Integration**: Anthropic Claude API via async client
- **Tool System**: Extensible tool framework for AI agent capabilities

### Application Structure

```
src/
├── __init__.py              # Application factory (create_app)
├── config.py               # Environment-based configuration
├── routes.py               # Main blueprint registration
├── extensions.py           # Extension initialization order
├── blueprints/            # Route blueprints
│   └── auth.py           # Authentication routes
├── models/               # Database models
│   ├── user.py          # User model and manager
│   └── organisation.py  # Organisation model
├── modules/             # Core services
│   ├── database.py      # Database connection management
│   ├── llm_service.py   # Anthropic Claude integration
│   └── tool_manager.py  # AI tool system
├── tools/              # AI agent tools
│   └── fallback_tool.py # Default tool for unknown calls
└── templates/          # Jinja2 templates with HTMX
```

## Development Commands

### Environment Setup
```bash
# Install Python dependencies
uv pip install -r requirements.txt

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
# Development server
python main.py

# Production server (via Docker)
docker build -t apparat .
docker run -p 8080:8080 apparat
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

### Extension Initialization Order
Extensions in `src/extensions.py` must be initialized in dependency order:
1. Compress, Assets, Logging
2. Database (required by user management)
3. User Manager, Tool Manager
4. LLM Service (depends on tools)

### Tool System
- All tools inherit from `Tool` abstract base class in `tool_manager.py`
- Tools are automatically registered during `ToolManager.init_app()`
- Fallback tool handles unknown tool calls gracefully
- Tools can implement conditional availability via `is_available()`

### HTMX Integration
- Flash messages automatically injected into HTMX responses via `inject_flash_messages_for_htmx`
- Out-of-band swaps used for dynamic UI updates
- Templates use `jinja-ui-kit` for consistent components

### Database Models
- User model supports authentication via `UserManager`
- Models use SQLAlchemy with async support (asyncpg)
- Database URL constructed from individual env vars with PostgreSQL+asyncpg driver

## Environment Variables

Required:
- `SECRET_KEY`: Flask session encryption
- `ANTHROPIC_API_KEY`: Claude API access
- `DATABASE_*`: PostgreSQL connection details

Optional:
- `DEBUG`: Enable debug mode (default: False)
- `SENTRY_DSN`: Error tracking
- `LOG_LEVEL`: Logging level (default: INFO)

## Testing

- Uses pytest with asyncio support
- Test markers: `asyncio`, `integration`, `stress`
- Test configuration in `pyproject.toml`
- Never attempt to start a development server - the app is already running locally with auto-reload
