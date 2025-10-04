"""VNC server management for browser authentication."""

import asyncio
import os
import signal
import subprocess
import time

from quart import current_app


class VNCServer:
    """Manages VNC server lifecycle for remote browser viewing."""

    def __init__(self):
        """Initialize VNC server."""
        self.display = None
        self.vnc_port = None
        self.xvfb_process = None
        self.x11vnc_process = None
        self.running = False

    def init_app(self, app):
        """Initialize with Quart application.

        Args:
            app: Quart application instance
        """
        self.display = app.config["VNC_DISPLAY"]
        self.vnc_port = app.config["VNC_PORT"]

        # Register in extensions
        app.extensions["vnc_server"] = self

        # Start VNC server on app startup
        @app.before_serving
        async def start_vnc():
            """Start VNC server when app starts."""
            await self.start()
            # Set DISPLAY environment variable for browser
            os.environ["DISPLAY"] = self.get_display_env()
            app.logger.info(
                f"DISPLAY environment variable set to {self.get_display_env()}"
            )

        # Register cleanup handler
        @app.after_serving
        async def cleanup_vnc():
            """Stop VNC server on shutdown."""
            if self.running:
                await self.stop()

    def _cleanup_stale_display(self):
        """Clean up stale X11 display lock files and processes."""
        # Extract display number from self.display (e.g., ":99" -> "99")
        display_num = self.display.lstrip(":")
        lock_file = f"/tmp/.X{display_num}-lock"

        # Check if lock file exists
        if os.path.exists(lock_file):
            current_app.logger.warning(f"Found stale lock file: {lock_file}")

            # Try to read PID from lock file
            try:
                with open(lock_file, "r") as f:
                    pid = int(f.read().strip())

                # Check if process is still running
                try:
                    os.kill(pid, 0)  # Signal 0 just checks if process exists
                    current_app.logger.warning(
                        f"Display {self.display} is still in use by PID {pid}"
                    )
                    # Kill the orphaned process
                    current_app.logger.info(f"Killing orphaned Xvfb process {pid}")
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(1)  # Give process time to terminate
                    try:
                        os.kill(pid, signal.SIGKILL)  # Force kill if still running
                    except ProcessLookupError:
                        pass
                except ProcessLookupError:
                    # Process doesn't exist, safe to remove lock file
                    current_app.logger.info(
                        f"Process {pid} not found, removing stale lock"
                    )
            except (ValueError, FileNotFoundError):
                current_app.logger.warning(f"Could not read PID from {lock_file}")

            # Remove the lock file
            try:
                os.remove(lock_file)
                current_app.logger.info(f"Removed lock file: {lock_file}")
            except OSError as e:
                current_app.logger.error(f"Failed to remove lock file: {e}")

    def _cleanup_stale_port(self):
        """Clean up processes using the VNC port."""
        try:
            # Use lsof to find process using the port
            result = subprocess.run(
                ["lsof", "-ti", f":{self.vnc_port}"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    pid = pid.strip()
                    if pid:
                        current_app.logger.warning(
                            f"Found process {pid} using port {self.vnc_port}"
                        )
                        try:
                            # Try graceful termination first
                            current_app.logger.info(
                                f"Killing orphaned x11vnc process {pid}"
                            )
                            os.kill(int(pid), signal.SIGTERM)
                            time.sleep(1)
                            # Force kill if still running
                            try:
                                os.kill(int(pid), signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        except ProcessLookupError:
                            current_app.logger.info(f"Process {pid} already terminated")
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
        """Start Xvfb virtual display and x11vnc server."""
        if self.running:
            current_app.logger.warning("VNC server already running")
            return

        try:
            # Clean up any stale display locks
            self._cleanup_stale_display()

            # Clean up any processes using the VNC port
            self._cleanup_stale_port()

            # Start virtual display (Xvfb)
            current_app.logger.info(f"Starting Xvfb on display {self.display}")
            self.xvfb_process = subprocess.Popen(
                [
                    "Xvfb",
                    self.display,
                    "-screen",
                    "0",
                    "1280x720x24",  # Resolution and color depth
                    "-ac",  # Disable access control
                    "+extension",
                    "GLX",  # Enable OpenGL (for modern web content)
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            # Wait for Xvfb to be ready
            await asyncio.sleep(2)

            # Verify Xvfb started
            if self.xvfb_process.poll() is not None:
                stderr = self.xvfb_process.stderr.read().decode()
                raise RuntimeError(f"Xvfb failed to start: {stderr}")

            # Start VNC server attached to Xvfb display
            current_app.logger.info(f"Starting x11vnc on port {self.vnc_port}")
            self.x11vnc_process = subprocess.Popen(
                [
                    "x11vnc",
                    "-display",
                    self.display,
                    "-forever",  # Keep running after client disconnects
                    "-shared",  # Allow multiple VNC clients
                    "-rfbport",
                    str(self.vnc_port),
                    "-nopw",  # No VNC password (secured by app auth)
                    "-quiet",  # Reduce log spam
                    "-localhost",  # Only accept local connections (noVNC proxies)
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            # Wait for x11vnc to be ready
            await asyncio.sleep(1)

            # Verify x11vnc started
            if self.x11vnc_process.poll() is not None:
                stderr = self.x11vnc_process.stderr.read().decode()
                raise RuntimeError(f"x11vnc failed to start: {stderr}")

            self.running = True
            current_app.logger.info("VNC server started successfully")

        except Exception as e:
            current_app.logger.error(f"Failed to start VNC server: {e}")
            await self.stop()
            raise

    async def stop(self):
        """Stop VNC server and virtual display."""
        if not self.running:
            return

        current_app.logger.info("Stopping VNC server")

        # Stop x11vnc
        if self.x11vnc_process:
            try:
                self.x11vnc_process.send_signal(signal.SIGTERM)
                self.x11vnc_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.x11vnc_process.kill()
            self.x11vnc_process = None

        # Stop Xvfb
        if self.xvfb_process:
            try:
                self.xvfb_process.send_signal(signal.SIGTERM)
                self.xvfb_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.xvfb_process.kill()
            self.xvfb_process = None

        self.running = False
        current_app.logger.info("VNC server stopped")

    def get_display_env(self) -> str:
        """Get DISPLAY environment variable for browser."""
        return self.display
