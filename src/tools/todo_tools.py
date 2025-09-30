"""Todo management tools for agent."""

import secrets
from typing import Dict
from typing import List

from pydantic_ai import RunContext
from pydantic_ai.toolsets import FunctionToolset
from quart import current_app

# Create toolset for todo tools
todo_toolset = FunctionToolset()


@todo_toolset.tool
async def todo_read(ctx: RunContext[dict]) -> str:
    """Use this tool to read the current to-do list for the session.

    This tool should be used proactively and frequently to ensure that you are aware of the status of the current task list.
    You should make use of this tool as often as possible, especially in the following situations:
    - At the beginning of conversations to see what's pending
    - Before starting new tasks to prioritize work
    - When the user asks about previous tasks or plans
    - Whenever you're uncertain about what to do next
    - After completing tasks to update your understanding of remaining work
    - After every few messages to ensure you're on track

    Usage:
    - This tool takes in no parameters. So leave the input blank or empty. DO NOT include a dummy object, placeholder string or a key like "input" or "empty". LEAVE IT BLANK.
    - Returns a list of todo items with their status, priority, and content
    - Use this information to track progress and plan next steps
    - If no todos exist yet, an empty list will be returned
    """
    current_app.logger.info("🔧 TOOL CALLED: todo_read")
    conversation = ctx.deps.get("conversation")
    if not conversation:
        return "Error: No conversation context available."

    todos = conversation.get_todos()

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


@todo_toolset.tool
async def todo_write(  # noqa: C901
    ctx: RunContext[dict], tasks: List[Dict[str, str]]
) -> str:
    """Use this tool to create and manage a structured task list for your current session.

    This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
    It also helps the user understand the progress of the task and overall progress of their requests.

    ## When to Use This Tool
    Use this tool proactively in these scenarios:

    1. Complex multi-step tasks - When a task requires 3 or more distinct steps or actions
    2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
    3. User explicitly requests todo list - When the user directly asks you to use the todo list
    4. User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
    5. After receiving new instructions - Immediately capture user requirements as todos. Feel free to edit the todo list based on new information.
    6. After completing a task - Mark it complete and add any new follow-up tasks
    7. When you start working on a new task, mark the todo as in_progress. Ideally you should only have one todo as in_progress at a time. Complete existing tasks before starting new ones.

    ## When NOT to Use This Tool

    Skip using this tool when:
    1. There is only a single, straightforward task
    2. The task is trivial and tracking it provides no organizational benefit
    3. The task can be completed in less than 3 trivial steps
    4. The task is purely conversational or informational

    NOTE that you should not use this tool if there is only one trivial task to do. In this case you are better off just doing the task directly.

    ## Examples of When to Use the Todo List

    <example>
    User: I need help organizing my daily schedule, creating a budget plan, and researching vacation destinations for next summer.
    Assistant: I'll help you with these tasks. Let me create a todo list to track this work.
    *Creates todo list with the following items:*
    1. Help organize daily schedule - gather current commitments and preferences
    2. Create comprehensive budget plan - assess income, expenses, and financial goals
    3. Research vacation destinations for next summer - compile options with costs and activities
    *Begins working on the first task*

    <reasoning>
    The assistant used the todo list because:
    1. The user provided multiple distinct tasks that require different approaches
    2. Each task is complex and involves multiple steps (gathering info, analysis, compilation)
    3. The todo list helps ensure all three requests are addressed systematically
    4. This approach allows tracking progress across all three areas
    </reasoning>
    </example>

    <example>
    User: Can you help me write a professional email to my manager about a project delay, and also help me brainstorm solutions to get back on track?
    Assistant: I'll help you write a professional email about the project delay and brainstorm solutions. Let me create a todo list to track this work.
    *Creates todo list with items like: 1) Draft professional email to manager explaining project delay, 2) Brainstorm practical solutions to get project back on track, 3) Review and refine both the email and solutions*

    <reasoning>
    The assistant used the todo list because:
    1. This involves two related but distinct deliverables (email + solutions)
    2. Each requires different approaches and considerations
    3. The tasks are interconnected and benefit from systematic tracking
    4. This ensures both parts of the request are fully addressed
    </reasoning>
    </example>

    <example>
    User: I'm planning a dinner party for 8 people next weekend. Can you help me plan the menu, create a shopping list, and suggest a timeline for preparation?
    Assistant: I'd be happy to help you plan your dinner party! Let me create a todo list to organize this planning.
    *Creates todo list with items like: 1) Plan dinner party menu for 8 people considering dietary restrictions, 2) Create comprehensive shopping list organized by store sections, 3) Develop preparation timeline with tasks scheduled optimally*

    <reasoning>
    The assistant used the todo list because:
    1. Planning a dinner party involves multiple complex, interconnected tasks
    2. Menu planning, shopping, and timing all require different considerations
    3. The systematic approach ensures nothing is forgotten
    4. Each task builds on the others and benefits from organized tracking
    </reasoning>
    </example>

    ## Examples of When NOT to Use the Todo List

    <example>
    User: What's the weather like today?
    Assistant: I don't have access to real-time weather data, but you can check the current weather by looking at a weather app, website like weather.com, or asking a voice assistant like Siri or Google Assistant.

    <reasoning>
    The assistant did not use the todo list because this is a single, straightforward informational request that can be answered immediately without multiple steps or complex planning.
    </reasoning>
    </example>

    <example>
    User: Can you explain what a metaphor is?
    Assistant: A metaphor is a figure of speech that directly compares two unlike things by stating that one thing is another, without using "like" or "as." For example, "Time is money" compares time to money, suggesting both are valuable resources that can be spent or saved.

    <reasoning>
    The assistant did not use the todo list because this is a simple informational request requiring a single explanation, not multiple tasks or complex operations.
    </reasoning>
    </example>

    <example>
    User: Please remind me to call my dentist.
    Assistant: I'm not able to set actual reminders or send notifications, but I'd suggest setting a reminder on your phone, calendar app, or writing it down so you don't forget to call your dentist.

    <reasoning>
    The assistant did not use the todo list because this is a single, simple request that can be addressed with one response. There's no complex task to track or multiple steps to manage.
    </reasoning>
    </example>

    ## Task States and Management

    1. **Task States**: Use these states to track progress:
       - pending: Task not yet started
       - in_progress: Currently working on (limit to ONE task at a time)
       - completed: Task finished successfully
       - cancelled: Task no longer needed

    2. **Task Management**:
       - Update task status in real-time as you work
       - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
       - Only have ONE task in_progress at any time
       - Complete current tasks before starting new ones
       - Cancel tasks that become irrelevant

    3. **Task Breakdown**:
       - Create specific, actionable items
       - Break complex tasks into smaller, manageable steps
       - Use clear, descriptive task names

    When in doubt, use this tool. Being proactive with task management demonstrates attentiveness and ensures you complete all requirements successfully.
    """
    current_app.logger.info(
        f"🔧 TOOL CALLED: todo_write with {len(tasks) if tasks else 0} tasks"
    )
    conversation = ctx.deps.get("conversation")
    if not conversation:
        return "Error: No conversation context available."

    if not tasks:
        return "No tasks provided."

    # Validate only one task can be in_progress
    in_progress_count = sum(1 for task in tasks if task.get("state") == "in_progress")
    if in_progress_count > 1:
        return "Error: Only one task can have 'in_progress' state at a time."

    # Validate required fields and states
    valid_states = {"pending", "in_progress", "completed"}
    for task in tasks:
        if not isinstance(task, dict):
            return "Error: Each task must be a dictionary."
        if "description" not in task or "state" not in task:
            return "Error: Each task must have 'description' and 'state' fields."
        if task["state"] not in valid_states:
            return (
                f"Error: Invalid state '{task['state']}'. Must be one of:"
                f" {', '.join(valid_states)}"
            )

    # Generate simple IDs and create todos
    new_todos = []
    for task_data in tasks:
        todo = {
            "id": secrets.token_urlsafe(6),
            "description": task_data["description"],
            "state": task_data["state"],
        }
        new_todos.append(todo)

    # Set todos on conversation (automatically broadcasts status update)
    await conversation.set_todos(new_todos)

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
