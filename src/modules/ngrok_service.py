"""Ngrok tunnel service for exposing local app to the internet."""

import logging
from typing import Optional

try:
    import ngrok

    NGROK_AVAILABLE = True
except ImportError:
    NGROK_AVAILABLE = False


class NgrokService:
    """Service for managing ngrok tunnels."""

    def __init__(self):
        self.listener = None
        self.tunnel_url: Optional[str] = None
        self.error_message: Optional[str] = None
        self.logger = logging.getLogger(__name__)

    def init_app(self, app) -> bool:
        """Initialize the ngrok service with the Flask/Quart app."""
        # Always register service in extensions (even if not active)
        app.extensions["ngrok_service"] = self

        public_url_mode = app.config.get("PUBLIC_URL_MODE", "ngrok")
        auth_token = app.config.get("NGROK_AUTH_TOKEN")

        if not NGROK_AVAILABLE:
            if auth_token and public_url_mode == "ngrok":
                self.logger.warning(
                    "Ngrok mode selected but ngrok package not installed"
                )
            return False

        if public_url_mode != "ngrok":
            self.logger.info(
                f"Public URL mode is '{public_url_mode}', skipping ngrok tunnel"
            )
            return False

        if not auth_token:
            self.logger.info("No ngrok auth token configured, skipping ngrok tunnel")
            return False

        # Schedule tunnel initialization for when the event loop is ready
        app.before_serving(self._start_tunnel)
        app.after_serving(self._stop_tunnel)
        self.logger.info("Ngrok service setup scheduled for server start")
        return True

    async def _start_tunnel(self):
        """Start the ngrok tunnel."""
        from quart import current_app

        try:
            auth_token = current_app.config.get("NGROK_AUTH_TOKEN")

            if not auth_token:
                current_app.logger.warning("Cannot start ngrok tunnel: no auth token")
                return

            # Start ngrok tunnel on port 8080
            current_app.logger.info("Starting ngrok tunnel on port 8080...")
            self.listener = await ngrok.forward(8080, authtoken=auth_token)
            self.tunnel_url = self.listener.url()
            self.error_message = None  # Clear any previous errors

            current_app.logger.info(
                f"Ngrok tunnel established successfully at {self.tunnel_url}"
            )

        except ValueError as e:
            # Handle ngrok-specific errors (like session limit)
            error_str = str(e)
            if "ERR_NGROK_108" in error_str:
                self.error_message = (
                    "Your ngrok account is limited to 1 simultaneous session. "
                    "Please close other ngrok sessions or upgrade your plan."
                )
            elif "failed to connect session" in error_str:
                # Extract the main error message from the tuple
                if isinstance(e.args, tuple) and len(e.args) > 1:
                    self.error_message = e.args[1].split("\n")[0]
                else:
                    self.error_message = "Failed to connect to ngrok service"
            else:
                self.error_message = f"Ngrok error: {error_str}"

            current_app.logger.error(
                f"Failed to start ngrok tunnel: {e}", exc_info=True
            )
            # Reset state on failure
            self.listener = None
            self.tunnel_url = None

        except Exception as e:
            self.error_message = f"Failed to start ngrok tunnel: {str(e)}"
            current_app.logger.error(
                f"Failed to start ngrok tunnel: {e}", exc_info=True
            )
            # Reset state on failure
            self.listener = None
            self.tunnel_url = None

    async def _stop_tunnel(self):
        """Stop the ngrok tunnel."""
        from quart import current_app

        if self.listener:
            try:
                current_app.logger.info("Closing ngrok tunnel...")
                await self.listener.close()
                current_app.logger.info("Ngrok tunnel closed successfully")
            except Exception as e:
                current_app.logger.error(
                    f"Error closing ngrok tunnel: {e}", exc_info=True
                )
            finally:
                self.listener = None
                self.tunnel_url = None

    def get_tunnel_url(self) -> Optional[str]:
        """Get the current ngrok tunnel URL."""
        return self.tunnel_url

    def is_active(self) -> bool:
        """Check if the ngrok tunnel is active."""
        return self.listener is not None and self.tunnel_url is not None
