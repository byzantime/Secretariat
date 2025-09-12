"""Fallback tool for handling unknown tool calls from the LLM."""

from typing import Any
from typing import Dict

from quart import current_app

from src.modules.tool_manager import Tool


class FallbackTool(Tool):
    """A fallback tool that handles unknown tool calls by treating them as regular messages."""

    @property
    def name(self) -> str:
        """Return the tool name."""
        return "__fallback__"

    @property
    def description(self) -> str:
        """Return the tool description."""
        return "Fallback tool for handling unknown tool calls"

    @property
    def input_schema(self) -> Dict:
        """Return the tool input schema."""
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "The reason for this message",
                },
                "message": {
                    "type": "string",
                    "description": "The message text to send to the user",
                },
            },
            "required": ["message"],
        }

    async def execute(self, input_data: Dict, conversation) -> Any:
        """Execute the fallback tool by treating it as a regular message."""
        message_text = input_data.get("message", "")

        if not message_text and len(input_data) == 1:
            message_text = next(iter(input_data.values()))

        # If still no message, provide a default
        if not message_text:
            message_text = "I'm here to help you. How can I assist you today?"
            current_app.logger.warning(
                "Fallback tool called with no usable message, using default. Input"
                f" was: {input_data}"
            )

        current_app.logger.info(
            f"Fallback tool handling message for conversation {conversation.id}:"
            f" '{message_text}'"
        )

        # Add the message to conversation history and speak it
        await conversation.speak(message_text)
        return f"Message sent: {message_text}"

    def is_available(self, conversation) -> bool:
        """Check if this tool is available for the given conversation."""
        # Fallback tool is always available (though it's handled separately)
        return True
