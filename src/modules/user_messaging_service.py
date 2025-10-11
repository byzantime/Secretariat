"""Communication service for handling multi-channel user messaging."""

import asyncio
import html
import secrets
from abc import ABC
from abc import abstractmethod
from datetime import datetime
from typing import Dict
from typing import List
from typing import Optional

from quart import current_app
from quart import render_template

try:
    from telegram import Bot
    from telegram.ext import Application

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


class CommunicationChannel(ABC):
    """Abstract base class for communication channels."""

    def __init__(self, channel_name: str, channel_type: str):
        self.channel_name = channel_name
        self.channel_type = channel_type  # "webui" or "messaging"

    @abstractmethod
    def init_app(self, app) -> bool:
        """Initialise the channel with the Flask/Quart app. Return True if successful."""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if this channel is currently connected/available."""
        pass

    async def send_message_start(self, message_id: str, content: str) -> bool:
        """Send initial message. Return True if successful, False if not supported."""
        return False

    async def send_message_update(self, message_id: str, content: str) -> bool:
        """Send message update. Return True if successful, False if not supported."""
        return False

    async def send_message_complete(self, message_id: str, content: str) -> bool:
        """Send message completion. Return True if successful, False if not supported."""
        return False

    async def send_error(self, error_message: str) -> bool:
        """Send error message. Return True if successful, False if not supported."""
        return False

    async def send_tool_notification(self, tool_name: str, tool_args: dict) -> bool:
        """Send tool usage notification. Default implementation logs the tool usage."""
        current_app.logger.info(f"Tool called: {tool_name} with args {tool_args}")
        return True

    def _get_friendly_tool_message(self, tool_name: str) -> str:
        """Convert tool name to user-friendly message."""
        tool_messages = {
            "duckduckgo_search": "Searching the web...",
            "browse_web": "Using the web browser...",
            "record_grocery_order": "Recording grocery order...",
            "get_shopping_predictions": "Analyzing shopping patterns...",
            "add_to_shopping_list": "Adding to shopping list...",
            "remove_from_shopping_list": "Removing from shopping list...",
            "adjust_item_frequency": "Adjusting item frequency...",
            "get_shopping_list": "Getting shopping list...",
            "get_item_history": "Looking up item history...",
            "memory_search": "Searching my memory...",
            "setup_automation": "Setting up automation...",
            "automations_list": "Listing automations...",
            "delete_automation": "Deleting automation...",
            "todo_read": "Reading todos...",
            "todo_write": "Updating todos...",
        }
        return tool_messages.get(tool_name, f"Using {tool_name}...")

    async def update_status(self, status_message: Optional[str] = None) -> bool:
        """Update status display. Return True if successful, False if not supported."""
        return False


class WebUIChannel(CommunicationChannel):
    """Web UI communication channel via Server-Sent Events."""

    def __init__(self):
        super().__init__("webui", "webui")
        self._sse_clients: Dict[str, asyncio.Queue] = {}

    async def is_connected(self) -> bool:
        """Check if SSE clients are connected."""
        return len(self._sse_clients) > 0

    def get_connected_clients_count(self) -> int:
        """Get the number of connected SSE clients."""
        return len(self._sse_clients)

    def add_client(self, client_id: str, client_queue: asyncio.Queue):
        """Add a new SSE client."""
        self._sse_clients[client_id] = client_queue
        current_app.logger.info(f"SSE client {client_id} connected")

    def remove_client(self, client_id: str):
        """Remove an SSE client."""
        self._sse_clients.pop(client_id, None)
        current_app.logger.info(f"SSE client {client_id} cleaned up")

    async def send_message_start(self, message_id: str, content: str) -> bool:
        """Send initial message via SSE."""
        try:
            html_message = await render_template(
                "macros/ui_message.html",
                sender="Assistant",
                content=content,
                message_id=message_id,
                timestamp=datetime.now(),
            )
            await self.broadcast_event("streaming_text", html_message)
            return True
        except Exception as e:
            current_app.logger.error(f"SSE message start failed: {e}")
            return False

    async def send_message_update(self, message_id: str, content: str) -> bool:
        """Send message update via SSE."""
        try:
            html_message = await render_template(
                "macros/ui_message_update.html",
                content=content,
                message_id=message_id,
                oob_swap=True,
            )
            await self.broadcast_event(f"message-{message_id}-update", html_message)
            return True
        except Exception as e:
            current_app.logger.error(f"SSE message update failed: {e}")
            return False

    async def send_message_complete(self, message_id: str, content: str) -> bool:
        """Send message completion via SSE."""
        if content:
            await self.send_message_update(message_id, content)
        return True

    async def send_error(self, error_message: str) -> bool:
        """Send error message via SSE."""
        try:
            await self.broadcast_event("error", error_message)
            return True
        except Exception as e:
            current_app.logger.error(f"SSE error send failed: {e}")
            return False

    async def send_user_message(self, message: str) -> bool:
        """Send a user message via SSE."""
        try:
            message_id = secrets.token_urlsafe(8)
            html_message = await render_template(
                "macros/ui_message.html",
                sender="You",
                content=message,
                message_id=message_id,
                timestamp=datetime.now(),
            )
            await self.broadcast_event("streaming_text", html_message)
            return True
        except Exception as e:
            current_app.logger.error(f"SSE user message failed: {e}")
            return False

    async def send_tool_notification(self, tool_name: str, tool_args: dict) -> bool:
        """Send tool usage notification via SSE as a status update."""
        try:
            friendly_message = self._get_friendly_tool_message(tool_name)
            await self.broadcast_event("status_update", friendly_message)
            return True
        except Exception as e:
            current_app.logger.error(f"SSE tool notification failed: {e}")
            return False

    async def broadcast_event(self, event_type: str, data: str):
        """Broadcast event to all connected SSE clients."""
        if not self._sse_clients:
            current_app.logger.debug(
                f"No SSE clients connected for event: {event_type}"
            )
            return

        if "update" not in event_type:
            current_app.logger.debug(
                f"Broadcasting event '{event_type}' to {len(self._sse_clients)} clients"
            )

        # Send to all connected clients
        dead_clients = []
        for client_id, queue in list(self._sse_clients.items()):
            try:
                # Use a non-blocking put with maxsize to prevent memory buildup
                if queue.qsize() > 100:  # Prevent memory issues from slow clients
                    current_app.logger.warning(
                        f"Client {client_id} queue too large, dropping connection"
                    )
                    dead_clients.append(client_id)
                    continue

                await queue.put((event_type, data))
                current_app.logger.debug(f"Event sent to client {client_id}")
            except Exception as e:
                current_app.logger.error(
                    f"Failed to send event to client {client_id}: {e}"
                )
                dead_clients.append(client_id)

        # Clean up dead clients
        for client_id in dead_clients:
            self._sse_clients.pop(client_id, None)
            current_app.logger.info(f"Removed dead SSE client: {client_id}")

        if dead_clients:
            current_app.logger.info(f"Cleaned up {len(dead_clients)} dead SSE clients")

    async def update_status(self, status_message: Optional[str] = None) -> bool:
        """Update status display for WebUI, prioritising todo display if todos exist."""
        try:
            # Get communication service to access current conversation
            communication_service = current_app.extensions["communication_service"]

            if (
                communication_service.current_conversation
                and communication_service.current_conversation.todos
            ):
                # Always show todos if they exist
                await (
                    communication_service.current_conversation._broadcast_todo_status()
                )
            else:
                # Show the provided status or "Ready" if none
                status_text = status_message or "Ready"
                await self.broadcast_event("status_update", status_text)
            return True
        except Exception as e:
            current_app.logger.error(f"WebUI status update failed: {e}")
            return False

    def init_app(self, app) -> bool:
        """Initialise the WebUI channel with the Flask/Quart app."""
        app.logger.info("WebUI channel initialised successfully")
        return True


class TelegramChannel(CommunicationChannel):
    """Telegram communication channel via Bot API."""

    def __init__(self):
        super().__init__("telegram", "messaging")
        self.bot_token: Optional[str] = None
        self.webhook_url: Optional[str] = None
        self.bot: Optional[Bot] = None
        self.application: Optional[Application] = None
        self._user_conversations: Dict[int, str] = {}
        self.allowed_users: set = set()

    def init_app(self, app) -> bool:
        """Initialise the Telegram channel with the Flask/Quart app."""
        # Get configuration
        self.bot_token = app.config.get("TELEGRAM_BOT_TOKEN")
        self.webhook_url = app.config.get("TELEGRAM_WEBHOOK_URL")

        # Parse allowed users
        allowed_users_str = app.config.get("TELEGRAM_ALLOWED_USERS", "")
        if allowed_users_str:
            try:
                # Parse comma-separated list of user IDs
                self.allowed_users = {
                    int(user_id.strip())
                    for user_id in allowed_users_str.split(",")
                    if user_id.strip().isdigit()
                }
                app.logger.info(
                    f"Telegram access restricted to {len(self.allowed_users)} users"
                )
            except ValueError as e:
                app.logger.error(f"Invalid TELEGRAM_ALLOWED_USERS format: {e}")
                self.allowed_users = set()
        else:
            app.logger.warning(
                "TELEGRAM_ALLOWED_USERS not configured - bot will reject all messages"
            )
            self.allowed_users = set()

        if not TELEGRAM_AVAILABLE:
            app.logger.warning(
                "Telegram bot token provided but python-telegram-bot not installed"
            )
            return False

        if not self.bot_token:
            app.logger.info(
                "No Telegram bot token configured, skipping Telegram channel"
            )
            return False

        # Schedule bot initialization for when the event loop is ready
        app.before_serving(self.initialize_bot)
        app.logger.info("Telegram channel setup scheduled for server start")
        return True

    async def initialize_bot(self):
        """Initialize the Telegram bot when the event loop is ready."""
        try:
            # Initialize the bot
            self.application = Application.builder().token(self.bot_token).build()
            self.bot = self.application.bot

            # Initialize but don't start polling (we'll use webhooks)
            await self.application.initialize()
            current_app.logger.info("Telegram bot initialized successfully")

            # Determine webhook URL (prefer ngrok, fall back to manual)
            webhook_url = self._get_webhook_url()

            # Auto-setup webhook if webhook URL is available
            if webhook_url:
                current_app.logger.info("Setting up Telegram webhook automatically...")
                webhook_success = await self.setup_webhook(webhook_url)
                if webhook_success:
                    current_app.logger.info(
                        "Telegram webhook setup completed successfully"
                    )
                else:
                    current_app.logger.warning(
                        "Telegram webhook setup failed - bot will still work"
                        " but won't receive messages"
                    )
            else:
                current_app.logger.info(
                    "No webhook URL available (neither ngrok nor manual), skipping"
                    " webhook setup"
                )

        except Exception as e:
            current_app.logger.error(
                f"Telegram bot initialization failed: {e}", exc_info=True
            )
            # Reset bot state on failure
            self.bot = None
            self.application = None

    def _get_webhook_url(self) -> Optional[str]:
        """Get the webhook URL based on configured mode."""
        public_url_mode = current_app.config.get("PUBLIC_URL_MODE", "ngrok")

        if public_url_mode == "ngrok":
            # Check for ngrok service
            ngrok_service = current_app.extensions["ngrok_service"]
            if ngrok_service.is_active():
                ngrok_url = ngrok_service.get_tunnel_url()
                if ngrok_url:
                    current_app.logger.info(
                        f"Using ngrok tunnel URL for webhook: {ngrok_url}"
                    )
                    return ngrok_url
            else:
                current_app.logger.warning(
                    "Ngrok mode selected but tunnel is not active"
                )
                return None
        else:
            # Use manual webhook URL
            if self.webhook_url:
                current_app.logger.info(f"Using manual webhook URL: {self.webhook_url}")
                return self.webhook_url
            else:
                current_app.logger.warning("Manual mode selected but no URL configured")
                return None

    async def is_connected(self) -> bool:
        """Check if the bot is initialised and ready."""
        return self.bot is not None and self.application is not None

    async def send_message_complete(self, message_id: str, content: str) -> bool:
        """Send message completion via Telegram."""
        if not await self.is_connected():
            return False

        success = True
        for chat_id in self._user_conversations.keys():
            try:
                await self.bot.send_message(
                    chat_id=chat_id, text=content, parse_mode="Markdown"
                )
            except Exception as e:
                # Fallback to escaped HTML entities if Markdown parsing fails
                try:
                    await self.bot.send_message(
                        chat_id=chat_id, text=html.escape(content), parse_mode="HTML"
                    )
                except Exception as fallback_e:
                    current_app.logger.error(
                        f"Failed to send completion to {chat_id}: {e}, fallback failed:"
                        f" {fallback_e}",
                        exc_info=True,
                    )
                    success = False
        return success

    async def send_tool_notification(self, tool_name: str, tool_args: dict) -> bool:
        """Send tool usage notification via Telegram."""
        if not await self.is_connected():
            return False

        friendly_message = self._get_friendly_tool_message(tool_name)
        success = True
        for chat_id in self._user_conversations.keys():
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=f"_{friendly_message}_",
                    parse_mode="Markdown",
                )
            except Exception as e:
                current_app.logger.error(
                    f"Failed to send tool notification to {chat_id}: {e}"
                )
                success = False
        return success

    def is_user_authorized(self, user_id: int) -> bool:
        """Check if a user is authorized to use the bot."""
        # Only allow users explicitly listed in allowed_users
        return user_id in self.allowed_users

    def register_user(self, chat_id: int, conversation_id: Optional[str] = None):
        """Register a Telegram user for receiving messages."""
        self._user_conversations[chat_id] = conversation_id
        current_app.logger.info(f"Registered Telegram user {chat_id}")

    def unregister_user(self, chat_id: int):
        """Unregister a Telegram user."""
        self._user_conversations.pop(chat_id, None)
        current_app.logger.info(f"Unregistered Telegram user {chat_id}")

    async def process_incoming_message(self, chat_id: int, text: str):
        """Process incoming message from Telegram user."""
        # Check if user is authorized
        if not self.is_user_authorized(chat_id):
            current_app.logger.warning(
                f"Unauthorized Telegram user {chat_id} attempted to send message:"
                f" {text}"
            )
            return

        # Register user if not already registered
        if chat_id not in self._user_conversations:
            self.register_user(chat_id)

        # Get communication service to send the message
        current_app.extensions["communication_service"]
        # Emit the message event to be processed by the LLM
        event_handler = current_app.extensions["event_handler"]
        await event_handler.emit_to_services(
            "chat.message",
            {
                "message": text,
                "source_channel": "telegram",
                "user_id": str(chat_id),
            },
        )

    async def update_status(self, status_message: Optional[str] = None) -> bool:
        """Update status via Telegram chat action indicator."""
        if not await self.is_connected():
            return False

        # Handle None status_message
        if status_message is None:
            return False

        # Only send typing indicators for certain status messages
        if status_message.lower() not in ["thinking...", "generating..."]:
            return False

        action = "typing"
        success = True

        for chat_id in self._user_conversations.keys():
            try:
                await self.bot.send_chat_action(chat_id=chat_id, action=action)
                current_app.logger.debug(
                    f"Sent '{action}' action to Telegram user {chat_id}"
                )
            except Exception as e:
                current_app.logger.error(
                    f"Failed to send chat action to {chat_id}: {e}"
                )
                success = False
        return success

    async def setup_webhook(self, webhook_url: str) -> bool:
        """Automatically set up the Telegram webhook."""
        if not await self.is_connected():
            current_app.logger.error("Cannot setup webhook: Telegram bot not connected")
            return False

        # Set the webhook
        webhook_url_full = f"{webhook_url}/telegram/webhook"
        result = await self.bot.set_webhook(url=webhook_url_full)

        if result:
            current_app.logger.info(f"Webhook set successfully to {webhook_url_full}")
            return True
        else:
            current_app.logger.error(
                "Failed to set webhook: Telegram API returned False"
            )
            return False


class CommunicationService:
    """Service for managing communication across multiple channels."""

    def __init__(self, channels: Optional[List[CommunicationChannel]] = None, app=None):
        self.channels: Dict[str, CommunicationChannel] = {}
        self.current_conversation = None
        self._background_tasks: set = set()  # Track background tasks for cleanup

        # Store channels for initialization during init_app
        self._channel_instances = channels or [WebUIChannel(), TelegramChannel()]

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialise the communication service with the app."""
        # Initialise and register channels
        self._initialise_channels(app)

        # Subscribe to LLM events
        self._subscribe_to_llm_events(app)

        # Subscribe to chat and UI events
        self._subscribe_to_chat_events(app)

        app.extensions["communication_service"] = self
        app.logger.info("CommunicationService initialised")

        # Add shutdown handler for task cleanup
        app.after_serving(self._cleanup_background_tasks)

    def _initialise_channels(self, app):
        """Initialise and register all channels with individual error handling."""
        for channel in self._channel_instances:
            try:
                app.logger.info(
                    "Initialising channel:"
                    f" {channel.channel_name} ({channel.channel_type})"
                )

                # Try to initialise the channel
                success = channel.init_app(app)

                if success:
                    # Only register channels that initialised successfully
                    self.register_channel(app, channel)
                    app.logger.info(
                        f"Channel '{channel.channel_name}' initialised and registered"
                        " successfully"
                    )
                else:
                    app.logger.warning(
                        f"Channel '{channel.channel_name}' initialization returned"
                        " False - skipping registration"
                    )

            except Exception as e:
                app.logger.error(
                    f"Failed to initialise channel '{channel.channel_name}': {e}"
                )
                app.logger.debug("Channel initialization error details:", exc_info=True)

    def register_channel(self, app, channel: CommunicationChannel):
        """Register a communication channel."""
        self.channels[channel.channel_name] = channel
        app.logger.info(
            "Registered communication channel:"
            f" {channel.channel_name} ({channel.channel_type})"
        )

    def get_webui_channel(self) -> Optional["WebUIChannel"]:
        """Get the WebUI channel instance."""
        webui_channel = self.channels.get("webui")
        if isinstance(webui_channel, WebUIChannel):
            return webui_channel
        return None

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

    def _subscribe_to_chat_events(self, app):
        """Subscribe to chat events for conversation management."""
        event_handler = app.extensions["event_handler"]
        # Chat lifecycle events
        event_handler.on("chat.message", self._handle_chat_message)
        event_handler.on("chat.interrupt", self._handle_chat_interrupt)
        # Status update events
        event_handler.on("status.update", self._handle_status_update)
        # User message events
        event_handler.on("message.send", self._handle_user_message)

    async def _handle_message_start(self, data: Optional[Dict] = None):
        """Handle the start of a new message."""
        if not data or data.get("message_id") is None:
            return

        await self._broadcast_to_connected_channels(
            "send_message_start",
            data.get("message_id"),
            data.get("content", ""),
        )

    async def _handle_message_chunk(self, data: Optional[Dict] = None):
        """Handle a message chunk update."""
        if not data or data.get("message_id") is None:
            return

        await self._broadcast_to_connected_channels(
            "send_message_update",
            data.get("message_id"),
            data.get("content", ""),
        )

    async def _handle_message_complete(self, data: Optional[Dict] = None):
        """Handle message completion."""
        if not data or data.get("message_id") is None:
            return

        await self._broadcast_to_connected_channels(
            "send_message_complete",
            data.get("message_id"),
            data.get("content", ""),
        )

    async def _handle_error(self, data: Optional[Dict] = None):
        """Handle LLM errors."""
        if not data:
            return

        error_message = data.get("error", "Unknown error occurred")
        await self._broadcast_to_connected_channels("send_error", error_message)

    async def _handle_tool_called(self, data: Optional[Dict] = None):
        """Handle tool usage notifications."""
        if not data or data.get("tool_name") is None:
            return

        await self._broadcast_to_connected_channels(
            "send_tool_notification",
            data.get("tool_name"),
            data.get("tool_args", {}),
        )

    async def _broadcast_to_connected_channels(self, method_name: str, *args):
        """Broadcast message to all connected channels."""
        for channel in self.channels.values():
            if await channel.is_connected():
                method = getattr(channel, method_name, None)
                if method:
                    try:
                        await method(*args)
                    except Exception as e:
                        current_app.logger.warning(
                            f"Failed to send via {channel.channel_name}: {e}"
                        )

    async def send_user_message(
        self, message: str, source_channel: Optional[str] = None
    ):
        """Send a user message via WebUI (user messages are typically shown in UI)."""
        # Send the message via WebUI for display
        webui_channel = self.channels.get("webui")
        if webui_channel and await webui_channel.is_connected():
            asyncio.create_task(webui_channel.send_user_message(message))

    # Chat Event Handlers
    async def _handle_chat_message(self, data: Optional[Dict] = None):
        """Handle chat message event - create conversation if needed and process message."""
        if not data:
            return

        message = data.get("message")
        if not message:
            return

        # Get or create conversation
        if self.current_conversation is None:
            conversation_manager = current_app.extensions["conversation_manager"]
            self.current_conversation = await conversation_manager.create_conversation()
            current_app.logger.info(
                f"Created new conversation: {self.current_conversation.id}"
            )
            # Refresh todo status for new conversation (empty todos)
            await self.current_conversation.set_todos([])

        # Emit automation started event
        await self.update_status("Thinking...")

        # Start chat processing in background
        task = asyncio.create_task(
            self._process_chat_message(self.current_conversation, message)
        )
        self.current_conversation.set_processing_task(task)

        # Track task for cleanup
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _handle_chat_interrupt(self, data: Optional[Dict] = None):
        """Handle chat interrupt event."""
        if self.current_conversation:
            await self.current_conversation.cancel_processing()

        await self.update_status("Stopped")

    async def _handle_status_update(self, data: Optional[Dict] = None):
        """Handle status update event."""
        if not data:
            return
        await self.update_status(data.get("message"))

    async def _handle_user_message(self, data: Optional[Dict] = None):
        """Handle user message event."""
        if not data or data.get("message") is None:
            return

        await self.send_user_message(
            data.get("message"),
            data.get("source_channel"),
        )

    async def update_status(self, status_message: Optional[str] = None):
        """Update status across all connected channels."""
        for channel in self.channels.values():
            if await channel.is_connected():
                asyncio.create_task(channel.update_status(status_message))

    async def _process_chat_message(self, conversation, message: str):
        """Process chat message with LLM and tools."""
        current_app.logger.info(f"Processing chat message: {message}")
        await self.update_status("Generating response...")

        # Broadcast user message for UI
        await self.send_user_message(message)

        current_app.logger.info(
            "Pydantic message count before processing:"
            f" {len(conversation.pydantic_messages)}"
        )
        # Get the LLM service
        llm_service = current_app.extensions["llm"]
        try:
            # Process the conversation with LLM
            await llm_service.process_and_respond(conversation.id, message)
        except asyncio.CancelledError:
            current_app.logger.info("Chat processing was cancelled")
            await self.update_status("Cancelled by user")
            raise  # Re-raise to properly handle the cancellation
        finally:
            await self.update_status()

    async def _cleanup_background_tasks(self):
        """Cancel all background tasks on shutdown."""
        if not self._background_tasks:
            return

        current_app.logger.info(
            f"Cancelling {len(self._background_tasks)} background tasks"
        )

        # Cancel all background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellation to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        current_app.logger.info("Background task cleanup completed")
