"""Human assistance completion monitor."""

import asyncio
import time
from urllib.parse import urlparse

from quart import current_app


class AssistanceMonitor:
    """Monitors browser for completion of human assistance."""

    def init_app(self, app):
        """Initialize with Quart application.

        Args:
            app: Quart application instance
        """
        # Register in extensions
        app.extensions["assistance_monitor"] = self

    async def monitor_for_completion(
        self,
        browser_session,
        initial_url: str,
        session_id: str,
        timeout: int = 300,
    ) -> bool:
        """Monitor browser for completion of human assistance.

        Detects completion via:
        1. URL navigation away from the initial page
        2. Manual completion signal (user clicking "Done" button)

        Args:
            browser_session: browser-use BrowserSession instance
            initial_url: Initial page URL where assistance was requested
            session_id: Session ID to check for manual completion
            timeout: Maximum time to wait (seconds)

        Returns:
            True if assistance completed, False if timeout
        """
        start_time = time.time()
        initial_path = self._get_url_path(initial_url)

        current_app.logger.info(
            f"Monitoring for human assistance completion, initial URL: {initial_url}"
        )

        while time.time() - start_time < timeout:
            try:
                # Check if user manually marked as done
                assistance_service = current_app.extensions["human_assistance_service"]
                session = assistance_service.active_sessions.get(session_id)
                if session and session.completed:
                    current_app.logger.info(
                        "User manually marked assistance as complete"
                    )
                    return True

                # Check for URL navigation (automatic detection)
                tabs = await browser_session.get_tabs()

                if tabs:
                    current_url = tabs[0].url
                    current_path = self._get_url_path(current_url)

                    # Assistance successful if navigated away from initial page
                    if current_path != initial_path:
                        current_app.logger.info(
                            f"Navigation detected, assistance complete: {current_url}"
                        )
                        return True

            except Exception as e:
                current_app.logger.error(f"Error monitoring assistance: {e}")

            await asyncio.sleep(1)

        current_app.logger.warning("Assistance monitoring timeout")
        return False

    def _get_url_path(self, url: str) -> str:
        """Extract path from URL for comparison."""
        parsed = urlparse(url)
        return parsed.path
