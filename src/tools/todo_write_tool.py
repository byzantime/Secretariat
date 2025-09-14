"""Simple todo write tool for LLM interactions."""

import secrets
from typing import Any, Dict, List
from uuid import UUID

from quart import current_app

from src.modules.tool_manager import Tool
from src.tools.todo_storage import todos_storage


class TodoWriteTool(Tool):
    """A simple tool for writing/updating the entire todo list."""

    @property
    def name(self) -> str:
        return "todo_write"

    @property
    def input_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "Clear, actionable task description",
                            },
                            "state": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "Current task state",
                            },
                        },
                        "required": ["description", "state"],
                    },
                    "description": "Complete list of tasks (replaces existing todos)",
                }
            },
            "required": ["tasks"],
        }

    async def execute(self, input_data: Dict, conversation) -> Any:
        """Execute the todo write tool."""
        conversation_id = conversation.id
        tasks_data = input_data.get("tasks", [])

        if not tasks_data:
            return "No tasks provided."

        # Validate only one task can be in_progress
        in_progress_count = sum(
            1 for task in tasks_data if task.get("state") == "in_progress"
        )
        if in_progress_count > 1:
            return "Error: Only one task can have 'in_progress' state at a time."

        # Generate simple IDs and create todos
        new_todos = []
        for task_data in tasks_data:
            todo = {
                "id": secrets.token_urlsafe(6),  # 8-char URL-safe ID
                "description": task_data["description"],
                "state": task_data["state"],
            }
            new_todos.append(todo)

        # Replace entire todo list atomically
        todos_storage[conversation_id] = new_todos

        # Broadcast todo status update
        await self._broadcast_todo_status_update()

        # Return summary
        state_counts = {}
        for todo in new_todos:
            state = todo["state"]
            state_counts[state] = state_counts.get(state, 0) + 1

        summary = f"Updated todos: {len(new_todos)} total"
        if state_counts:
            parts = []
            for state, count in state_counts.items():
                emoji = {"pending": "⏳", "in_progress": "🔄", "completed": "✅"}[state]
                parts.append(f"{count} {state} {emoji}")
            summary += f" ({', '.join(parts)})"

        return summary

    async def _broadcast_todo_status_update(self):
        """Broadcast todo status update to the UI."""
        try:
            # Import here to avoid circular imports
            from src.routes import _broadcast_todo_status

            await _broadcast_todo_status()
        except ImportError:
            # If routes module isn't available, silently skip
            pass
