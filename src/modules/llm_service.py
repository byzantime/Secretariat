"""LLMService using Pydantic AI agent framework."""

import json
import secrets
from datetime import datetime
from typing import Dict
from typing import List
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

import browser_use
from pydantic_ai import Agent
from pydantic_ai import RunContext
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from quart import current_app

from src.tools.todo_storage import todos_storage


class LLMService:
    """Service for interacting with LLMs using Pydantic AI."""

    # Constants
    DEFAULT_MODEL = "claude-3-haiku-20240307"
    DEFAULT_MAX_TOKENS = 1000
    DEFAULT_TEMPERATURE = 0
    CHUNK_SIZE_THRESHOLD = 30
    EXTRACTION_MAX_TOKENS = 500

    def __init__(self, app=None):
        self.agent = None
        self.extraction_agent = None
        self.max_history = 20
        self.browser_instance = None  # Persistent browser for automation tasks
        if app is not None:
            self.init_app(app)

    def _create_model(self, app):
        """Create model based on provider configuration."""
        provider = app.config["LLM_PROVIDER"].lower()

        if provider == "anthropic":
            api_key = app.config["ANTHROPIC_API_KEY"]
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY is required when using Anthropic provider"
                )

            provider_instance = AnthropicProvider(api_key=api_key)
            return AnthropicModel(
                model_name=self.DEFAULT_MODEL,
                provider=provider_instance,
            )

        elif provider == "openrouter":
            api_key = app.config["OPENROUTER_API_KEY"]
            model_name = app.config["OPENROUTER_MODEL"]

            if not api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY is required when using OpenRouter provider"
                )

            provider_instance = OpenRouterProvider(api_key=api_key)
            return OpenAIChatModel(
                model_name=model_name,
                provider=provider_instance,
            )

        else:
            raise ValueError(
                f"Unsupported LLM provider: {provider}. Supported: 'anthropic',"
                " 'openrouter'"
            )

    def init_app(self, app):
        """Initialise LLM service with app."""
        # Create model based on provider configuration
        model = self._create_model(app)

        # Load instructions from file
        import os

        instructions_path = os.path.join(
            os.path.dirname(app.root_path), "agent_instructions.txt"
        )
        with open(instructions_path, "r", encoding="utf-8") as f:
            instructions_content = f.read()

        # Create the main agent with tools
        self.agent = Agent(
            model=model,
            deps_type=dict,  # We'll pass conversation context as deps
            system_prompt="You are a helpful AI assistant.",
            instructions=instructions_content,
        )

        # Create extraction agent for structured data extraction
        self.extraction_agent = Agent(
            model=model,
            deps_type=dict,
            system_prompt=(
                "You are an expert at extracting and formatting information from text."
                " Output only valid JSON with the requested fields. Do not include any"
                " explanation or additional text."
            ),
        )

        # Add dynamic system prompt for time context
        @self.agent.system_prompt
        def add_time_context(ctx: RunContext[dict]) -> str:
            """Add current time context to system prompt."""
            current_time = datetime.now(ZoneInfo("Pacific/Auckland")).strftime(
                "%A %-d %B %Y, %-I:%M %P"
            )
            return f"The current date and time is {current_time}."

        # Register tools
        self._register_tools()

        provider_name = app.config["LLM_PROVIDER"]
        app.logger.info(
            f"LLMService initialised with Pydantic AI using {provider_name} provider"
        )
        app.extensions["llm"] = self

    def _register_tools(self):
        """Register tools with the agent."""

        @self.agent.tool
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
            conversation_id = ctx.deps.get("conversation_id")
            if not conversation_id:
                return "Error: No conversation context available."

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

        @self.agent.tool
        async def todo_write(ctx: RunContext[dict], tasks: List[Dict[str, str]]) -> str:
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
            conversation_id = ctx.deps.get("conversation_id")
            if not conversation_id:
                return "Error: No conversation context available."

            if not tasks:
                return "No tasks provided."

            # Validate only one task can be in_progress
            in_progress_count = sum(
                1 for task in tasks if task.get("state") == "in_progress"
            )
            if in_progress_count > 1:
                return "Error: Only one task can have 'in_progress' state at a time."

            # Validate required fields and states
            valid_states = {"pending", "in_progress", "completed"}
            for task in tasks:
                if not isinstance(task, dict):
                    return "Error: Each task must be a dictionary."
                if "description" not in task or "state" not in task:
                    return (
                        "Error: Each task must have 'description' and 'state' fields."
                    )
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
                    emoji = {"pending": "⏳", "in_progress": "🔄", "completed": "✅"}[
                        state
                    ]
                    parts.append(f"{count} {state} {emoji}")
                summary += f" ({', '.join(parts)})"

            return summary

        @self.agent.tool
        async def browser_automation(ctx: RunContext[dict], task: str) -> str:
            """Use this tool to automate browser tasks like web navigation, form filling, data extraction, and more.

            This tool uses an AI-powered browser automation agent that can:
            - Navigate to websites and interact with elements
            - Fill out forms and submit data
            - Extract information from web pages
            - Handle complex multi-step workflows
            - Wait for human intervention when needed (2FA, captcha, etc.)

            The browser session is persistent, so authentication and login state is maintained across tasks.

            Args:
                task: A clear description of what you want the browser to do.
                      Examples:
                      - "Go to google.com and search for 'best restaurants near me'"
                      - "Navigate to amazon.com, search for 'wireless headphones', and get the first 3 product details"
                      - "Fill out the contact form on example.com with my information"
                      - "Go to my bank website and check my account balance" (will pause for human login)

            Returns:
                A description of what was accomplished, including any extracted data or final results.
            """
            # Initialize browser if needed
            if self.browser_instance is None:
                self.browser_instance = browser_use.Browser(
                    headless=False,  # Visible so human can intervene
                    keep_alive=True,  # Persistent session
                )

            # Create browser-use agent with same Anthropic model
            api_key = current_app.config["ANTHROPIC_API_KEY"]
            browser_agent = browser_use.Agent(
                task=task,
                llm=browser_use.ChatAnthropic(
                    model=self.DEFAULT_MODEL, api_key=api_key
                ),
                browser=self.browser_instance,
            )

            # Run the browser automation task
            current_app.logger.info(f"Starting browser automation task: {task}")
            history = await browser_agent.run()

            # Extract results
            if history and hasattr(history, "final_result"):
                result = history.final_result()
                if result:
                    success_msg = (
                        f"✅ Browser automation completed successfully:\n{result}"
                    )
                else:
                    success_msg = f"✅ Browser automation task completed: {task}"
            else:
                success_msg = f"✅ Browser automation task completed: {task}"

            # Add screenshot info if available
            if (
                history
                and hasattr(history, "screenshot_paths")
                and history.screenshot_paths()
            ):
                screenshots = history.screenshot_paths()
                success_msg += f"\n📷 Screenshots saved: {len(screenshots)} files"

            current_app.logger.info(f"Browser automation completed: {task}")
            return success_msg

    async def _broadcast_todo_status_update(self):
        """Broadcast todo status update to the UI."""
        # Import here to avoid circular imports
        from src.routes import _broadcast_todo_status

        await _broadcast_todo_status()

    async def respond_with_context(
        self, conversation_id: UUID, messages: list, tools: Optional[List[Dict]] = None
    ):
        """Call the LLM with a specific context and optional tools."""
        current_app.logger.debug(f"LLM call for conversation {conversation_id}")

        conversation = await self._get_conversation(conversation_id)
        deps = {"conversation_id": conversation_id, "conversation": conversation}

        try:
            async with self.agent.run_stream(
                user_prompt="", message_history=messages, deps=deps
            ) as result:
                async for text in result.stream_text():
                    yield text

                # Get the final message with potential usage info
                final_message = await result.get_data()
                await self._update_token_counts(conversation, result)

                # Store result in conversation's pydantic messages
                conversation.store_run_result(result)

                yield final_message

        except Exception as e:
            current_app.logger.error(
                f"Error in LLM response generation: {str(e)}", exc_info=True
            )
            raise

    async def process_and_respond(self, conversation_id: UUID, user_message: str):
        """Process conversation history and generate a response."""
        conversation = await self._get_conversation(conversation_id)

        # Add user message to pydantic history
        conversation.add_user_message(user_message)

        # Get pydantic-ai compatible message history
        message_history = conversation.get_pydantic_messages(last_n=self.max_history)

        current_app.logger.debug(
            f"Conversation history for {conversation_id}:"
            f" {len(message_history)} messages"
        )

        try:
            # Set up context for tools
            deps = {"conversation_id": conversation_id, "conversation": conversation}

            message_id = None

            # Run the agent with streaming
            async with self.agent.run_stream(
                user_prompt=user_message,
                message_history=message_history[:-1],
                deps=deps,
            ) as result:
                async for text in result.stream_text():
                    current_app.logger.debug(f"Received streaming text: {text}...")

                    # Create message placeholder on first chunk, then send updates
                    if message_id is None:
                        message_id = secrets.token_urlsafe(8)
                        await self._send_initial_message(message_id, text)
                    else:
                        # Send out-of-band update to replace content
                        await self._send_message_update(message_id, text)

                # Update token counts
                await self._update_token_counts(conversation, result)

                # Store the run result for future message history
                conversation.store_run_result(result)

        except Exception as e:
            await self._handle_general_error(conversation, e)
        finally:
            await current_app.extensions["event_handler"].emit_to_services(
                "speak_end", conversation_id, {}
            )
            current_app.logger.info(
                f"LLM streaming completed for conversation {conversation_id}"
            )

    async def _send_initial_message(self, message_id: str, content: str):
        """Send the initial message HTML that gets appended to conversation area."""
        from src.routes import _broadcast_event

        html_message = f"""<div class="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-4">
            <div class="font-semibold text-gray-800">Assistant</div>
            <div id="msg-{message_id}-content" class="text-gray-700" sse-swap="message-{message_id}-update">{content}</div>
        </div>"""
        await _broadcast_event("streaming_text", html_message)

    async def _send_message_update(self, message_id: str, content: str):
        """Send out-of-band update to replace message content within existing message."""
        current_app.logger.debug(f"Sending OOB update for {message_id}: {content}")
        from src.routes import _broadcast_event

        html_message = f"""
            <div id="msg-{message_id}-content" class="text-gray-700" sse-swap="message-{message_id}-update"
            hx-swap-oob="true">{content}</div>
        """
        await _broadcast_event(f"message-{message_id}-update", html_message)

    async def _handle_general_error(self, conversation, error):
        """Handle general errors during LLM processing."""
        current_app.logger.error(
            f"Error in LLM response generation: {str(error)}", exc_info=True
        )
        current_app.logger.info("LLM error handled - no response generated")

    async def extract_info(
        self, text: str, extraction_prompt: str, conversation_id: Optional[UUID] = None
    ) -> dict:
        """Extract structured information from text using Claude.

        Args:
            text (str): Text to extract information from
            extraction_prompt (str): Prompt specifying what to extract and how
            conversation_id (UUID, optional): Conversation ID for token tracking

        Returns:
            dict: Extracted information
        """
        user_prompt = f"{extraction_prompt}\n\nText to analyze: {text}"

        deps = {}
        if conversation_id:
            deps["conversation_id"] = conversation_id

        try:
            result = await self.extraction_agent.run(user_prompt=user_prompt, deps=deps)

            # Update token counts if conversation_id provided
            if conversation_id:
                conversation = await self._get_conversation(conversation_id)
                await self._update_token_counts(conversation, result)

            return json.loads(result.data)
        except Exception as e:
            current_app.logger.error(f"Error extracting information: {str(e)}")
            return {}

    async def _get_conversation(self, conversation_id: UUID):
        """Get conversation by ID."""
        conversation_manager = current_app.extensions["conversation_manager"]
        return await conversation_manager.get_conversation(conversation_id)

    async def _update_token_counts(self, conversation, result):
        """Update conversation token counts from LLM response."""
        if hasattr(result, "usage") and result.usage:
            conversation.input_token_count += getattr(result.usage, "input_tokens", 0)
            conversation.output_token_count += getattr(result.usage, "output_tokens", 0)
