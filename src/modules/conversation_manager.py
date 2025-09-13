"""Simplified conversation management for LLM interactions."""

import asyncio
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from uuid import UUID
from uuid import uuid4


@dataclass(slots=True)
class Conversation:
    """Simplified conversation class for LLM interactions."""

    id: UUID = field(default_factory=uuid4)
    user_id: Optional[int] = None
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    _history_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    interrupt_event: asyncio.Event = field(default_factory=asyncio.Event)

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None

    # Token tracking
    input_token_count: int = 0
    output_token_count: int = 0

    async def add_to_conversation_history(self, message: dict):
        """Add a message to conversation history."""
        message["id"] = str(uuid4())  # Add unique ID to each message
        message["timestamp"] = datetime.now(timezone.utc)
        self.conversation_history.append(message)

    async def get_convo_history_for_llm(
        self,
        last_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get conversation history for LLM processing."""
        # Return only the last N messages if specified
        if last_n is not None:
            history = self.conversation_history[-last_n:]
        else:
            history = self.conversation_history

        # Filter for LLM-relevant messages and keys
        filtered_messages = []
        for msg in history:
            if msg.get("role") in ["user", "assistant"]:
                filtered_messages.append(
                    {key: msg[key] for key in ["role", "content"] if key in msg}
                )

        return filtered_messages

    async def add_to_role_convo_history(
        self,
        role: str,
        text: str,
        final: Optional[bool] = True,
    ):
        """Add or update conversation history for a specific role."""
        async with self._history_lock:
            history = self.conversation_history
            last_message = history[-1] if history else {}

            # Create new entry if no history, different role, or system role
            if not history or last_message.get("role") != role or role == "system":
                content_blocks = [{"type": "text", "text": text}]
                await self.add_to_conversation_history({
                    "role": role,
                    "content": content_blocks,
                    "final": final,
                })
            else:
                # Update existing message
                if final or not last_message.get("final", True):
                    # Replace content for final messages or streaming updates
                    last_message["content"] = [{"type": "text", "text": text}]
                    last_message["final"] = final
                else:
                    # Append to existing content
                    existing_text = ""
                    for block in last_message.get("content", []):
                        if block.get("type") == "text":
                            existing_text += block.get("text", "")

                    last_message["content"] = [
                        {"type": "text", "text": existing_text + text}
                    ]

    async def is_interrupted(self) -> bool:
        """Check if conversation is interrupted."""
        return self.interrupt_event.is_set()

    async def interrupt(self):
        """Interrupt the conversation."""
        self.interrupt_event.set()

    async def clear_interrupt(self):
        """Clear interrupt state."""
        if self.interrupt_event.is_set():
            self.interrupt_event.clear()


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
            await conversation.interrupt()
