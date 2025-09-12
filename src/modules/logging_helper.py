import logging
import os
from typing import Dict

from quart.logging import default_handler


class LoggingHelper:
    """Helper class for setting up logging.

    Library log levels can be overriden using envvars, e.g.:
    AIOHTTP_LOG_LEVEL=DEBUG
    """

    def __init__(self, app=None):
        """Initialise the LoggingHelper.

        Args:
            app (Quart, optional): The Quart application instance.
        """
        self._enabled_loggers: Dict[str, str] = {}
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize logging configuration.

        Sets up root logger with console handler that will be used by both the
        application and any library loggers (like aiohttp). This provides
        centralized control over all logging.
        """
        # Get application log level
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        numeric_level = getattr(logging, log_level, None)
        if not isinstance(numeric_level, int):
            raise ValueError(f"Invalid log level: {log_level}")

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(numeric_level)

        # Create console handler
        console_handler = logging.StreamHandler()

        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(formatter)

        # Add handler to root logger
        root_logger.addHandler(console_handler)

        # Configure Quart app logger
        app.logger.removeHandler(default_handler)
        app.logger.setLevel(numeric_level)

        # Set all existing loggers to WARNING by default
        self._configure_third_party_loggers(app)

        # Load any explicitly configured loggers from environment
        self._load_enabled_loggers(app)

        app.extensions["logging_helper"] = self
        app.logger.info(f"Logging initialised with level: {log_level}")

    def _configure_third_party_loggers(self, app):
        """Set all third-party loggers to WARNING."""
        for name in logging.root.manager.loggerDict:
            # Skip our own logger
            if name == app.name or name.startswith(f"{app.name}."):
                continue
            # Set third-party logger to WARNING
            logging.getLogger(name).setLevel(logging.WARNING)

    def _load_enabled_loggers(self, app):
        """Load explicitly configured loggers from environment."""
        for key, value in os.environ.items():
            if key.endswith("_LOG_LEVEL"):
                logger_name = key[:-10].lower()  # Remove _LOG_LEVEL suffix
                self.set_logger_level(app, logger_name, value)

    def set_logger_level(self, app, logger_name: str, level: str):
        """Set log level for a specific logger.

        Args:
            logger_name: Name of the logger
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        numeric_level = getattr(logging, level.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError(f"Invalid log level: {level}")

        logger = logging.getLogger(logger_name)
        logger.setLevel(numeric_level)
        self._enabled_loggers[logger_name] = level
        app.logger.info(f"Set {logger_name} log level to {level}")
