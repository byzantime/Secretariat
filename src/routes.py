"""Routes.py."""

import asyncio
import os
from typing import Optional

from quart import Blueprint
from quart import current_app
from quart import flash
from quart import make_response
from quart import render_template
from quart import request
from quart import stream_with_context
from quart_auth import current_user

from src.blueprints.auth import auth_bp
from src.blueprints.browser_auth import browser_auth_bp
from src.blueprints.telegram import telegram_bp
from src.config import save_settings_to_env
from src.forms import SettingsForm
from src.models.settings import Settings

# Create blueprints for different parts of the app
main_bp = Blueprint("main", __name__)


async def _emit_event(event_name: str, data: Optional[dict] = None):
    """Emit an event via the event handler."""
    event_handler = current_app.extensions["event_handler"]
    await event_handler.emit_to_services(event_name, data or {})


@main_bp.route("/health")
async def healthcheck():
    """Healthcheck endpoint."""
    return "ok", 200


@main_bp.route("/")
async def index():
    """Render the main dashboard page."""
    return await render_template("index.html", user=current_user)


@main_bp.route("/message", methods=["POST"])
async def send_message():
    """Send a message to the AI assistant."""
    form = await request.form
    message = form.get("message")

    if not message:
        return "Message is required", 400

    # Emit chat message event with the message
    await _emit_event("chat.message", {"message": message})

    return "", 200


@main_bp.route("/stop", methods=["POST"])
async def stop_chat():
    """Stop the current chat processing."""
    # Emit chat interrupt event
    await _emit_event("chat.interrupt", {})
    return "", 200


@main_bp.route("/events")
async def chat_events():
    """SSE endpoint for chat events."""

    @stream_with_context
    async def event_stream():
        # Get WebUI channel from communication service
        communication_service = current_app.extensions["communication_service"]
        webui_channel = communication_service.get_webui_channel()

        if not webui_channel:
            current_app.logger.error("WebUI channel not available")
            yield "event: error\ndata: WebUI channel not available\n\n"
            return

        # Create a queue for this client
        client_id = f"client_{id(asyncio.current_task())}"
        client_queue = asyncio.Queue()
        webui_channel.add_client(client_id, client_queue)

        try:
            # Send initial connection message
            yield "event: connected\ndata: Connected to chat events\n\n"

            while True:
                try:
                    # Wait for events with timeout for heartbeat
                    event_type, data = await asyncio.wait_for(
                        client_queue.get(), timeout=30.0
                    )
                    escaped_data = data.replace("\n", "")
                    yield f"event: {event_type}\ndata: {escaped_data}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield "event: heartbeat\ndata: ping\n\n"

        except asyncio.CancelledError:
            current_app.logger.info(f"SSE client {client_id} disconnected")
        except Exception as e:
            current_app.logger.error(f"SSE error for client {client_id}: {e}")
            # Try to send error event before closing
            try:
                yield "event: error\ndata: Connection error\n\n"
            except:  # noqa
                pass
        finally:
            # Clean up client
            webui_channel.remove_client(client_id)

    response = await make_response(
        event_stream(),
        {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Access-Control-Allow-Origin": "*",  # CORS support
        },
    )
    return response


@main_bp.route("/settings", methods=["GET", "POST"], strict_slashes=False)
async def settings():
    """Settings page for environment variables."""
    form = SettingsForm()

    # Get setup mode status
    setup_mode = current_app.config.get("SETUP_MODE", False)

    # Load existing settings if available
    if request.method == "GET":
        existing_settings = Settings.from_env_file(validate=False)
        form.populate_from_settings(existing_settings)

    if form.validate_on_submit():
        # Convert form data to settings
        settings_dict = form.to_settings_dict()
        settings = Settings(**settings_dict)

        # Save to .env file
        save_settings_to_env(settings)

        # Schedule app shutdown after a short delay to allow response to be sent
        # Docker/systemd will automatically restart the container/service
        async def delayed_shutdown():
            """Shutdown the application after a brief delay."""
            await asyncio.sleep(0.5)  # Give time for response to be sent
            current_app.logger.info(
                "Settings saved. Shutting down for restart by container"
                " orchestration..."
            )
            # Exit cleanly - Docker/systemd will restart the app
            os._exit(0)

        # Schedule the shutdown task but don't await it
        asyncio.create_task(delayed_shutdown())

        # Flash success message
        await flash(
            "Settings saved! Application will restart automatically...",
            "success",
        )

        # Return success response immediately
        return await render_template(
            "settings.html",
            form=form,
            setup_mode=setup_mode,
            settings_saved=True,
        )
    else:
        current_app.logger.debug(form.errors)

    return await render_template("settings.html", form=form, setup_mode=setup_mode)


def register_blueprints(app):
    """Register all blueprints with the application."""
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(browser_auth_bp)
    app.register_blueprint(telegram_bp)
