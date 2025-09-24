"""Unit tests for memory tools, specifically testing conversation filtering."""

import time
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import pytest_asyncio
from pydantic_ai import RunContext

from src.tools.memory_tools import memory_search


# Import fixtures from memory tests
@pytest.fixture
def mock_vector_generator():
    """Mock vector generator that returns predictable vectors."""
    mock_gen = MagicMock()

    # Return predictable vectors for testing - sync function
    def sync_generate_all(*args, **kwargs):
        return {
            "semantic": [0.1] * 384,  # Standard sentence transformer size
            "temporal": [0.2] * 20,  # Hour patterns
            "contextual": [0.3] * 100,  # Context features
            "role": [0.4] * 1,  # Role vector
        }

    mock_gen.generate_all = sync_generate_all
    return mock_gen


@pytest.fixture
def mock_sentiment_analyzer():
    """Mock sentiment analyzer for consistent emotional charge."""
    mock_analyzer = MagicMock()

    # Return consistent sentiment scores
    mock_analyzer.polarity_scores.return_value = {
        "compound": 0.5,
        "pos": 0.3,
        "neu": 0.4,
        "neg": 0.3,
    }
    return mock_analyzer


@pytest.fixture
def mock_app():
    """Mock Quart app with required configuration and extensions."""
    mock_app = MagicMock()

    # Configure app config
    mock_app.config = {
        "QDRANT_HOST": ":memory:",
        "QDRANT_PORT": 6333,
        "QDRANT_API_KEY": None,
        "MEMORY_COLLECTION_NAME": "test_memories",
    }

    # Mock logger
    mock_app.logger = MagicMock()
    mock_app.logger.info = MagicMock()
    mock_app.logger.debug = MagicMock()

    # Mock extensions
    mock_event_handler = MagicMock()
    mock_event_handler.on = MagicMock()

    mock_communication_service = MagicMock()
    mock_communication_service.current_conversation = None

    mock_app.extensions = {
        "event_handler": mock_event_handler,
        "communication_service": mock_communication_service,
    }
    return mock_app


@pytest_asyncio.fixture
async def memory_system(mock_app, mock_vector_generator, mock_sentiment_analyzer):
    """Create a MemoryService instance with in-memory Qdrant and mocked dependencies."""
    from src.modules import memory

    with (
        patch("src.modules.memory.VectorGenerator", return_value=mock_vector_generator),
        patch(
            "src.modules.memory.SentimentIntensityAnalyzer",
            return_value=mock_sentiment_analyzer,
        ),
        patch.object(memory, "current_app", mock_app),
    ):
        from src.modules.memory import MemoryService

        # Use new Quart extension pattern
        system = MemoryService()
        system.init_app(mock_app)
        await system._setup_collection()
        return system


@pytest.fixture
def sample_vectors():
    """Sample vectors for testing."""
    return {
        "semantic": [0.1] * 384,
        "temporal": [0.2] * 20,
        "contextual": [0.3] * 100,
        "role": [0.4] * 1,
    }


@pytest.fixture
def mock_conversation():
    """Mock conversation object with an ID."""
    mock_conv = MagicMock()
    mock_conv.id = "test-conversation-123"
    return mock_conv


@pytest.fixture
def mock_run_context_with_conversation(mock_conversation):
    """Mock RunContext with a conversation dependency."""
    mock_ctx = MagicMock(spec=RunContext)
    mock_ctx.deps = {"conversation": mock_conversation}
    return mock_ctx


@pytest.fixture
def mock_run_context_no_conversation():
    """Mock RunContext without a conversation dependency."""
    mock_ctx = MagicMock(spec=RunContext)
    mock_ctx.deps = {}
    return mock_ctx


@pytest_asyncio.fixture
async def memory_system_with_conversations(memory_system, sample_vectors):
    """Memory system with pre-stored memories from different conversations."""
    time.time()

    # Store memories from current conversation (conversation-123)
    current_conv_memories = [
        "This is from the current conversation",
        "Another message from current conversation",
        "Current conversation discussion about AI",
    ]

    current_conv_ids = []
    for content in current_conv_memories:
        memory_id = await memory_system.store_memory(
            content=content,
            vectors=sample_vectors,
            context_tags=["current", "test"],
            role="user",
            conversation_id="test-conversation-123",
        )
        current_conv_ids.append(memory_id)

    # Store memories from other conversations
    other_conv_memories = [
        ("This is from another conversation", "other-conversation-456"),
        ("Different conversation about programming", "other-conversation-456"),
        ("Old conversation about databases", "old-conversation-789"),
        ("Previous discussion about memory systems", "old-conversation-789"),
    ]

    other_conv_ids = []
    for content, conv_id in other_conv_memories:
        memory_id = await memory_system.store_memory(
            content=content,
            vectors=sample_vectors,
            context_tags=["other", "test"],
            role="user",
            conversation_id=conv_id,
        )
        other_conv_ids.append(memory_id)

    return {
        "memory_system": memory_system,
        "current_conv_ids": current_conv_ids,
        "other_conv_ids": other_conv_ids,
        "current_conversation_id": "test-conversation-123",
    }


class TestMemorySearchConversationFiltering:
    """Test cases for memory search conversation filtering functionality."""

    @pytest.mark.asyncio
    async def test_memory_search_filters_current_conversation(
        self, memory_system_with_conversations, mock_run_context_with_conversation
    ):
        """Test that memories from current conversation are filtered out."""
        setup = memory_system_with_conversations

        mock_app = MagicMock()
        mock_app.extensions = {"memory": setup["memory_system"]}
        mock_app.logger = MagicMock()

        with patch("src.tools.memory_tools.current_app", mock_app):
            # Search for memories (should exclude current conversation)
            result = await memory_search(
                mock_run_context_with_conversation, "conversation about programming"
            )

            # Verify result contains memories from other conversations only
            assert "Found" in result  # Should find some memories
            assert (
                "This is from another conversation" in result
                or "Different conversation about programming" in result
            )

            # Verify current conversation memories are not in results
            assert "This is from the current conversation" not in result
            assert "Another message from current conversation" not in result
            assert "Current conversation discussion about AI" not in result

    @pytest.mark.asyncio
    async def test_memory_search_includes_other_conversations(
        self, memory_system_with_conversations, mock_run_context_with_conversation
    ):
        """Test that memories from other conversations are included in results."""
        setup = memory_system_with_conversations

        mock_app = MagicMock()
        mock_app.extensions = {"memory": setup["memory_system"]}
        mock_app.logger = MagicMock()

        with patch("src.tools.memory_tools.current_app", mock_app):

            # Search for memories
            result = await memory_search(
                mock_run_context_with_conversation, "conversation"
            )

            # Should find memories from other conversations
            assert "Found" in result  # Should find some memories
            assert "No relevant memories found" not in result

            # Verify it contains memories from other conversations
            other_conversation_content = [
                "This is from another conversation",
                "Different conversation about programming",
                "Old conversation about databases",
                "Previous discussion about memory systems",
            ]

            found_other_content = any(
                content in result for content in other_conversation_content
            )
            assert found_other_content, "Should find content from other conversations"

    @pytest.mark.asyncio
    async def test_memory_search_no_conversation_context(
        self, memory_system_with_conversations, mock_run_context_no_conversation
    ):
        """Test memory search when no conversation context is available."""
        setup = memory_system_with_conversations

        mock_app = MagicMock()
        mock_app.extensions = {"memory": setup["memory_system"]}
        mock_app.logger = MagicMock()

        with patch("src.tools.memory_tools.current_app", mock_app):

            # Search without conversation context (should return all memories)
            result = await memory_search(
                mock_run_context_no_conversation, "conversation"
            )

            # Should find memories from all conversations since no filter is applied
            assert "Found" in result

            # Should potentially include memories from all conversations
            all_content = [
                "This is from the current conversation",
                "This is from another conversation",
                "Old conversation about databases",
            ]

            # At least some content should be found
            found_any_content = any(content in result for content in all_content)
            assert found_any_content

    @pytest.mark.asyncio
    async def test_memory_search_empty_results(
        self, memory_system, mock_run_context_with_conversation
    ):
        """Test memory search when no relevant memories exist."""
        mock_app = MagicMock()
        mock_app.extensions = {"memory": memory_system}
        mock_app.logger = MagicMock()

        with patch("src.tools.memory_tools.current_app", mock_app):

            # Search in empty memory system
            result = await memory_search(
                mock_run_context_with_conversation, "nonexistent topic"
            )

            # Should return no results message
            assert "No relevant memories found" in result

    @pytest.mark.asyncio
    async def test_memory_search_memory_service_unavailable(
        self, mock_run_context_with_conversation, mock_app
    ):
        """Test memory search when memory service is unavailable."""
        mock_memory_service = MagicMock()
        mock_memory_service.is_available.return_value = False

        mock_app.extensions = {"memory": mock_memory_service}
        mock_app.logger = MagicMock()

        with patch("src.tools.memory_tools.current_app", mock_app):
            result = await memory_search(
                mock_run_context_with_conversation, "any query"
            )

            assert "Memory search is not available" in result

    @pytest.mark.asyncio
    async def test_memory_search_conversation_filter_structure(
        self, memory_system_with_conversations, mock_run_context_with_conversation
    ):
        """Test that the conversation filter is structured correctly."""
        setup = memory_system_with_conversations

        mock_app = MagicMock()
        mock_app.extensions = {"memory": setup["memory_system"]}
        mock_app.logger = MagicMock()

        with patch("src.tools.memory_tools.current_app", mock_app):

            # Mock the retrieve_memories method to capture the filter
            original_retrieve = setup["memory_system"].retrieve_memories
            called_filters = []

            async def mock_retrieve(query_vectors, limit, query_filter=None):
                called_filters.append(query_filter)
                return await original_retrieve(query_vectors, limit, query_filter)

            setup["memory_system"].retrieve_memories = mock_retrieve

            # Execute search
            await memory_search(mock_run_context_with_conversation, "test query")

            # Verify filter structure
            assert len(called_filters) == 1
            filter_obj = called_filters[0]
            assert filter_obj is not None
            assert hasattr(filter_obj, "must_not")
            assert len(filter_obj.must_not) == 1

            # Verify the filter targets conversation_id
            field_condition = filter_obj.must_not[0]
            assert hasattr(field_condition, "key")
            assert field_condition.key == "conversation_id"
            assert hasattr(field_condition, "match")
            assert field_condition.match.value == "test-conversation-123"

    @pytest.mark.asyncio
    async def test_memory_search_multiple_conversations_scenario(
        self, memory_system, sample_vectors, mock_run_context_with_conversation
    ):
        """Test memory search with multiple conversations and verify proper filtering."""
        # Store memories from multiple different conversations
        conversations = [
            ("current-conv", "test-conversation-123"),  # This should be filtered out
            ("conv-a", "conversation-aaa"),
            ("conv-b", "conversation-bbb"),
            ("conv-c", "conversation-ccc"),
        ]

        stored_memories = {}
        for conv_name, conv_id in conversations:
            memory_content = f"Important discussion in {conv_name}"
            memory_id = await memory_system.store_memory(
                content=memory_content,
                vectors=sample_vectors,
                context_tags=[conv_name],
                role="user",
                conversation_id=conv_id,
            )
            stored_memories[conv_id] = {
                "id": memory_id,
                "content": memory_content,
            }

        mock_app = MagicMock()
        mock_app.extensions = {"memory": memory_system}
        mock_app.logger = MagicMock()

        with patch("src.tools.memory_tools.current_app", mock_app):

            # Search for memories
            result = await memory_search(
                mock_run_context_with_conversation, "Important discussion"
            )

            # Verify current conversation is filtered out
            current_conv_content = stored_memories["test-conversation-123"]["content"]
            assert current_conv_content not in result

            # Verify other conversations are included
            other_conversations = [
                "conversation-aaa",
                "conversation-bbb",
                "conversation-ccc",
            ]
            found_other_conversations = 0

            for conv_id in other_conversations:
                if stored_memories[conv_id]["content"] in result:
                    found_other_conversations += 1

            # Should find memories from other conversations
            assert (
                found_other_conversations > 0
            ), "Should find memories from other conversations"

    @pytest.mark.asyncio
    async def test_memory_search_result_formatting(
        self, memory_system, sample_vectors, mock_run_context_with_conversation
    ):
        """Test that memory search results are formatted correctly."""
        # Store a memory from another conversation
        await memory_system.store_memory(
            content="Test memory for formatting",
            vectors=sample_vectors,
            context_tags=["formatting", "test"],
            role="assistant",
            conversation_id="other-conversation",
        )

        mock_app = MagicMock()
        mock_app.extensions = {"memory": memory_system}
        mock_app.logger = MagicMock()

        with patch("src.tools.memory_tools.current_app", mock_app):

            result = await memory_search(
                mock_run_context_with_conversation, "Test memory"
            )

            # Verify result formatting
            assert "## Memory Search Results" in result
            assert "Found" in result and "relevant memories" in result
            assert "**1.**" in result  # Should have numbered results
            assert "assistant" in result  # Should show role
            assert "Test memory for formatting" in result  # Should show content

            # Should include timestamp information
            assert any(char.isdigit() for char in result), "Should include timestamp"
