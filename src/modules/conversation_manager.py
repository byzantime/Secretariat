"""Simplified conversation management for LLM interactions."""

import asyncio
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from typing import TYPE_CHECKING
from typing import Dict
from typing import List
from typing import Optional
from uuid import UUID
from uuid import uuid4

from pydantic_ai.messages import ModelRequest
from pydantic_ai.messages import UserPromptPart

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.result import AgentRunResult


@dataclass(slots=True)
class Conversation:
    """Simplified conversation class for LLM interactions."""

    id: UUID = field(default_factory=uuid4)
    user_id: Optional[int] = None
    pydantic_messages: List["ModelMessage"] = field(default_factory=list)
    processing_task: Optional[asyncio.Task] = None

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None

    # Token tracking
    input_token_count: int = 0
    output_token_count: int = 0

    def store_run_result(self, result: "AgentRunResult"):
        """Store a pydantic-ai run result for future message history."""
        # Store all messages from this run result
        self.pydantic_messages.extend(result.all_messages())

    def get_pydantic_messages(
        self, last_n: Optional[int] = None
    ) -> List["ModelMessage"]:
        """Get pydantic-ai compatible messages for LLM processing."""
        if last_n is not None:
            return self.pydantic_messages[-last_n:]
        return self.pydantic_messages.copy()

    def add_user_message(self, message: str):
        """Add a user message to pydantic message history."""
        user_request = ModelRequest(parts=[UserPromptPart(content=message)])
        self.pydantic_messages.append(user_request)

    def set_processing_task(self, task: asyncio.Task):
        """Set the current processing task."""
        self.processing_task = task

    async def cancel_processing(self):
        """Cancel the current processing task."""
        if self.processing_task and not self.processing_task.done():
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass  # Expected when cancelling


class ConversationManager:
    """Manages conversations for LLM interactions."""

    def __init__(self, app=None):
        """Initialize the ConversationManager."""
        self.conversations: Dict[UUID, Conversation] = {}
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the app with the ConversationManager."""
        app.extensions["conversation_manager"] = self

    async def create_conversation(self, **kwargs) -> Conversation:
        """Create a new conversation."""
        conversation = Conversation()

        # Set any additional attributes from kwargs
        for attr, value in kwargs.items():
            if hasattr(conversation, attr):
                setattr(conversation, attr, value)

        self.conversations[conversation.id] = conversation
        return conversation

    async def get_conversation(self, conversation_id: UUID) -> Optional[Conversation]:
        """Get a conversation by ID."""
        return self.conversations.get(conversation_id)

    async def end_conversation(self, conversation_id: UUID):
        """End a conversation."""
        conversation = self.conversations.get(conversation_id)
        if conversation and not conversation.ended_at:
            conversation.ended_at = datetime.now(timezone.utc)
            await conversation.cancel_processing()
