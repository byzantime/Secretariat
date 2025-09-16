"""LLMService using Pydantic AI agent framework."""

import os
import secrets
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic_ai import Agent
from pydantic_ai import RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider
from quart import current_app
from quart import render_template

from src.routes import _broadcast_event


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

        app.logger.info("LLMService initialised")
        app.extensions["llm"] = self

    def _register_tools(self):
        """Register tools with the agent."""
        from src.tools.browser_tools import browse_web
        from src.tools.todo_tools import todo_read
        from src.tools.todo_tools import todo_write

        # Register imported tools with the agent
        self.agent.tool(todo_read)
        self.agent.tool(todo_write)
        self.agent.tool(browse_web)

    async def process_and_respond(self, conversation_id: UUID, user_message: str):
        """Process conversation history and generate a response."""
        conversation = await self._get_conversation(conversation_id)

        # Add user message to pydantic history
        conversation.add_user_message(user_message)

        # Get pydantic-ai compatible message history
        message_history = conversation.get_pydantic_messages(last_n=self.max_history)

        current_app.logger.debug(
            f"Conversation history for {conversation_id}: {len(message_history)} messages"
        )

        try:
            # Set up context for tools
            deps = {"conversation_id": conversation_id, "conversation": conversation}

            message_id = None
            full_response = ""

            # Log the start of LLM processing
            current_app.logger.info(
                f"🤖 Starting LLM processing for: {user_message[:100]}..."
            )

            # Use iter for streaming with complete tool execution
            async with self.agent.run_stream(
                user_prompt=user_message,
                message_history=message_history[:-1],
                deps=deps,
            ) as result:
                async for text in result.stream_text():
                    # Accumulate the full response
                    full_response = text

                    # Create message placeholder on first chunk, then send updates
                    if message_id is None:
                        message_id = secrets.token_urlsafe(8)
                        await self._send_initial_message(message_id, text)
                    else:
                        # Send out-of-band update to replace content
                        await self._send_message_update(message_id, text)

                # Log the complete response only after streaming is done
                current_app.logger.debug(
                    f"LLM response completed for conversation {conversation_id}: {full_response}"
                )

            # Log the complete response only after streaming is done
            current_app.logger.debug(
                f"LLM response completed for conversation {conversation_id}: {full_response}"
            )

            # Log tool usage information using correct Pydantic AI message structure
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
                                tool_calls.append(part.tool_name)

            if tool_calls:
                current_app.logger.info(
                    f"🔧 TOOLS USED: {', '.join(set(tool_calls))}"  # Use set to avoid duplicates
                )
            else:
                current_app.logger.info("🚫 NO TOOLS USED in this response")

            # Update token counts
            await self._update_token_counts(conversation, result)

            # Store the run result for future message history
            conversation.store_run_result(result)

        except Exception as e:
            await self._handle_general_error(conversation, e)
        finally:
            current_app.logger.info(
                f"LLM streaming completed for conversation {conversation_id}"
            )

    async def _send_initial_message(self, message_id: str, content: str):
        """Send the initial message HTML that gets appended to conversation area."""
        html_message = await render_template(
            "macros/ui_message.html",
            sender="Assistant",
            content=content,
            message_id=message_id,
            timestamp=datetime.now(),
        )
        await _broadcast_event("streaming_text", html_message)

    async def _send_message_update(self, message_id: str, content: str):
        """Send out-of-band update to replace message content within existing message."""
        html_message = await render_template(
            "macros/ui_message_update.html",
            content=content,
            message_id=message_id,
            oob_swap=True,
        )
        await _broadcast_event(f"message-{message_id}-update", html_message)

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
