from quart import current_app
from quart import redirect
from quart import url_for
from quart_auth import Unauthorized


def register_error_handlers(app):
    """Register error handlers with the application."""

    @app.errorhandler(Exception)
    async def handle_exception(e):
        current_app.logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
        return "An unexpected error occurred", 500

    @app.errorhandler(404)
    async def handle_not_found(e):
        return "Not found", 404

    @app.errorhandler(403)
    async def handle_forbidden(e):
        return "Forbidden", 403

    @app.errorhandler(401)
    async def handle_unauthorized(e):
        return "Unauthorized", 401

    @app.errorhandler(Unauthorized)
    async def redirect_to_login(*_):
        return redirect(url_for("auth.login"))
