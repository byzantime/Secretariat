"""Web automation blueprint with SSE events."""

import asyncio
from typing import Dict
from uuid import UUID

from quart import Blueprint
from quart import current_app
from quart import make_response
from quart import request
from quart import stream_with_context

from src.modules.conversation_manager import Conversation

automation_bp = Blueprint("automation", __name__, url_prefix="/automation")

# In-memory storage for automation sessions (using conversation IDs)
_sse_clients: Dict[str, asyncio.Queue] = {}


@automation_bp.route("/start", methods=["POST"])
async def start_automation():
    """Start a new automation task."""
    form = await request.form
    task = form.get("task")

    if not task:
        return "Task is required", 400

    # Create a new conversation for this automation
    conversation_manager = current_app.extensions["conversation_manager"]
    conversation = await conversation_manager.create_conversation()

    # Send user message to conversation area
    await _broadcast_event(
        "conversation_message",
        '<div class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4"><div'
        ' class="font-semibold text-blue-800">You</div><div'
        f' class="text-blue-700">{task}</div></div>',
    )

    # Notify automation started
    await _broadcast_event("automation_started", "")
    await _broadcast_event("automation_status", "Starting automation...")

    # Start automation in background with conversation object
    asyncio.create_task(_run_automation_task(conversation, task))

    return "", 200


@automation_bp.route("/stop", methods=["POST"])
async def stop_automation():
    """Stop running automation."""
    await _send_assistant_message("Automation stopped by user")
    await _broadcast_event("automation_status", "Stopped")
    await _broadcast_event("automation_complete", "")
    return "", 200


@automation_bp.route("/respond", methods=["POST"])
async def respond_to_intervention():
    """Respond to intervention request."""
    form = await request.form
    response = form.get("response")

    if not response:
        return "Response is required", 400

    # For now, just acknowledge the response
    await _broadcast_event("automation_status", f"Received response: {response}")

    return "Response received", 200


@automation_bp.route("/events")
async def automation_events():
    """SSE endpoint for automation events."""

    @stream_with_context
    async def event_stream():
        # Create a queue for this client
        client_id = f"client_{id(asyncio.current_task())}"
        client_queue = asyncio.Queue()
        _sse_clients[client_id] = client_queue

        current_app.logger.info(f"SSE client {client_id} connected")

        try:
            # Send initial connection message
            yield "event: connected\ndata: Connected to automation events\n\n"

            while True:
                try:
                    # Wait for events with timeout for heartbeat
                    event_type, data = await asyncio.wait_for(
                        client_queue.get(), timeout=30.0
                    )
                    # Ensure proper UTF-8 encoding and escape newlines in data
                    yield f"event: {event_type}\ndata: {data.replace('\n', '')}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield "event: heartbeat\ndata: ping\n\n"

        except asyncio.CancelledError:
            current_app.logger.info(f"SSE client {client_id} disconnected")
        except Exception as e:
            current_app.logger.error(f"SSE error for client {client_id}: {e}")
            # Try to send error event before closing
            try:
                yield f"event: error\ndata: Connection error\n\n"
            except:
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
    response.timeout = None
    return response


async def _run_automation_task(conversation: Conversation, task: str):
    """Run automation task in background."""
    current_app.logger.info(f"Starting automation task: {task}")

    # Get the LLM service and web automation tool
    llm_service = current_app.extensions["llm"]
    tool_manager = current_app.extensions["tool_manager"]
    web_automation_tool = tool_manager.get_tool("web_automation")

    await _send_assistant_message("Starting web automation...")
    await _broadcast_event("automation_status", "Running automation...")

    # Execute the automation tool - let exceptions bubble up
    result = await web_automation_tool.execute({"task": task}, conversation)

    await _send_assistant_message(f"Automation completed successfully!")
    await _broadcast_event("automation_status", "Completed")
    await _broadcast_event("automation_complete", "")


async def _send_assistant_message(message: str):
    """Send an assistant message to the conversation area."""
    html_message = f"""<div class="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-4">
        <div class="font-semibold text-gray-800">Assistant</div>
        <div class="text-gray-700">{message}</div>
    </div>"""
    await _broadcast_event("conversation_message", html_message)


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
