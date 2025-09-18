"""Routes.py."""

import asyncio
from typing import Dict
from typing import Optional

from quart import Blueprint
from quart import current_app
from quart import make_response
from quart import render_template
from quart import request
from quart import stream_with_context
from quart_auth import current_user

from src.blueprints.auth import auth_bp
from src.modules.conversation_manager import Conversation

# Create blueprints for different parts of the app
main_bp = Blueprint("main", __name__)

# In-memory storage for SSE clients and conversations
_sse_clients: Dict[str, asyncio.Queue] = {}
_current_conversation = None


async def _update_status(status_message: Optional[str] = None):
    """Update status, prioritizing todo display if todos exist."""
    global _current_conversation
    if _current_conversation and _current_conversation.todos:
        # Always show todos if they exist
        await _current_conversation._broadcast_todo_status()
    else:
        # Show the provided status or "Ready" if none
        status_text = status_message or "Ready"
        await _broadcast_event("status_update", status_text)


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

    # Get or create conversation for this chat session
    global _current_conversation
    conversation_manager = current_app.extensions["conversation_manager"]

    if _current_conversation is None:
        _current_conversation = await conversation_manager.create_conversation()
        current_app.logger.info(f"Created new conversation: {_current_conversation.id}")
        # Refresh todo status for new conversation (empty todos)
        await _current_conversation.set_todos([])

    conversation = _current_conversation

    # Notify chat started
    await _broadcast_event("automation_started", "")
    await _update_status("Thinking...")

    # Start chat processing in background and store task on conversation
    task = asyncio.create_task(_process_chat_message(conversation, message))
    conversation.set_processing_task(task)

    return "", 200


@main_bp.route("/stop", methods=["POST"])
async def stop_chat():
    """Stop the current chat processing."""
    global _current_conversation
    if _current_conversation:
        await _current_conversation.cancel_processing()

    await _update_status("Stopped")
    await _broadcast_event("automation_complete", "")
    return "", 200


@main_bp.route("/events")
async def chat_events():
    """SSE endpoint for chat events."""

    @stream_with_context
    async def event_stream():
        # Create a queue for this client
        client_id = f"client_{id(asyncio.current_task())}"
        client_queue = asyncio.Queue()
        _sse_clients[client_id] = client_queue

        current_app.logger.info(f"SSE client {client_id} connected")

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
            _sse_clients.pop(client_id, None)
            current_app.logger.info(f"SSE client {client_id} cleaned up")

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


async def _process_chat_message(conversation: Conversation, message: str):
    """Process chat message with LLM and tools."""
    current_app.logger.info(f"Processing chat message: {message}")

    # Broadcast user message for UI
    await _broadcast_user_message(message)

    # Get the LLM service
    llm_service = current_app.extensions["llm"]
    await _update_status("Generating response...")

    current_app.logger.info(
        "Pydantic message count before processing:"
        f" {len(conversation.pydantic_messages)}"
    )
    try:
        # Process the conversation with LLM
        await llm_service.process_and_respond(conversation.id, message)
    except asyncio.CancelledError:
        current_app.logger.info("Chat processing was cancelled")
        await _update_status("Cancelled by user")
        raise  # Re-raise to properly handle the cancellation
    finally:
        await _broadcast_event("automation_complete", "")
        await _update_status()  # Show todos if they exist, otherwise "Ready"


async def _broadcast_user_message(message: str):
    """Broadcast a user message to the UI using UserMessagingService."""
    user_messaging = current_app.extensions["user_messaging"]
    # Use the global conversation for user messages
    global _current_conversation
    if _current_conversation:
        await user_messaging.send_user_message(message)


async def _broadcast_event(event_type: str, data: str):
    """Broadcast event to all connected SSE clients."""
    if not _sse_clients:
        current_app.logger.debug(f"No SSE clients connected for event: {event_type}")
        return

    current_app.logger.debug(
        f"Broadcasting event '{event_type}' to {len(_sse_clients)} clients"
    )

    # Send to all connected clients
    dead_clients = []
    for client_id, queue in list(_sse_clients.items()):
        try:
            # Use a non-blocking put with maxsize to prevent memory buildup
            if queue.qsize() > 100:  # Prevent memory issues from slow clients
                current_app.logger.warning(
                    f"Client {client_id} queue too large, dropping connection"
                )
                dead_clients.append(client_id)
                continue

            await queue.put((event_type, data))
            current_app.logger.debug(f"Event sent to client {client_id}")
        except Exception as e:
            current_app.logger.error(f"Failed to send event to client {client_id}: {e}")
            dead_clients.append(client_id)

    # Clean up dead clients
    for client_id in dead_clients:
        _sse_clients.pop(client_id, None)
        current_app.logger.info(f"Removed dead SSE client: {client_id}")

    if dead_clients:
        current_app.logger.info(f"Cleaned up {len(dead_clients)} dead SSE clients")


def register_blueprints(app):
    """Register all blueprints with the application."""
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
