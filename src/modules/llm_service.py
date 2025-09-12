"""LLMService with sentence-based text chunking."""

import asyncio
import json
from datetime import datetime
from typing import Dict
from typing import List
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

import anthropic
import httpx
from anthropic import AsyncAnthropic
from quart import current_app

from src.modules.decorators import processing_state
from src.modules.text_utils import chunk_text_by_sentence


class LLMService:
    """Service for interacting with Anthropic's Claude LLM."""

    # Constants
    DEFAULT_MODEL = "claude-3-haiku-20240307"
    DEFAULT_MAX_TOKENS = 1000
    DEFAULT_TEMPERATURE = 0
    CHUNK_SIZE_THRESHOLD = 30
    EXTRACTION_MAX_TOKENS = 500

    def __init__(self, app=None):
        self.client = None
        self.max_history = 20  # Adjust as needed
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialise LLM service with app."""
        api_key = app.config["ANTHROPIC_API_KEY"]
        # Custom HTTP client with optimized settings
        http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=30.0,
            ),
            timeout=30.0,
            http2=True,  # Enable HTTP/2
        )
        self.client = AsyncAnthropic(
            api_key=api_key,
            max_retries=1,
            http_client=http_client,
        )
        app.logger.info("LLMService initialised with Anthropic API")
        app.extensions["llm"] = self

    async def respond_with_context(
        self, conversation_id: UUID, messages: list, tools: Optional[List[Dict]] = None
    ):
        """Call the LLM with a specific context and optional tools."""
        current_app.logger.debug(f"LLM call for conversation {conversation_id}")

        # Build system prompt and request parameters
        conversation = await self._get_conversation(conversation_id)
        system_prompt = await self._build_system_prompt(conversation)
        request_params = self._build_request_params(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
        )

        self._log_request_debug(conversation.id, system_prompt, tools)

        async with self.client.messages.stream(**request_params) as stream:
            async for text in stream.text_stream:
                yield text

        # Update token counts and yield final message
        final_message = await stream.get_final_message()
        await self._update_token_counts(conversation, final_message)
        yield final_message

    async def emit_llm_chunk(self, conversation, chunk: str):
        """Emit an LLM chunk event for TTS consumption."""
        current_app.logger.debug(
            f"LLM emitting text for conversation {conversation.id}: '{chunk}'"
        )
        data = {"text": chunk}
        await current_app.extensions["event_handler"].emit_to_services(
            "speak_stream", conversation.id, data
        )

    @processing_state("LLM")
    async def process_and_respond(self, conversation_id: UUID):
        """Process conversation history and generate a response."""
        conversation = await self._get_conversation(conversation_id)
        conversation_history = await conversation.get_convo_history_for_llm(
            last_n=self.max_history,
        )
        current_app.logger.debug(
            f"Conversation history for {conversation_id}: {conversation_history}"
        )

        # Get available tools
        tool_manager = current_app.extensions["tool_manager"]
        tools = await tool_manager.get_available_tools(conversation)

        try:
            # Iteratively handle LLM responses and tool use until completion
            max_iterations = 5  # Prevent infinite loops
            iteration = 0
            total_buffer = ""

            while iteration < max_iterations:
                # Generate streaming response with tool handling
                buffer, tool_used = await self._generate_streaming_response(
                    conversation, conversation_history, tools
                )
                total_buffer += buffer

                # If no tool was used, we're done
                if not tool_used:
                    break

                # Check if conversation was interrupted
                if await conversation.is_interrupted():
                    break

                # Get updated conversation history and tools for next iteration
                conversation_history = await conversation.get_convo_history_for_llm(
                    last_n=self.max_history
                )
                current_app.logger.debug(
                    f"Conversation history for {conversation_id}:"
                    f" {conversation_history}"
                )
                tool_manager = current_app.extensions["tool_manager"]
                tools = await tool_manager.get_available_tools(conversation)

                iteration += 1
                current_app.logger.debug(
                    f"Tool use iteration {iteration} for conversation {conversation_id}"
                )

            # Only finalize response in conversation history if no tool was used in final iteration
            # (tools handle their own response text and history updates)
            if not tool_used and total_buffer.strip():
                asyncio.create_task(
                    conversation.add_to_role_convo_history(
                        "assistant",
                        total_buffer,
                        final=True,
                    )
                )

        except anthropic.APIStatusError as e:
            await self._handle_general_error(conversation, e)
        except asyncio.CancelledError:
            current_app.logger.info(
                f"LLM response processing cancelled for conversation {conversation_id}"
            )
        except Exception as e:
            await self._handle_general_error(conversation, e)
        finally:
            await current_app.extensions["event_handler"].emit_to_services(
                "speak_end", conversation_id, {}
            )
            current_app.logger.info(
                f"LLM streaming completed for conversation {conversation_id}"
            )

    async def _generate_streaming_response(
        self,
        conversation,
        conversation_history: list,
        tools: list,
    ) -> tuple[str, bool]:
        """Generate streaming response with tool handling."""
        buffer = ""
        last_emit = 0  # Track position of last emit
        final_message = None
        tool_used = False

        # Initial streaming response
        async for text in self.respond_with_context(
            conversation.id, conversation_history, tools
        ):
            if isinstance(text, anthropic.types.Message):
                # This is the final message with potential tool use
                final_message = text
                break

            buffer += text
            current_length = len(buffer)

            # Process and emit text chunks
            last_emit = await self._process_text_chunks(
                conversation, buffer, last_emit, current_length
            )

        # Handle tool use if present
        if final_message and final_message.stop_reason == "tool_use":
            tool_used = True
            # Extract any text content from the final message before tool execution
            text_content = ""
            for content_block in final_message.content:
                if content_block.type == "text":
                    text_content += content_block.text

            if text_content:
                buffer += text_content
                current_length = len(buffer)

                # Process text content through normal chunking pipeline for consistent streaming
                last_emit = await self._process_text_chunks(
                    conversation, buffer, last_emit, current_length
                )

            # Execute tools - tools now handle their own response text and history updates
            await self._handle_tool_use(final_message, conversation)

            # Signal that tool results need follow-up processing
            # The iterative loop in process_and_respond will handle this
        else:
            # Process any remaining text (only if not interrupted and no tool used)
            await self._emit_remaining_text(conversation, buffer, last_emit)

        return buffer, tool_used

    async def _emit_remaining_text(self, conversation, buffer: str, last_emit: int):
        """Emit any remaining text if not interrupted."""
        if not await conversation.is_interrupted():
            remaining_text = buffer[last_emit:].strip()
            if remaining_text:
                current_app.logger.debug(
                    f"LLM emitting final chunk: '{remaining_text[:50]}...'"
                )
                await self.emit_llm_chunk(conversation, remaining_text)

    async def _handle_general_error(self, conversation, error):
        """Handle general errors during LLM processing."""
        current_app.logger.error(
            f"Error in LLM response generation: {str(error)}", exc_info=True
        )
        # For skeleton app, just log the error without generating excuses
        current_app.logger.info("LLM error handled - no response generated")

    async def _call_llm(
        self,
        system_prompt: str,
        messages: list,
        max_tokens: int = None,
        temperature: float = None,
        conversation_id: Optional[UUID] = None,
        tools: Optional[List[Dict]] = None,
    ):
        """Make a basic call to Claude LLM.

        Returns:
            str: Generated response
        """
        try:
            request_params = self._build_request_params(
                system_prompt=system_prompt,
                messages=messages,
                max_tokens=max_tokens or self.DEFAULT_MAX_TOKENS,
                temperature=(
                    temperature if temperature is not None else self.DEFAULT_TEMPERATURE
                ),
                tools=tools,
            )

            response = await self.client.messages.create(**request_params)

            # Track tokens from response usage
            if conversation_id is not None:
                conversation = await self._get_conversation(conversation_id)
                await self._update_token_counts(conversation, response)

            return response.content[0].text
        except Exception as e:
            current_app.logger.error(f"Error in LLM call: {str(e)}")
            raise

    async def extract_info(
        self, text: str, extraction_prompt: str, conversation_id: Optional[UUID] = None
    ) -> dict:
        """Extract structured information from text using Claude.

        Args:
            text (str): Text to extract information from
            extraction_prompt (str): Prompt specifying what to extract and how

        Returns:
            dict: Extracted information
        """
        system_prompt = """You are an expert at extracting and formatting information from text.
        Output only valid JSON with the requested fields. Do not include any explanation or additional text."""

        messages = [{
            "role": "user",
            "content": f"{extraction_prompt}\n\nText to analyze: {text}",
        }]
        current_app.logger.debug(f"MESSAGES!!! {messages}")
        try:
            response = await self._call_llm(
                system_prompt=system_prompt,
                messages=messages,
                temperature=0,  # Use 0 for consistent extraction
                max_tokens=self.EXTRACTION_MAX_TOKENS,
                conversation_id=conversation_id,
            )
            return json.loads(response)
        except Exception as e:
            current_app.logger.error(f"Error extracting information: {str(e)}")
            return {}

    async def _handle_tool_use(
        self, message: anthropic.types.Message, conversation
    ) -> Optional[List[Dict]]:
        """Handle tool use in LLM response and store in conversation history."""
        import json

        # Log conversation history before tool processing
        history_before = await conversation.get_convo_history_for_llm()
        current_app.logger.debug(
            "Conversation history BEFORE tool processing for"
            f" {conversation.id}:\n{json.dumps(history_before, indent=2)}"
        )

        tool_manager = current_app.extensions["tool_manager"]
        tool_results = []

        # Convert the full message content to content blocks format and store
        text_blocks = []
        tool_blocks = []

        for content_block in message.content:
            if content_block.type == "text":
                text_blocks.append({"type": "text", "text": content_block.text})
            elif content_block.type == "tool_use":
                tool_blocks.append({
                    "type": "tool_use",
                    "id": content_block.id,
                    "name": content_block.name,
                    "input": content_block.input,
                })

        # Store the assistant message with all content in conversation history
        await conversation.add_to_conversation_history({
            "role": "assistant",
            "content": text_blocks + tool_blocks,
            "final": True,
        })

        # Execute tools and collect results
        for content_block in message.content:
            if content_block.type == "tool_use":
                tool_name = content_block.name
                tool_input = content_block.input
                tool_use_id = content_block.id

                current_app.logger.info(
                    f"Executing tool '{tool_name}' with input: {tool_input}"
                )

                # Execute the tool (ToolManager now returns (result_text, is_error))
                result_text, is_error = await tool_manager.execute_tool(
                    tool_name, tool_input, conversation
                )

                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result_text,
                }

                if is_error:
                    tool_result["is_error"] = True

                tool_results.append(tool_result)

        # Store tool results in conversation history
        if tool_results:
            await conversation.add_to_conversation_history({
                "role": "user",
                "content": tool_results,
                "final": True,
            })

        # Verify tool_use/tool_result ID matching
        tool_use_ids = []
        for content_block in message.content:
            if content_block.type == "tool_use":
                tool_use_ids.append(content_block.id)

        tool_result_ids = [result["tool_use_id"] for result in tool_results]

        current_app.logger.debug(
            f"Tool ID verification for {conversation.id}:\n"
            f"Tool use IDs: {tool_use_ids}\n"
            f"Tool result IDs: {tool_result_ids}\n"
            f"IDs match: {set(tool_use_ids) == set(tool_result_ids)}"
        )

        # Log conversation history after tool processing
        history_after = await conversation.get_convo_history_for_llm()
        current_app.logger.debug(
            "Conversation history AFTER tool processing for"
            f" {conversation.id}:\n{json.dumps(history_after, indent=2)}"
        )

        return tool_results if tool_results else None

    async def _get_conversation(self, conversation_id: UUID):
        """Get conversation by ID."""
        conversation_manager = current_app.extensions["conversation_manager"]
        return await conversation_manager.get_conversation(conversation_id)

    async def _build_system_prompt(self, conversation) -> str:
        """Build system prompt with time context."""
        current_time = datetime.now(ZoneInfo("Pacific/Auckland")).strftime(
            "%A %-d %B %Y, %-I:%M %P"
        )
        time_context = f"The current date and time is {current_time}.\n\n"
        system_prompt = "You are a helpful AI assistant. Be friendly and informative."
        return time_context + system_prompt

    def _build_request_params(
        self,
        system_prompt: str,
        messages: list,
        max_tokens: int = None,
        temperature: float = None,
        tools: Optional[List[Dict]] = None,
    ) -> Dict:
        """Build request parameters for LLM API calls."""
        params = {
            "model": self.DEFAULT_MODEL,
            "max_tokens": max_tokens or self.DEFAULT_MAX_TOKENS,
            "temperature": temperature or self.DEFAULT_TEMPERATURE,
            "system": system_prompt,
            "messages": messages,
        }

        if tools:
            params["tools"] = tools

        return params

    async def _update_token_counts(self, conversation, message_or_response):
        """Update conversation token counts from LLM response."""
        if hasattr(message_or_response, "usage"):
            conversation.input_token_count += message_or_response.usage.input_tokens
            conversation.output_token_count += message_or_response.usage.output_tokens

    def _log_request_debug(
        self,
        conversation_id: str,
        system_prompt: str,
        tools: Optional[List[Dict]],
    ):
        """Log debug information for LLM request."""

        current_app.logger.debug(
            "\n==============================================\n"
            f"LLM request for conversation {conversation_id}:"
            f"\nSystem prompt:\n{system_prompt}"
            f"\nTools available: {len(tools) if tools else 0}"
            "\n=============================================="
        )

    async def _process_text_chunks(
        self, conversation, buffer: str, last_emit: int, current_length: int
    ) -> int:
        """Process and emit text chunks for streaming response."""
        # Only process new content since last emit
        if current_length - last_emit <= self.CHUNK_SIZE_THRESHOLD:
            return last_emit

        new_content = buffer[last_emit:]
        chunks = chunk_text_by_sentence(new_content)
        if not chunks:
            return last_emit

        # Only emit complete sentences, keep last chunk in buffer
        completed_chunks = chunks[:-1]
        chars_processed = 0

        for chunk in completed_chunks:
            if await conversation.is_interrupted():
                break
            current_app.logger.debug(f"LLM emitting chunk: '{chunk[:50]}...'")
            await self.emit_llm_chunk(conversation, chunk)
            asyncio.create_task(
                conversation.add_to_role_convo_history(
                    "assistant",
                    buffer,
                    final=False,
                )
            )
            # Find the actual end position of this chunk in new_content
            chunk_end = new_content.find(chunk, chars_processed) + len(chunk)
            chars_processed = chunk_end

        # Return updated last_emit position
        return last_emit + chars_processed
