"""noVNC WebSocket proxy service."""

import asyncio
import subprocess

import novnc
from quart import current_app


class NoVNCProxy:
    """Manages noVNC WebSocket proxy (websockify)."""

    def __init__(self):
        """Initialize noVNC proxy."""
        self.listen_port = None
        self.vnc_host = None
        self.vnc_port = None
        self.process = None
        self.running = False

    def init_app(self, app):
        """Initialize with Quart application.

        Args:
            app: Quart application instance
        """
        self.listen_port = app.config["NOVNC_PORT"]
        self.vnc_host = "localhost"
        self.vnc_port = app.config["VNC_PORT"]

        # Register in extensions
        app.extensions["novnc_proxy"] = self

        # Start noVNC proxy on app startup (after VNC server)
        @app.before_serving
        async def start_novnc():
            """Start noVNC proxy when app starts."""
            await self.start()

        # Register cleanup handler
        @app.after_serving
        async def cleanup_novnc():
            """Stop noVNC proxy on shutdown."""
            if self.running:
                await self.stop()

    def _cleanup_stale_port(self):
        """Clean up processes using the noVNC port."""
        try:
            # Use lsof to find process using the port
            result = subprocess.run(
                ["lsof", "-ti", f":{self.listen_port}"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    pid = pid.strip()
                    if pid:
                        current_app.logger.warning(
                            f"Found process {pid} using port {self.listen_port}"
                        )
                        try:
                            # Try graceful termination first
                            current_app.logger.info(
                                f"Killing orphaned websockify process {pid}"
                            )
                            subprocess.run(["kill", pid], check=False)
                            # Give it a moment to terminate
                            subprocess.run(["sleep", "1"], check=False)
                            # Force kill if still running
                            subprocess.run(["kill", "-9", pid], check=False)
                        except Exception as e:
                            current_app.logger.error(
                                f"Failed to kill process {pid}: {e}"
                            )
        except FileNotFoundError:
            # lsof not available
            current_app.logger.warning("lsof not available, skipping port cleanup")
        except Exception as e:
            current_app.logger.error(f"Error during port cleanup: {e}")

    async def start(self):
        """Start websockify proxy for noVNC."""
        if self.running:
            current_app.logger.warning("noVNC proxy already running")
            return

        try:
            # Clean up any processes using the port
            self._cleanup_stale_port()

            # Start websockify (comes with novnc package)
            current_app.logger.info(f"Starting websockify on port {self.listen_port}")

            # Use Python's websockify module from novnc package
            self.process = await asyncio.create_subprocess_exec(
                "websockify",
                "--web",
                novnc.server_path,  # noVNC files path (extracted to /tmp/novnc_server)
                str(self.listen_port),
                f"{self.vnc_host}:{self.vnc_port}",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait for websockify to start
            await asyncio.sleep(1)

            # Verify process still running
            if self.process.returncode is not None:
                stderr = await self.process.stderr.read()
                raise RuntimeError(f"websockify failed: {stderr.decode()}")

            self.running = True
            current_app.logger.info("noVNC proxy started successfully")

        except Exception as e:
            current_app.logger.error(f"Failed to start noVNC proxy: {e}")
            await self.stop()
            raise

    async def stop(self):
        """Stop websockify proxy."""
        if not self.running:
            return

        current_app.logger.info("Stopping noVNC proxy")

        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            self.process = None

        self.running = False
        current_app.logger.info("noVNC proxy stopped")
