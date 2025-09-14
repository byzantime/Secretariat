"""Tests for LLMService sequence numbering in process_and_respond method."""

import sys
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import uuid4

import pytest

# Mock anthropic module before any imports
mock_anthropic = MagicMock()
# Create mock types with proper structure
mock_anthropic.types = MagicMock()
mock_anthropic.types.Message = type("Message", (), {})
mock_anthropic.APIStatusError = type("APIStatusError", (Exception,), {})
sys.modules["anthropic"] = mock_anthropic

from src.modules.llm_service import LLMService  # noqa: E402


@pytest.fixture
def llm_service():
    """Create an LLMService instance for testing."""
    service = LLMService()
    service.client = MagicMock()
    return service


@pytest.fixture
def conversation_id():
    """Generate a test conversation ID."""
    return uuid4()


@pytest.fixture
def mock_conversation():
    """Create a mock conversation object."""
    conv = MagicMock()
    conv.id = uuid4()
    conv.set_processing_task = MagicMock()
    conv.cancel_processing = AsyncMock()
    return conv


@pytest.fixture
def mock_app_context():
    """Create mock application context."""
    mock_app = MagicMock()
    mock_conversation_manager = MagicMock()
    mock_conversation_manager.get_conversation = AsyncMock()
    mock_event_handler = MagicMock()
    mock_event_handler.emit_to_services = AsyncMock()
    mock_tool_manager = AsyncMock()
    mock_tool_manager.get_available_tools.return_value = []

    mock_app.extensions = {
        "conversation_manager": mock_conversation_manager,
        "event_handler": mock_event_handler,
        "tool_manager": mock_tool_manager,
    }
    mock_app.logger = MagicMock()
    mock_app.logger.debug = MagicMock()
    mock_app.logger.info = MagicMock()

    return mock_app


class TestLLMServiceChunking:
    """Test text chunking and emission in LLM service streaming responses."""

    @pytest.mark.asyncio
    async def test_single_sentence_chunking(
        self, llm_service, conversation_id, mock_conversation, mock_app_context
    ):
        """Test that a single sentence response is emitted correctly."""
        # Setup mock conversation manager
        mock_app_context.extensions[
            "conversation_manager"
        ].get_conversation.return_value = mock_conversation

        # Track emit_llm_chunk calls
        emitted_chunks = []

        async def mock_emit_llm_chunk(conversation, chunk):
            emitted_chunks.append({"chunk": chunk})

        # Mock streaming response - single sentence that's long enough to trigger emission
        async def mock_stream():
            yield (
                "This is a single sentence response that is longer than thirty"
                " characters."
            )

        with patch("src.modules.llm_service.current_app", mock_app_context):
            with patch.object(
                llm_service, "respond_with_context", return_value=mock_stream()
            ):
                with patch.object(
                    llm_service, "emit_llm_chunk", side_effect=mock_emit_llm_chunk
                ):
                    await llm_service.process_and_respond(conversation_id)

        # Should have one chunk with the expected content
        assert len(emitted_chunks) == 1
        assert "This is a single sentence response" in emitted_chunks[0]["chunk"]

    @pytest.mark.asyncio
    async def test_multi_sentence_chunking(
        self, llm_service, conversation_id, mock_conversation, mock_app_context
    ):
        """Test that multi-sentence responses are emitted as separate chunks."""
        # Setup mock conversation manager
        mock_app_context.extensions[
            "conversation_manager"
        ].get_conversation.return_value = mock_conversation

        # Track emit_llm_chunk calls
        emitted_chunks = []

        async def mock_emit_llm_chunk(conversation, chunk):
            emitted_chunks.append({"chunk": chunk})

        # Mock streaming response - multi-sentence
        async def mock_stream():
            yield "First sentence. Second sentence. Third"
            yield " sentence. Fourth sentence."

        with patch("src.modules.llm_service.current_app", mock_app_context):
            with patch.object(
                llm_service, "respond_with_context", return_value=mock_stream()
            ):
                with patch.object(
                    llm_service, "emit_llm_chunk", side_effect=mock_emit_llm_chunk
                ):
                    await llm_service.process_and_respond(conversation_id)

        # Should have multiple chunks
        assert len(emitted_chunks) >= 3  # At least first, second, and final chunks

        # Verify chunks contain expected content
        chunk_texts = [chunk["chunk"] for chunk in emitted_chunks]
        combined_text = "".join(chunk_texts)
        assert "First sentence." in combined_text
        assert "Second sentence." in combined_text
        assert "Third sentence." in combined_text
        assert "Fourth sentence." in combined_text

    @pytest.mark.asyncio
    async def test_final_chunk_emission(
        self, llm_service, conversation_id, mock_conversation, mock_app_context
    ):
        """Test that the final chunk is emitted correctly."""
        # Setup mock conversation manager
        mock_app_context.extensions[
            "conversation_manager"
        ].get_conversation.return_value = mock_conversation

        # Track emit_llm_chunk calls
        emitted_chunks = []

        async def mock_emit_llm_chunk(conversation, chunk):
            emitted_chunks.append({"chunk": chunk})

        # Mock streaming response that creates multiple chunks with a final partial
        async def mock_stream():
            yield "Complete sentence one. Complete sentence two. Partial"
            yield " final text"  # This will become the final chunk

        with patch("src.modules.llm_service.current_app", mock_app_context):
            with patch.object(
                llm_service, "respond_with_context", return_value=mock_stream()
            ):
                with patch.object(
                    llm_service, "emit_llm_chunk", side_effect=mock_emit_llm_chunk
                ):
                    await llm_service.process_and_respond(conversation_id)

        # Should have at least 3 chunks: sentence one, sentence two, final partial
        assert len(emitted_chunks) >= 3

        # Final chunk should contain the partial text
        final_chunk = emitted_chunks[-1]
        assert "final text" in final_chunk["chunk"]

        # Verify all content is emitted
        combined_text = "".join(chunk["chunk"] for chunk in emitted_chunks)
        assert "Complete sentence one." in combined_text
        assert "Complete sentence two." in combined_text
        assert "Partial final text" in combined_text

    @pytest.mark.asyncio
    async def test_buffer_threshold_processing(
        self, llm_service, conversation_id, mock_conversation, mock_app_context
    ):
        """Test chunk emission with text that crosses the 30-character threshold."""
        # Setup mock conversation manager
        mock_app_context.extensions[
            "conversation_manager"
        ].get_conversation.return_value = mock_conversation

        # Track emit_llm_chunk calls
        emitted_chunks = []

        async def mock_emit_llm_chunk(conversation, chunk):
            emitted_chunks.append({"chunk": chunk})

        # Mock streaming response with incremental builds that cross 30-char threshold
        async def mock_stream():
            yield "Short."  # 6 chars - won't trigger
            yield " More text to reach threshold."  # Total: 37 chars - will trigger
            yield " Final sentence."  # Additional content

        with patch("src.modules.llm_service.current_app", mock_app_context):
            with patch.object(
                llm_service, "respond_with_context", return_value=mock_stream()
            ):
                with patch.object(
                    llm_service, "emit_llm_chunk", side_effect=mock_emit_llm_chunk
                ):
                    await llm_service.process_and_respond(conversation_id)

        # Should have emitted chunks when threshold is crossed
        assert len(emitted_chunks) >= 1

        # Verify content is emitted correctly
        combined_text = "".join(chunk["chunk"] for chunk in emitted_chunks)
        assert "Short." in combined_text
        assert "More text to reach threshold." in combined_text

    @pytest.mark.asyncio
    async def test_multiple_chunks_in_single_iteration(
        self, llm_service, conversation_id, mock_conversation, mock_app_context
    ):
        """Test chunk emission when multiple sentences are processed in a single iteration."""
        # Setup mock conversation manager
        mock_app_context.extensions[
            "conversation_manager"
        ].get_conversation.return_value = mock_conversation

        # Track emit_llm_chunk calls
        emitted_chunks = []

        async def mock_emit_llm_chunk(conversation, chunk):
            emitted_chunks.append({"chunk": chunk})

        # Mock streaming response that produces multiple complete sentences at once
        async def mock_stream():
            yield "First sentence. Second sentence. Third sentence. Fourth sentence."

        with patch("src.modules.llm_service.current_app", mock_app_context):
            with patch.object(
                llm_service, "respond_with_context", return_value=mock_stream()
            ):
                with patch.object(
                    llm_service, "emit_llm_chunk", side_effect=mock_emit_llm_chunk
                ):
                    await llm_service.process_and_respond(conversation_id)

        # Should have multiple chunks
        assert len(emitted_chunks) >= 3

        # Verify all sentences are emitted
        combined_text = "".join(chunk["chunk"] for chunk in emitted_chunks)
        assert "First sentence." in combined_text
        assert "Second sentence." in combined_text
        assert "Third sentence." in combined_text
        assert "Fourth sentence." in combined_text

    @pytest.mark.asyncio
    async def test_empty_final_chunk_handling(
        self, llm_service, conversation_id, mock_conversation, mock_app_context
    ):
        """Test that empty final chunks are not emitted."""
        # Setup mock conversation manager
        mock_app_context.extensions[
            "conversation_manager"
        ].get_conversation.return_value = mock_conversation

        # Track emit_llm_chunk calls
        emitted_chunks = []

        async def mock_emit_llm_chunk(conversation, chunk):
            emitted_chunks.append({"chunk": chunk})

        # Mock streaming response that ends with complete sentences (no partial)
        async def mock_stream():
            yield "Complete sentence one. Complete sentence two."

        with patch("src.modules.llm_service.current_app", mock_app_context):
            with patch.object(
                llm_service, "respond_with_context", return_value=mock_stream()
            ):
                with patch.object(
                    llm_service, "emit_llm_chunk", side_effect=mock_emit_llm_chunk
                ):
                    await llm_service.process_and_respond(conversation_id)

        # Verify all emitted chunks have content (no empty chunks)
        for chunk_data in emitted_chunks:
            assert chunk_data["chunk"].strip()  # Should not be empty

        # Verify expected content is present
        combined_text = "".join(chunk["chunk"] for chunk in emitted_chunks)
        assert "Complete sentence one." in combined_text
        assert "Complete sentence two." in combined_text

    @pytest.mark.asyncio
    async def test_chunk_emission_across_buffer_cycles(
        self, llm_service, conversation_id, mock_conversation, mock_app_context
    ):
        """Test that chunks are emitted correctly across multiple buffer processing cycles."""
        # Setup mock conversation manager
        mock_app_context.extensions[
            "conversation_manager"
        ].get_conversation.return_value = mock_conversation

        # Track emit_llm_chunk calls
        emitted_chunks = []

        async def mock_emit_llm_chunk(conversation, chunk):
            emitted_chunks.append({"chunk": chunk})

        # Mock streaming response with multiple yield cycles
        async def mock_stream():
            # First cycle - will trigger processing and emission
            yield "First complete sentence. Second complete sentence."
            # Second cycle - should continue sequence numbering
            yield " Third complete sentence. Fourth"
            # Third cycle - final chunk
            yield " complete sentence."

        with patch("src.modules.llm_service.current_app", mock_app_context):
            with patch.object(
                llm_service, "respond_with_context", return_value=mock_stream()
            ):
                with patch.object(
                    llm_service, "emit_llm_chunk", side_effect=mock_emit_llm_chunk
                ):
                    await llm_service.process_and_respond(conversation_id)

        # Should have multiple chunks from different processing cycles
        assert len(emitted_chunks) >= 3

        # Verify all content is emitted correctly across cycles
        combined_text = "".join(chunk["chunk"] for chunk in emitted_chunks)
        assert "First complete sentence." in combined_text
        assert "Second complete sentence." in combined_text
        assert "Third complete sentence." in combined_text
        assert "Fourth complete sentence." in combined_text

    @pytest.mark.asyncio
    async def test_emit_llm_chunk_parameters(
        self, llm_service, conversation_id, mock_conversation, mock_app_context
    ):
        """Test that emit_llm_chunk is called with correct parameters."""
        # Setup mock conversation manager
        mock_app_context.extensions[
            "conversation_manager"
        ].get_conversation.return_value = mock_conversation

        # Track emit_llm_chunk calls with full parameter details
        emit_calls = []

        async def mock_emit_llm_chunk(conversation, chunk):
            emit_calls.append({"conversation_id": conversation.id, "chunk": chunk})

        # Mock streaming response
        async def mock_stream():
            yield "Test sentence. Another sentence."

        with patch("src.modules.llm_service.current_app", mock_app_context):
            with patch.object(
                llm_service, "respond_with_context", return_value=mock_stream()
            ):
                with patch.object(
                    llm_service, "emit_llm_chunk", side_effect=mock_emit_llm_chunk
                ):
                    await llm_service.process_and_respond(conversation_id)

        # Verify emit_llm_chunk was called with correct parameters
        assert len(emit_calls) >= 1

        for call in emit_calls:
            # Conversation should be the mock conversation
            assert call["conversation_id"] == mock_conversation.id
            # Chunk should be non-empty string
            assert isinstance(call["chunk"], str)
            assert call["chunk"].strip()

        # Verify expected content is present
        all_chunks = "".join(call["chunk"] for call in emit_calls)
        assert "Test sentence." in all_chunks
        assert "Another sentence." in all_chunks
