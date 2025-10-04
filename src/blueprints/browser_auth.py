"""Browser human assistance blueprint."""

import asyncio
import mimetypes
from pathlib import Path
from urllib.parse import urlencode

import novnc
import websockets
from quart import Blueprint
from quart import current_app
from quart import render_template
from quart import request
from quart import send_file
from quart import url_for
from quart import websocket
from werkzeug.exceptions import Forbidden
from werkzeug.exceptions import NotFound

browser_auth_bp = Blueprint("browser_auth", __name__, url_prefix="/auth")


@browser_auth_bp.after_request
async def security_headers(response):
    """Add security headers to responses."""
    endpoint = request.endpoint
    # Don't apply restrictive headers to noVNC static files (they need to be iframed)
    if endpoint == "browser_auth.serve_novnc_files":
        # Very permissive CSP for noVNC - remove most restrictions
        # Don't set X-Frame-Options or frame-ancestors to allow iframing
        response.headers.pop("X-Frame-Options", None)
        response.headers["Content-Security-Policy"] = (
            "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
            "script-src * 'unsafe-inline' 'unsafe-eval'; "
            "connect-src * ws: wss:; "
            "img-src * data: blob:; "
            "style-src * 'unsafe-inline'; "
            "worker-src * blob:; "
            "font-src * data:; "
            "frame-ancestors *"  # Allow being iframed from anywhere
        )
        current_app.logger.info(
            f"✓ Applied permissive CSP for noVNC file: {request.path}"
        )
        return response

    # For viewer page - allow iframing noVNC
    if endpoint == "browser_auth.browser_viewer":
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Very permissive CSP for viewer page that embeds noVNC iframe
        response.headers.pop("X-Frame-Options", None)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self' ws: wss: http: https:; "
            "frame-src *; "  # Allow iframes from any source temporarily
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "child-src *"  # Allow any child sources
        )
        current_app.logger.info(
            f"✓ Applied permissive CSP for viewer page: {request.path}"
        )
        return response

    # Apply strict headers to other routes
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws: wss:; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'"
    )
    return response


@browser_auth_bp.route("/browser/<token>")
async def browser_viewer(token: str):
    """Serve browser assistance viewer page.

    Args:
        token: Signed session token

    Returns:
        Rendered viewer page
    """
    assistance_service = current_app.extensions["human_assistance_service"]

    # Verify token
    session_id = assistance_service.verify_session(token)
    if not session_id:
        raise Forbidden("Invalid or expired assistance link")

    session = assistance_service.active_sessions.get(session_id)
    if not session:
        raise NotFound("Session not found")

    # Generate noVNC URL using proxied routes (works with Ngrok)
    # Construct WebSocket path explicitly (url_for may add ws:// scheme for WebSocket endpoints)
    ws_path = "/auth/novnc-ws"

    # Detect correct scheme (ngrok terminates HTTPS and forwards HTTP)
    # Check X-Forwarded-Proto header first, fall back to request.scheme
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme)

    # Build noVNC URL with properly encoded query parameters
    # Use same scheme as incoming request to avoid mixed content errors
    novnc_base = url_for(
        "browser_auth.serve_novnc_files",
        filename="vnc_lite.html",
        _external=True,
        _scheme=scheme,
    )
    query_params = urlencode(
        {"autoconnect": "true", "resize": "scale", "path": ws_path}
    )
    novnc_url = f"{novnc_base}?{query_params}"

    return await render_template(
        "browser_auth/viewer.html",
        session_id=session_id,
        url=session.url,
        reason=session.reason,
        novnc_url=novnc_url,
    )


@browser_auth_bp.route("/status/<session_id>")
async def check_status(session_id: str):
    """Check assistance session status.

    Args:
        session_id: Session identifier

    Returns:
        JSON status
    """
    assistance_service = current_app.extensions["human_assistance_service"]
    session = assistance_service.active_sessions.get(session_id)

    if not session:
        return {"completed": False, "exists": False}, 404

    return {"completed": session.completed, "exists": True}


@browser_auth_bp.route("/complete/<session_id>", methods=["POST"])
async def mark_complete(session_id: str):
    """Mark assistance session as complete.

    Args:
        session_id: Session identifier

    Returns:
        JSON response
    """
    assistance_service = current_app.extensions["human_assistance_service"]
    session = assistance_service.active_sessions.get(session_id)

    if not session:
        return {"error": "Session not found"}, 404

    assistance_service.mark_session_complete(session_id)
    return {"success": True, "completed": True}


@browser_auth_bp.route("/novnc/<path:filename>")
async def serve_novnc_files(filename: str):
    """Serve noVNC static files with correct MIME types.

    Args:
        filename: Requested file path

    Returns:
        Static file from noVNC directory
    """
    # Construct full file path
    file_path = Path(novnc.server_path) / filename

    # Security check - ensure path is within novnc directory
    try:
        file_path = file_path.resolve()
        novnc_base = Path(novnc.server_path).resolve()
        if not str(file_path).startswith(str(novnc_base)):
            raise Forbidden("Access denied")
    except (ValueError, OSError):
        raise NotFound("File not found")

    if not file_path.exists():
        raise NotFound("File not found")

    # Guess MIME type
    mimetype, _ = mimetypes.guess_type(str(file_path))

    # Override for JavaScript modules
    if file_path.suffix == ".js":
        mimetype = "application/javascript"
    elif file_path.suffix == ".mjs":
        mimetype = "application/javascript"
    elif mimetype is None:
        mimetype = "application/octet-stream"

    return await send_file(file_path, mimetype=mimetype)


@browser_auth_bp.websocket("/novnc-ws")
async def novnc_websocket_proxy():
    """WebSocket proxy for noVNC connections.

    Proxies WebSocket connections from the client to the local noVNC websockify server.
    This allows remote access via Ngrok without needing multiple tunnels.
    """
    novnc_port = current_app.config["NOVNC_PORT"]
    backend_uri = f"ws://localhost:{novnc_port}/websockify"

    # Connect to local websockify server
    try:
        async with websockets.connect(backend_uri) as backend_ws:

            async def forward_to_backend():
                """Forward messages from client to backend."""
                try:
                    while True:
                        data = await websocket.receive()
                        await backend_ws.send(data)
                except Exception as e:
                    current_app.logger.debug(f"Forward to backend ended: {e}")

            async def forward_to_client():
                """Forward messages from backend to client."""
                try:
                    async for message in backend_ws:
                        await websocket.send(message)
                except Exception as e:
                    current_app.logger.debug(f"Forward to client ended: {e}")

            # Run both forwarding tasks concurrently
            await asyncio.gather(
                forward_to_backend(), forward_to_client(), return_exceptions=True
            )

    except Exception as e:
        current_app.logger.error(f"WebSocket proxy error: {e}")
        await websocket.close(1011, "Backend connection failed")
