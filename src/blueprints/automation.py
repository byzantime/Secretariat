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
_automation_sessions: Dict[UUID, dict] = {}
_sse_clients: Dict[str, asyncio.Queue] = {}


@automation_bp.route("/start", methods=["POST"])
async def start_automation():
    """Start a new automation task."""
    form = await request.form
    task = form.get("task")

    if not task:
        return "Task is required", 400

    # Create a new conversation for this automation
    conversation_manager = current_app.extensions.get("conversation_manager")
    if not conversation_manager:
        return "Conversation manager not available", 500

    conversation = await conversation_manager.create_conversation()

    # Store session info using conversation ID
    _automation_sessions[conversation.id] = {
        "task": task,
        "status": "starting",
        "messages": [],
    }

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

        try:
            # Send initial connection message
            yield "event: connected\ndata: Connected to automation events\n\n"

            while True:
                try:
                    # Wait for events with timeout for heartbeat
                    event_type, data = await asyncio.wait_for(
                        client_queue.get(), timeout=30.0
                    )
                    yield f"event: {event_type}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield "event: heartbeat\ndata: ping\n\n"

        except asyncio.CancelledError:
            current_app.logger.info(f"SSE client {client_id} disconnected")
        except Exception as e:
            current_app.logger.error(f"SSE error for client {client_id}: {e}")
        finally:
            # Clean up client
            _sse_clients.pop(client_id, None)

    response = await make_response(
        event_stream(),
        {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    response.timeout = None
    return response


async def _run_automation_task(conversation: Conversation, task: str):
    """Run automation task in background."""
    current_app.logger.info(f"Starting automation task: {task}")

    try:
        # Get the LLM service to trigger the web automation tool
        llm_service = current_app.extensions.get("llm")
        if not llm_service:
            await _send_assistant_message("Error: LLM service not available")
            await _broadcast_event(
                "automation_status", "Error: LLM service not available"
            )
            await _broadcast_event("automation_complete", "")
            return

        # Get the web automation tool
        tool_manager = current_app.extensions.get("tool_manager")
        if not tool_manager:
            await _send_assistant_message("Error: Tool manager not available")
            await _broadcast_event(
                "automation_status", "Error: Tool manager not available"
            )
            await _broadcast_event("automation_complete", "")
            return

        web_automation_tool = tool_manager.get_tool("web_automation")
        if not web_automation_tool:
            await _send_assistant_message("Error: Web automation tool not available")
            await _broadcast_event(
                "automation_status", "Error: Web automation tool not available"
            )
            await _broadcast_event("automation_complete", "")
            return

        await _send_assistant_message("Starting web automation...")
        await _broadcast_event("automation_status", "Running automation...")

        # Execute the automation tool - let exceptions bubble up
        result = await web_automation_tool.execute({"task": task}, conversation)

        await _send_assistant_message(f"Automation completed successfully!")
        await _broadcast_event("automation_status", "Completed")
        await _broadcast_event("automation_complete", "")

    except Exception as e:
        error_msg = f"Automation failed: {str(e)}"
        await _send_assistant_message(error_msg)
        await _broadcast_event("automation_status", "Failed")
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
        return

    # Send to all connected clients
    for client_id, queue in list(_sse_clients.items()):
        try:
            await queue.put((event_type, data))
        except Exception as e:
            current_app.logger.error(f"Failed to send event to client {client_id}: {e}")
            # Remove dead clients
            _sse_clients.pop(client_id, None)
