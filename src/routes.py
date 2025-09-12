"""Routes.py."""

from quart import Blueprint
from quart import render_template
from quart_auth import current_user

from src.blueprints.auth import auth_bp
from src.blueprints.automation import automation_bp

# Create blueprints for different parts of the app
main_bp = Blueprint("main", __name__)


@main_bp.route("/health")
async def healthcheck():
    """Healthcheck endpoint."""
    return "ok", 200


@main_bp.route("/")
async def index():
    """Render the main dashboard page."""
    return await render_template("index.html", user=current_user)


def register_blueprints(app):
    """Register all blueprints with the application."""
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(automation_bp)
