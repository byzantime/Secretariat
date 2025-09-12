"""Web automation blueprint with SSE events."""

import asyncio
from typing import Dict

from quart import Blueprint
from quart import current_app
from quart import g
from quart import make_response
from quart import request
from quart import stream_with_context

automation_bp = Blueprint("automation", __name__, url_prefix="/automation")

# In-memory storage for automation sessions
_automation_sessions: Dict[str, dict] = {}
_sse_clients: Dict[str, asyncio.Queue] = {}


@automation_bp.route("/start", methods=["POST"])
async def start_automation():
    """Start a new automation task."""
    form = await request.form
    task = form.get("task")

    if not task:
        return "Task is required", 400

    # Create a session ID (for now, use a simple counter)
    session_id = f"session_{len(_automation_sessions) + 1}"

    # Store session info
    _automation_sessions[session_id] = {
        "task": task,
        "status": "starting",
        "messages": [],
    }

    # Start automation in background
    asyncio.create_task(_run_automation_task(session_id, task))

    return f"Automation started with session ID: {session_id}", 200


@automation_bp.route("/stop", methods=["POST"])
async def stop_automation():
    """Stop running automation."""
    # For now, just send a stop signal
    await _broadcast_event("automation_complete", "Automation stopped by user")
    return "Automation stopped", 200


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
            yield f"event: connected\ndata: Connected to automation events\n\n"

            while True:
                try:
                    # Wait for events with timeout for heartbeat
                    event_type, data = await asyncio.wait_for(
                        client_queue.get(), timeout=30.0
                    )
                    yield f"event: {event_type}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"event: heartbeat\ndata: ping\n\n"

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


async def _run_automation_task(session_id: str, task: str):
    """Run automation task in background."""
    try:
        current_app.logger.info(f"Starting automation task: {task}")

        # Get the LLM service to trigger the web automation tool
        llm_service = current_app.extensions.get("llm")
        if not llm_service:
            await _broadcast_event(
                "automation_status", "Error: LLM service not available"
            )
            return

        # Create a mock conversation object for the tool execution
        class MockConversation:
            def __init__(self):
                self.id = session_id

        conversation = MockConversation()

        # Get the web automation tool
        tool_manager = current_app.extensions.get("tool_manager")
        if not tool_manager:
            await _broadcast_event(
                "automation_status", "Error: Tool manager not available"
            )
            return

        web_automation_tool = tool_manager.get_tool("web_automation")
        if not web_automation_tool:
            await _broadcast_event(
                "automation_status", "Error: Web automation tool not available"
            )
            return

        await _broadcast_event("automation_status", "Starting web automation...")

        # Execute the automation tool
        result = await web_automation_tool.execute({"task": task}, conversation)

        await _broadcast_event("automation_status", f"Automation completed: {result}")
        await _broadcast_event("automation_complete", result)

    except Exception as e:
        error_msg = f"Automation failed: {str(e)}"
        current_app.logger.error(error_msg, exc_info=True)
        await _broadcast_event("automation_status", error_msg)
        await _broadcast_event("automation_complete", error_msg)


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
