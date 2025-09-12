import quart_flask_patch  # noqa - this has to be imported before Quart.
from quart import Quart
from quart import g
from quart import get_flashed_messages
from quart import redirect
from quart import render_template_string
from quart import request
from quart_auth import QuartAuth
from quart_auth import current_user
from jinja2 import ChoiceLoader, PrefixLoader, PackageLoader

from src.models.user import User


def create_app(config=None):  # noqa: C901
    """Create and configure the Quart application."""
    app = Quart(__name__)

    # Add Jinja extensions
    app.jinja_env.add_extension("jinja2.ext.do")
    app.jinja_env.add_extension("jinja2.ext.loopcontrols")
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.trim_blocks = True

    # Configure jinja-ui-kit loader
    app.jinja_loader = ChoiceLoader([
        PrefixLoader({
            "jinja_ui_kit": PackageLoader("jinja_ui_kit"),
        }),
        app.jinja_loader,
    ])

    # Load default configuration
    app.config.from_object("src.config.Config")

    # Apply config overrides
    if config:
        if isinstance(config, dict):
            app.config.update(config)
        else:
            app.config.from_object(config)

    # Initialize Sentry if DSN is configured and not in debug mode
    if app.config.get("SENTRY_DSN") and not app.config.get("DEBUG"):
        import sentry_sdk

        sentry_sdk.init(dsn=app.config["SENTRY_DSN"])

    # Initialize extensions (each extension has init_app)
    from src.extensions import init_extensions

    init_extensions(app)

    # Login manager.
    auth_manager = QuartAuth(
        duration=365 * 24 * 60 * 60,  # 365 days in seconds
        cookie_samesite="Lax",  # Mobile browser compatibility
        cookie_http_only=True,  # Security - prevent XSS access
        cookie_secure=app.config.get("QUART_AUTH_COOKIE_SECURE", True),
    )
    auth_manager.user_class = User
    auth_manager.init_app(app)

    # Register template filters
    from src.jinja_filters import register_filters

    register_filters(app)

    # Register blueprints
    from src.routes import register_blueprints

    register_blueprints(app)

    # Register error handlers
    from src.error_handlers import register_error_handlers

    register_error_handlers(app)

    @app.before_request
    def setup_session():
        """Set up session before each request.

        Make session permanent and ensures each session has a unique
        identifier.
        """
        from quart import session

        session.permanent = True

    @app.before_request
    def redirect_www():
        """Redirect www subdomain to non-www with 301 permanent redirect."""
        if request.host and request.host.startswith("www."):
            # Build the new URL without www
            new_host = request.host[4:]  # Remove 'www.'
            new_url = request.url.replace(f"://{request.host}", f"://{new_host}", 1)
            return redirect(new_url, code=301)

    @app.before_request
    @app.before_websocket
    async def load_current_user():
        """Load the current user before each request."""
        # Check if user is authenticated first
        if await current_user.is_authenticated:
            # Load additional user data if needed
            user = await current_user.load_user_data()  # type: ignore
            g.user = user
        else:
            g.user = None

    @app.after_request
    def add_cache_headers(response):
        """Add cache headers for static files."""
        if request.endpoint == "static":
            # Cache versioned static files for 1 year with immutable directive
            # Content hashes ensure cache invalidation on changes
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.after_request
    async def inject_flash_messages_for_htmx(response):
        """Inject flash messages into HTMX responses using out-of-band swaps."""
        # Only process HTMX requests
        if not request.headers.get("HX-Request"):
            return response

        # Check if there are any flash messages
        messages = get_flashed_messages(with_categories=True)
        if not messages:
            return response

        # Check if response already contains flash messages (avoid duplicates)
        current_data = await response.get_data()
        if b'id="flash-container"' in current_data:
            return response

        # Render flash messages with out-of-band swap
        flash_html = await render_template_string(
            '{% from "macros/flash_messages.html" import flash_messages %}{{'
            " flash_messages(oob_swap=True) }}"
        )

        # Append flash messages to response body
        response.set_data(current_data + flash_html.encode("utf-8"))

        return response

    return app
