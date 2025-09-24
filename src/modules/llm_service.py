"""LLMService using Pydantic AI agent framework."""

import os
import secrets
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic_ai import Agent
from pydantic_ai import RunContext
from pydantic_ai import capture_run_messages
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider
from quart import current_app

from src.tools.browser_tools import browse_web
from src.tools.scheduling_tools import automations_search
from src.tools.scheduling_tools import setup_automation
from src.tools.todo_tools import todo_read
from src.tools.todo_tools import todo_write


class LLMService:
    """Service for interacting with LLMs using Pydantic AI."""

    def __init__(self, app=None):
        self.agent = None
        self.extraction_agent = None
        self.max_history = 20
        if app is not None:
            self.init_app(app)

    def _create_model(self, app):
        """Create model based on provider configuration."""
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

    def init_app(self, app):
        """Initialise LLM service with app."""
        # Create model based on provider configuration
        model = self._create_model(app)

        # Load instructions from file
        instructions_path = os.path.join(
            os.path.dirname(app.root_path), "agent_instructions.txt"
        )
        with open(instructions_path, "r", encoding="utf-8") as f:
            instructions_content = f.read()

        # Create the main agent with tools
        self.agent = Agent(
            model=model,
            retries=3,
            deps_type=dict,  # We'll pass conversation context as deps
            system_prompt="You are a helpful AI assistant.",
            instructions=instructions_content,
        )

        # Create extraction agent for structured data extraction
        self.extraction_agent = Agent(
            model=model,
            retries=3,
            deps_type=dict,
            system_prompt=(
                "You are an expert at extracting and formatting information from text."
                " Output only valid JSON with the requested fields. Do not include any"
                " explanation or additional text."
            ),
        )

        @self.agent.instructions
        def add_time_context(ctx: RunContext[dict]) -> str:
            """Add current time context with explicit guidance for tool usage."""
            current_time = datetime.now(ZoneInfo("Pacific/Auckland")).strftime(
                "%A %-d %B %Y, %-I:%M %P"
            )
            return (
                f"The current date and time is {current_time}.\nIMPORTANT: When"
                " scheduling tasks or generating datetime strings for tools, you MUST"
                f" use the current year ({current_time.split()[-3]}) and current date"
                " as provided above. Do not use outdated years from your training"
                " data."
            )

        # Register tools
        self._register_tools()

        app.logger.info("LLMService initialised")
        app.extensions["llm"] = self

    def _register_tools(self):
        """Register tools with the agent."""
        self.agent.tool(todo_read)
        self.agent.tool(todo_write)
        self.agent.tool(browse_web)
        self.agent.tool(setup_automation)
        self.agent.tool(automations_search)

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

            # Log the start of LLM processing
            current_app.logger.info(
                f"Starting LLM processing for: {user_message[:100]}..."
            )

            # Log current time for debugging
            current_time = datetime.now(ZoneInfo("Pacific/Auckland")).strftime(
                "%A %-d %B %Y, %-I:%M %P"
            )
            current_app.logger.info(f"Current system time: {current_time}")

            # Use the new execute_agent_stream method for interactive processing
            await self.execute_agent_stream(
                agent_instructions=user_message,
                message_history=message_history,
                deps=deps,
                emit_events=True,  # Interactive processing should emit events
                store_result=True,  # Interactive sessions should store results
            )

        except Exception as e:
            # Handle errors for interactive processing
            event_handler = current_app.extensions["event_handler"]
            await event_handler.emit_to_services("llm.error", {"error": str(e)})
            await self._handle_general_error(conversation, e)
        finally:
            current_app.logger.info(
                f"LLM streaming completed for conversation {conversation_id}"
            )

    async def execute_agent_stream(
        self,
        agent_instructions: str,
        message_history: list,
        deps: dict,
        emit_events: bool = True,
        store_result: bool = True,
    ):
        """Core method for executing agent with streaming and optional event emission.

        Args:
            agent_instructions: Instructions for the agent
            message_history: Pydantic-compatible message history
            deps: Dependencies for the agent (conversation context)
            conversation: Conversation object
            emit_events: Whether to emit events for interactive processing
            store_result: Whether to store the run result in conversation

        Returns:
            The agent run result
        """
        # Get event handler for emitting events (only if needed)
        event_handler = current_app.extensions["event_handler"]

        try:
            # Generate message ID for tracking if emitting events
            message_id = None
            full_response = ""

            if emit_events:
                message_id = secrets.token_urlsafe(8)
                # Emit message start event
                await event_handler.emit_to_services(
                    "llm.message.start",
                    {"message_id": message_id, "content": ""},
                )

            # Use capture_run_messages to debug system prompts
            with capture_run_messages() as captured_messages:
                try:
                    # Use streaming for interactive tasks
                    async with self.agent.run_stream(
                        user_prompt=agent_instructions,
                        message_history=message_history[:-1] if message_history else [],
                        deps=deps,
                    ) as result:
                        async for text in result.stream_text():
                            # Accumulate the full response
                            full_response = text

                            # Emit message chunk events for streaming updates (if enabled)
                            if emit_events:
                                await event_handler.emit_to_services(
                                    "llm.message.chunk",
                                    {
                                        "message_id": message_id,
                                        "content": text,
                                    },
                                )
                except Exception as e:
                    current_app.logger.error(f"Error during agent run: {e}")
                    current_app.logger.error(
                        f"Captured messages on error: {captured_messages}"
                    )
                    raise

            if emit_events:
                # Emit message complete event
                await event_handler.emit_to_services(
                    "llm.message.complete",
                    {"message_id": message_id, "content": full_response},
                )

            # Log tool usage information
            tool_calls = []
            if hasattr(result, "new_messages"):
                for msg in result.new_messages():
                    if hasattr(msg, "parts"):
                        for part in msg.parts:
                            # Check for ToolCallPart in message parts
                            if (
                                hasattr(part, "part_kind")
                                and part.part_kind == "tool-call"
                            ):
                                tool_info = {
                                    "tool_name": part.tool_name,
                                    "tool_args": getattr(part, "args", {}),
                                }
                                tool_calls.append(tool_info)

            if tool_calls:
                if emit_events:
                    # Emit tool called events
                    for tool_call in tool_calls:
                        await event_handler.emit_to_services(
                            "llm.tool.called",
                            {
                                "tool_name": tool_call["tool_name"],
                                "tool_args": tool_call["tool_args"],
                            },
                        )
                        current_app.logger.info(f"🔧 TOOL CALLED: {tool_call}")
                # Log summary of unique tools used (always)
                unique_tools = set(tc["tool_name"] for tc in tool_calls)
                current_app.logger.info(f"🔧 TOOLS USED: {', '.join(unique_tools)}")

            conversation = deps.get("conversation")
            # Always update token counts
            if conversation is not None:
                await self._update_token_counts(conversation, result)

            # Store the run result for future message history (if enabled)
            if conversation is not None and store_result:
                conversation.store_run_result(result)

            return result

        except Exception as e:
            if emit_events:
                # Emit error event for interactive tasks
                await event_handler.emit_to_services("llm.error", {"error": str(e)})
            current_app.logger.error(
                f"Error in agent execution: {str(e)}", exc_info=True
            )
            raise

    async def _handle_general_error(self, conversation, error):
        """Handle general errors during LLM processing."""
        current_app.logger.error(
            f"Error in LLM response generation: {str(error)}", exc_info=True
        )
        current_app.logger.info("LLM error handled - no response generated")

    async def _get_conversation(self, conversation_id: UUID):
        """Get conversation by ID."""
        conversation_manager = current_app.extensions["conversation_manager"]
        return await conversation_manager.get_conversation(conversation_id)

    async def _update_token_counts(self, conversation, result):
        """Update conversation token counts from LLM response."""
        if hasattr(result, "usage") and result.usage:
            conversation.input_token_count += getattr(result.usage, "input_tokens", 0)
            conversation.output_token_count += getattr(result.usage, "output_tokens", 0)
