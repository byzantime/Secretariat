"""Human assistance service for browser automation."""

import asyncio
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from itsdangerous.url_safe import URLSafeTimedSerializer
from quart import current_app
from quart import url_for


@dataclass
class AssistanceSession:
    """Active human assistance session."""

    session_id: str
    url: str
    reason: str
    created_at: float
    completed: bool = False


class HumanAssistanceService:
    """Manages human assistance sessions for browser automation."""

    def __init__(self):
        """Initialize human assistance service."""
        self.serializer = None
        self.active_sessions: dict[str, AssistanceSession] = {}

    def init_app(self, app):
        """Initialize with Quart application.

        Args:
            app: Quart application instance
        """
        self.serializer = URLSafeTimedSerializer(app.config["ASSISTANCE_SECRET_KEY"])

        # Ensure browser profile directory exists
        profile_dir = Path(app.config["BROWSER_USER_DATA_DIR"])
        profile_dir.mkdir(parents=True, exist_ok=True)
        app.logger.info(f"Browser profile directory: {profile_dir}")

        # Register in extensions
        app.extensions["human_assistance_service"] = self

    def create_assistance_session(self, url: str, reason: str) -> tuple[str, str]:
        """Create assistance session and return (session_id, signed_url).

        Args:
            url: URL where assistance is needed
            reason: Reason for requesting human assistance

        Returns:
            Tuple of (session_id, assistance_url)
        """
        session_id = secrets.token_urlsafe(32)

        # Create session
        session = AssistanceSession(
            session_id=session_id,
            url=url,
            reason=reason,
            created_at=time.time(),
        )
        self.active_sessions[session_id] = session

        # Generate signed URL
        token = self.serializer.dumps(session_id)
        assistance_url = url_for(
            "browser_auth.browser_viewer", token=token, _external=True
        )

        # Schedule auto-cleanup
        asyncio.create_task(self._cleanup_session(session_id))

        current_app.logger.info(
            f"Created assistance session {session_id} for {url}: {reason}.  "
            f"Assistance URL: {assistance_url}"
        )
        return session_id, assistance_url

    async def _cleanup_session(self, session_id: str):
        """Remove session after expiration."""
        await asyncio.sleep(current_app.config["ASSISTANCE_LINK_EXPIRATION"])
        if session_id in self.active_sessions:
            session = self.active_sessions.pop(session_id)
            if not session.completed:
                current_app.logger.warning(f"Assistance session {session_id} expired")

    def verify_session(self, token: str) -> Optional[str]:
        """Verify token and return session_id.

        Args:
            token: Signed token from URL

        Returns:
            session_id if valid, None otherwise
        """
        try:
            session_id = self.serializer.loads(
                token, max_age=current_app.config["ASSISTANCE_LINK_EXPIRATION"]
            )
            if session_id in self.active_sessions:
                return session_id
        except Exception as e:
            current_app.logger.error(f"Token verification failed: {e}")
        return None

    def mark_session_complete(self, session_id: str):
        """Mark assistance session as completed."""
        if session_id in self.active_sessions:
            self.active_sessions[session_id].completed = True
            current_app.logger.info(f"Assistance session {session_id} completed")
