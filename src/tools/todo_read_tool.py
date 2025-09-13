"""Simple todo read tool for LLM interactions."""

import secrets
from typing import Any, Dict, List
from uuid import UUID

from quart import current_app

from src.modules.tool_manager import Tool
from src.tools.todo_storage import todos_storage


class TodoReadTool(Tool):
    """A simple tool for reading the current todo list."""

    @property
    def name(self) -> str:
        return "todo_read"

    @property
    def description(self) -> str:
        return """Read the current todo list for this conversation.

Use this tool to:
- Check current task progress
- Review what needs to be done next  
- Understand the current workflow state
- Get task status before starting new work

Returns a list of todos with id, description, and state (pending/in_progress/completed)."""

    @property
    def input_schema(self) -> Dict:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    async def execute(self, input_data: Dict, conversation) -> Any:
        """Execute the todo read tool."""
        conversation_id = conversation.id
        todos = todos_storage.get(conversation_id, [])

        if not todos:
            return "No todos found for this conversation."

        result = f"Current todos ({len(todos)} total):\n"
        for i, todo in enumerate(todos, 1):
            status_emoji = {
                "pending": "⏳",
                "in_progress": "🔄",
                "completed": "✅",
            }.get(todo["state"], "❓")
            result += (
                f"{i}. [{todo['state']}] {status_emoji} {todo['description']} (ID:"
                f" {todo['id']})\n"
            )

        return result.strip()
