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
    def description(self) -> str:
        return """Create and manage a structured task list for tracking progress.

Use this tool proactively when:
- Tasks have 3+ distinct steps
- User provides multiple tasks to complete
- Complex, non-trivial tasks requiring planning
- After receiving new instructions to capture requirements
- When starting work on a task (mark as in_progress)
- After completing tasks (mark as completed)

Skip this tool for:
- Single, straightforward tasks
- Trivial tasks with <3 steps
- Purely conversational requests

Task states: pending, in_progress, completed
Limit exactly ONE task as in_progress at any time."""

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
