"""Browser human assistance blueprint."""

import time

from quart import Blueprint
from quart import current_app
from quart import render_template
from quart import request
from quart import url_for
from werkzeug.exceptions import Forbidden
from werkzeug.exceptions import NotFound
from werkzeug.exceptions import TooManyRequests

browser_auth_bp = Blueprint("browser_auth", __name__, url_prefix="/auth")

# Rate limiting storage (use Redis in production)
auth_attempts: dict[str, list[float]] = {}


@browser_auth_bp.before_request
async def rate_limit():
    """Rate limit assistance requests."""
    # Skip rate limiting for viewer/status/complete endpoints (protected by token/polling)
    if request.endpoint in (
        "browser_auth.browser_viewer",
        "browser_auth.check_status",
        "browser_auth.mark_complete",
    ):
        return

    ip = request.remote_addr
    now = time.time()

    # Clean old attempts
    if ip in auth_attempts:
        auth_attempts[ip] = [t for t in auth_attempts[ip] if now - t < 300]

    # Check limit: 5 attempts per 5 minutes
    if len(auth_attempts.get(ip, [])) >= 5:
        raise TooManyRequests("Too many assistance requests. Try again later.")

    auth_attempts.setdefault(ip, []).append(now)


@browser_auth_bp.after_request
async def security_headers(response):
    """Add security headers to responses."""
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Build dynamic frame-src for noVNC proxy
    novnc_port = current_app.config["NOVNC_PORT"]
    http_base = url_for("main.index", _external=True, _scheme="http")
    https_base = url_for("main.index", _external=True, _scheme="https")

    # Replace port in URLs
    http_novnc = http_base.rsplit(":", 1)[0] + f":{novnc_port}"
    https_novnc = https_base.rsplit(":", 1)[0] + f":{novnc_port}"

    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws: wss:; "
        f"frame-src 'self' {http_novnc} {https_novnc}; "
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

    # Get noVNC proxy URL using url_for with _external=True
    novnc_port = current_app.config["NOVNC_PORT"]
    base_url = url_for("main.index", _external=True, _scheme="http")
    novnc_base = base_url.rsplit(":", 1)[0] + f":{novnc_port}"
    novnc_url = f"{novnc_base}/vnc_lite.html?autoconnect=true&resize=scale"

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
