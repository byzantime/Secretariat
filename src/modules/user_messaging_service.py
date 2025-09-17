"""User messaging service for handling SSE and future communication channels."""

from abc import ABC
from abc import abstractmethod
from datetime import datetime
from typing import Dict
from typing import Optional
from uuid import UUID

from quart import current_app
from quart import render_template


class ChannelFormatter(ABC):
    """Abstract base class for message formatters for different channels."""

    @abstractmethod
    async def format_message_start(
        self, conversation_id: UUID, message_id: str, content: str
    ) -> Dict[str, str]:
        """Format initial message for this channel."""
        pass

    @abstractmethod
    async def format_message_update(
        self, conversation_id: UUID, message_id: str, content: str
    ) -> Dict[str, str]:
        """Format message update for this channel."""
        pass

    @abstractmethod
    async def format_message_complete(
        self, conversation_id: UUID, message_id: str, content: str
    ) -> Dict[str, str]:
        """Format message completion for this channel."""
        pass

    @abstractmethod
    async def format_error(
        self, conversation_id: UUID, error_message: str
    ) -> Dict[str, str]:
        """Format error message for this channel."""
        pass


class SSEChannelFormatter(ChannelFormatter):
    """Formatter for Server-Sent Events channel."""

    async def format_message_start(
        self, conversation_id: UUID, message_id: str, content: str
    ) -> Dict[str, str]:
        """Format initial message for SSE."""
        html_message = await render_template(
            "macros/ui_message.html",
            sender="Assistant",
            content=content,
            message_id=message_id,
            timestamp=datetime.now(),
        )
        return {"event_type": "streaming_text", "data": html_message}

    async def format_message_update(
        self, conversation_id: UUID, message_id: str, content: str
    ) -> Dict[str, str]:
        """Format message update for SSE."""
        html_message = await render_template(
            "macros/ui_message_update.html",
            content=content,
            message_id=message_id,
            oob_swap=True,
        )
        return {"event_type": f"message-{message_id}-update", "data": html_message}

    async def format_message_complete(
        self, conversation_id: UUID, message_id: str, content: str
    ) -> Dict[str, str]:
        """Format message completion for SSE."""
        # For SSE, completion is just a status update
        return {"event_type": "message_complete", "data": message_id}

    async def format_error(
        self, conversation_id: UUID, error_message: str
    ) -> Dict[str, str]:
        """Format error message for SSE."""
        return {"event_type": "error", "data": error_message}


class UserMessagingService:
    """Service for handling user messaging across different channels."""

    def __init__(self, app=None):
        self.channels = {}
        self.default_channel = "sse"
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the user messaging service with the app."""
        # Register default SSE channel
        self.register_channel("sse", SSEChannelFormatter(), app)

        # Subscribe to LLM events
        self._subscribe_to_llm_events(app)

        app.extensions["user_messaging"] = self
        app.logger.info("UserMessagingService initialized")

    def register_channel(self, channel_name: str, formatter: ChannelFormatter, app):
        """Register a new communication channel."""
        self.channels[channel_name] = formatter
        app.logger.info(f"Registered messaging channel: {channel_name}")

    def _subscribe_to_llm_events(self, app):
        """Subscribe to LLM events for message delivery."""
        event_handler = app.extensions["event_handler"]
        # Message events
        event_handler.on("llm.message.start", self._handle_message_start)
        event_handler.on("llm.message.chunk", self._handle_message_chunk)
        event_handler.on("llm.message.complete", self._handle_message_complete)
        # Error events
        event_handler.on("llm.error", self._handle_error)
        # Tool events
        event_handler.on("llm.tool.called", self._handle_tool_called)

    async def _handle_message_start(
        self, conversation_id: UUID, data: Optional[Dict] = None
    ):
        """Handle the start of a new message."""
        if not data:
            return

        message_id = data.get("message_id")
        content = data.get("content", "")
        channel = self.default_channel

        if message_id and channel in self.channels:
            formatter = self.channels[channel]
            formatted = await formatter.format_message_start(
                conversation_id, message_id, content
            )
            await self._deliver_message(channel, formatted)

    async def _handle_message_chunk(
        self, conversation_id: UUID, data: Optional[Dict] = None
    ):
        """Handle a message chunk update."""
        if not data:
            return

        message_id = data.get("message_id")
        content = data.get("content", "")
        channel = self.default_channel

        if message_id and channel in self.channels:
            formatter = self.channels[channel]
            formatted = await formatter.format_message_update(
                conversation_id, message_id, content
            )
            await self._deliver_message(channel, formatted)

    async def _handle_message_complete(
        self, conversation_id: UUID, data: Optional[Dict] = None
    ):
        """Handle message completion."""
        if not data:
            return

        message_id = data.get("message_id")
        content = data.get("content", "")
        channel = self.default_channel

        if message_id and channel in self.channels:
            formatter = self.channels[channel]
            formatted = await formatter.format_message_complete(
                conversation_id, message_id, content
            )
            await self._deliver_message(channel, formatted)

    async def _handle_error(self, conversation_id: UUID, data: Optional[Dict] = None):
        """Handle LLM errors."""
        if not data:
            return

        error_message = data.get("error", "Unknown error occurred")
        channel = self.default_channel

        if channel in self.channels:
            formatter = self.channels[channel]
            formatted = await formatter.format_error(conversation_id, error_message)
            await self._deliver_message(channel, formatted)

    async def _handle_tool_called(
        self, conversation_id: UUID, data: Optional[Dict] = None
    ):
        """Handle tool usage notifications."""
        if not data:
            return

        # For now, just log tool usage
        tool_name = data.get("tool_name")
        tool_args = data.get("tool_args", {})
        current_app.logger.info(
            f"Tool called in conversation {conversation_id}: {tool_name} with args"
            f" {tool_args}"
        )

    async def _deliver_message(self, channel: str, formatted_message: Dict[str, str]):
        """Deliver a formatted message through the specified channel."""
        event_type = formatted_message["event_type"]
        data = formatted_message["data"]

        # For SSE, we use the existing broadcast mechanism
        if channel == "sse":
            # Import here to avoid circular dependency
            from src.routes import _broadcast_event

            await _broadcast_event(event_type, data)
        else:
            # Future channels can be implemented here
            current_app.logger.warning(f"Channel {channel} not yet implemented")

    async def send_user_message(self, conversation_id: UUID, message: str):
        """Send a user message through the default channel."""
        channel = self.default_channel

        if channel not in self.channels:
            current_app.logger.error(f"Unknown channel: {channel}")
            return

        # Generate message ID and format user message
        import secrets

        message_id = secrets.token_urlsafe(8)

        formatter = self.channels[channel]
        if hasattr(formatter, "format_user_message"):
            formatted = await formatter.format_user_message(
                conversation_id, message_id, message
            )
            await self._deliver_message(channel, formatted)
        else:
            # Default user message formatting
            html_message = await render_template(
                "macros/ui_message.html",
                sender="You",
                content=message,
                message_id=message_id,
                timestamp=datetime.now(),
            )
            await self._deliver_message(
                channel, {"event_type": "streaming_text", "data": html_message}
            )
