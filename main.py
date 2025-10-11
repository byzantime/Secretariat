import signal

from src import create_app

app = create_app()


def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        app.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        # Let Quart handle the shutdown process
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


if __name__ == "__main__":
    setup_signal_handlers()
    app.logger.info("Starting Secretariat")
    try:
        app.run(host="0.0.0.0", port=8080, debug=app.config["DEBUG"])
    except KeyboardInterrupt:
        app.logger.info("Shutdown signal received, stopping application")
    finally:
        app.logger.info("Application stopped")
