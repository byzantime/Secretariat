"""Unit tests for the memory system."""

import time
import uuid
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import pytest_asyncio
from qdrant_client.models import Distance
from qdrant_client.models import PointStruct

from src.modules.memory import MemoryService


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


@pytest.fixture
def mock_bulk_app():
    """Mock Quart app configured for bulk operations."""
    mock_app = MagicMock()

    # Configure app config
    mock_app.config = {
        "QDRANT_HOST": ":memory:",
        "QDRANT_PORT": 6333,
        "QDRANT_API_KEY": None,
        "MEMORY_COLLECTION_NAME": "test_bulk_memories",
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
    with (
        patch("src.modules.memory.VectorGenerator", return_value=mock_vector_generator),
        patch(
            "src.modules.memory.SentimentIntensityAnalyzer",
            return_value=mock_sentiment_analyzer,
        ),
    ):
        # Use new Quart extension pattern
        system = MemoryService()
        system.init_app(mock_app)
        await system.initialize_async()

        return system


@pytest_asyncio.fixture
async def bulk_memory_system(
    mock_bulk_app, mock_vector_generator, mock_sentiment_analyzer
):
    """Create a MemoryService instance in bulk mode."""
    with (
        patch("src.modules.memory.VectorGenerator", return_value=mock_vector_generator),
        patch(
            "src.modules.memory.SentimentIntensityAnalyzer",
            return_value=mock_sentiment_analyzer,
        ),
    ):
        system = MemoryService()
        system.init_app(mock_bulk_app)
        await system.initialize_async()
        system.bulk_mode = True  # Enable bulk mode after initialization

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


class TestMemoryServiceInitialization:
    """Test cases for MemoryService initialization."""

    def test_default_initialization(
        self, mock_app, mock_vector_generator, mock_sentiment_analyzer
    ):
        """Test MemoryService initialization with default parameters."""
        with (
            patch(
                "src.modules.memory.VectorGenerator", return_value=mock_vector_generator
            ),
            patch(
                "src.modules.memory.SentimentIntensityAnalyzer",
                return_value=mock_sentiment_analyzer,
            ),
        ):
            system = MemoryService()
            system.init_app(mock_app)

            assert system.collection_name == "test_memories"  # From mock app config
            assert not system.bulk_mode
            assert system.decay_constant == 86400 * 7  # 1 week
            assert system.min_strength_threshold == 0.1
            assert system.max_memories == 10000

    def test_custom_initialization(
        self, mock_vector_generator, mock_sentiment_analyzer
    ):
        """Test MemoryService initialization with custom parameters."""
        # Create custom mock app
        custom_mock_app = MagicMock()
        custom_mock_app.config = {
            "QDRANT_HOST": "test-host",
            "QDRANT_PORT": 9999,
            "QDRANT_API_KEY": None,
            "MEMORY_COLLECTION_NAME": "custom_memories",
        }
        custom_mock_app.logger = MagicMock()
        custom_mock_app.extensions = {
            "event_handler": MagicMock(),
            "communication_service": MagicMock(),
        }
        custom_mock_app.extensions["event_handler"].on = MagicMock()
        custom_mock_app.extensions["communication_service"].current_conversation = None

        with (
            patch(
                "src.modules.memory.VectorGenerator", return_value=mock_vector_generator
            ),
            patch(
                "src.modules.memory.SentimentIntensityAnalyzer",
                return_value=mock_sentiment_analyzer,
            ),
            patch.object(MemoryService, "_setup_collection"),
        ):
            system = MemoryService()
            system.init_app(custom_mock_app)
            system.bulk_mode = True  # Set after initialization

            assert system.collection_name == "custom_memories"
            assert system.bulk_mode

    @pytest.mark.asyncio
    async def test_collection_setup(self, memory_system):
        """Test that collection is set up with correct vector configurations."""
        # Verify collection exists
        collections = await memory_system.client.get_collections()
        collection_names = [c.name for c in collections.collections]
        assert "test_memories" in collection_names

        # Verify vector configurations
        collection_info = await memory_system.client.get_collection("test_memories")
        vectors_config = collection_info.config.params.vectors

        assert "semantic" in vectors_config
        assert "temporal" in vectors_config
        assert "contextual" in vectors_config
        assert "role" in vectors_config

        assert vectors_config["semantic"].size == 384
        assert vectors_config["temporal"].size == 20
        assert vectors_config["contextual"].size == 100
        assert vectors_config["role"].size == 1

        assert vectors_config["semantic"].distance == Distance.COSINE
        assert vectors_config["temporal"].distance == Distance.COSINE
        assert vectors_config["contextual"].distance == Distance.COSINE
        assert vectors_config["role"].distance == Distance.COSINE

    @pytest.mark.asyncio
    async def test_weight_parameters(self, memory_system):
        """Test that strength weights are set correctly."""
        assert memory_system.recency_weight == 1.0
        assert memory_system.frequency_weight == 0.5
        assert memory_system.emotional_weight == 2.0


class TestMemoryStorage:
    """Test cases for memory storage operations."""

    @pytest.mark.asyncio
    async def test_store_memory_basic(self, memory_system, sample_vectors):
        """Test basic memory storage."""
        content = "Test memory content"
        context_tags = ["test", "memory"]

        memory_id = await memory_system.store_memory(
            content=content, vectors=sample_vectors, context_tags=context_tags
        )

        assert isinstance(memory_id, str)
        # Verify it's a valid UUID format
        uuid.UUID(memory_id)

        # Verify memory is stored in Qdrant
        stored_memory = (
            await memory_system.client.retrieve(
                collection_name="test_memories", ids=[memory_id]
            )
        )[0]

        assert stored_memory.payload["content"] == content
        assert stored_memory.payload["context_tags"] == context_tags
        assert "created_at" in stored_memory.payload
        assert "last_accessed" in stored_memory.payload
        assert stored_memory.payload["retrieval_count"] == 0
        assert "emotional_charge" in stored_memory.payload

    @pytest.mark.asyncio
    async def test_store_memory_with_emotional_charge(
        self, memory_system, sample_vectors, mock_sentiment_analyzer
    ):
        """Test memory storage calculates emotional charge."""
        # Configure mock sentiment analyzer
        mock_sentiment_analyzer.polarity_scores.return_value = {"compound": 0.8}

        content = "This is an exciting discovery!"
        memory_id = await memory_system.store_memory(
            content=content, vectors=sample_vectors
        )

        stored_memory = (
            await memory_system.client.retrieve(
                collection_name="test_memories", ids=[memory_id]
            )
        )[0]

        assert stored_memory.payload["emotional_charge"] == 0.8

    @pytest.mark.asyncio
    async def test_store_memory_without_context_tags(
        self, memory_system, sample_vectors
    ):
        """Test memory storage without context tags."""
        content = "Memory without tags"
        memory_id = await memory_system.store_memory(
            content=content, vectors=sample_vectors
        )

        stored_memory = (
            await memory_system.client.retrieve(
                collection_name="test_memories", ids=[memory_id]
            )
        )[0]

        assert stored_memory.payload["context_tags"] == []

    @pytest.mark.asyncio
    async def test_generate_vectors(self, memory_system, mock_vector_generator):
        """Test vector generation."""
        content = "Test content for vector generation"
        timestamp = time.time()
        context_tags = ["test", "vector"]

        vectors = await memory_system.generate_vectors(
            content=content, role="user", timestamp=timestamp, context_tags=context_tags
        )

        # Note: Since we're using asyncio.to_thread, the mock won't show direct call args
        # We'll verify the return value instead
        expected_vectors = {
            "semantic": [0.1] * 384,
            "temporal": [0.2] * 20,
            "contextual": [0.3] * 100,
            "role": [0.4] * 1,
        }
        assert vectors == expected_vectors

    def test_emotional_charge_calculation(self, memory_system, mock_sentiment_analyzer):
        """Test emotional charge calculation."""
        # Test positive compound score
        mock_sentiment_analyzer.polarity_scores.return_value = {"compound": 0.6}
        charge = memory_system._calculate_emotional_charge("Happy content")
        assert charge == 0.6

        # Test negative compound score (should return absolute value)
        mock_sentiment_analyzer.polarity_scores.return_value = {"compound": -0.7}
        charge = memory_system._calculate_emotional_charge("Sad content")
        assert charge == 0.7

        # Test neutral score
        mock_sentiment_analyzer.polarity_scores.return_value = {"compound": 0.0}
        charge = memory_system._calculate_emotional_charge("Neutral content")
        assert charge == 0.0


class TestMemoryRetrieval:
    """Test cases for memory retrieval operations."""

    def setup_method(self):
        """Set up test data for each test method."""
        self.test_memories = [
            (
                "Strong recent memory",
                {
                    "semantic": [0.1] * 384,
                    "temporal": [0.2] * 20,
                    "contextual": [0.3] * 100,
                    "role": [1.0] * 1,
                },
            ),
            (
                "Older memory",
                {
                    "semantic": [0.4] * 384,
                    "temporal": [0.5] * 20,
                    "contextual": [0.6] * 100,
                    "role": [0.0] * 1,
                },
            ),
            (
                "Weak memory",
                {
                    "semantic": [0.7] * 384,
                    "temporal": [0.8] * 20,
                    "contextual": [0.9] * 100,
                    "role": [0.5] * 1,
                },
            ),
        ]

    @pytest.mark.asyncio
    async def test_retrieve_memories_basic(self, memory_system, sample_vectors):
        """Test basic memory retrieval functionality."""
        # Store a memory first
        content = "Test memory for retrieval"
        memory_id = await memory_system.store_memory(
            content=content, vectors=sample_vectors, context_tags=["test"]
        )

        # Retrieve using same vectors
        query_vectors = sample_vectors
        retrieved = await memory_system.retrieve_memories(query_vectors, limit=5)

        assert len(retrieved) == 1
        assert retrieved[0]["id"] == memory_id
        assert retrieved[0]["payload"]["content"] == content
        assert "strength" in retrieved[0]
        assert "score" in retrieved[0]
        assert retrieved[0]["payload"]["context_tags"] == ["test"]

    @pytest.mark.asyncio
    async def test_retrieve_memories_updates_access_stats(
        self, memory_system, sample_vectors
    ):
        """Test that retrieval updates last_accessed and retrieval_count."""
        # Store a memory
        memory_id = await memory_system.store_memory(
            content="Memory to track access", vectors=sample_vectors
        )

        # Get initial stats
        initial_memory = (
            await memory_system.client.retrieve(
                collection_name="test_memories", ids=[memory_id]
            )
        )[0]
        initial_last_accessed = initial_memory.payload["last_accessed"]
        initial_retrieval_count = initial_memory.payload["retrieval_count"]

        # Wait a bit to ensure timestamp difference
        time.sleep(0.01)

        # Retrieve the memory
        await memory_system.retrieve_memories(sample_vectors, limit=5)

        # Check updated stats
        updated_memory = (
            await memory_system.client.retrieve(
                collection_name="test_memories", ids=[memory_id]
            )
        )[0]

        assert updated_memory.payload["last_accessed"] > initial_last_accessed
        assert updated_memory.payload["retrieval_count"] == initial_retrieval_count + 1

    @pytest.mark.asyncio
    async def test_retrieve_memories_includes_all_strengths(self, memory_system):
        """Test that retrieval includes both strong and weak memories (strength only affects cleanup)."""
        # Create memories with different timestamps to affect strength
        current_time = time.time()

        # Store recent memory (should have high strength)
        recent_vectors = {
            "semantic": [0.1] * 384,
            "temporal": [0.2] * 20,
            "contextual": [0.3] * 100,
            "role": [0.4] * 1,
        }
        recent_id = await memory_system.store_memory(
            content="Recent memory", vectors=recent_vectors, role="user"
        )

        # Manually store old memory with low strength
        old_time = current_time - (memory_system.decay_constant * 5)  # Very old
        old_memory_id = str(uuid.uuid4())
        old_memory = PointStruct(
            id=old_memory_id,
            vector={
                "semantic": [0.4] * 384,
                "temporal": [0.5] * 20,
                "contextual": [0.6] * 100,
                "role": [0.7] * 1,
            },
            payload={
                "content": "Very old memory",
                "created_at": old_time,
                "last_accessed": old_time,
                "retrieval_count": 0,
                "emotional_charge": 0.0,
                "context_tags": [],
                "role": "user",
            },
        )
        await memory_system.client.upsert(
            collection_name="test_memories", points=[old_memory]
        )

        # Retrieve memories - both strong and weak should be returned
        query_vectors = recent_vectors
        retrieved = await memory_system.retrieve_memories(query_vectors, limit=10)

        # Both memories should be returned (strength filtering only happens during cleanup)
        retrieved_ids = [mem["id"] for mem in retrieved]
        assert recent_id in retrieved_ids
        assert old_memory_id in retrieved_ids

    @pytest.mark.asyncio
    async def test_retrieve_memories_sorting(self, memory_system):
        """Test that memories are sorted by similarity score only."""
        # Store multiple memories
        memories = []
        for i, (content, vectors) in enumerate(self.test_memories):
            memory_id = await memory_system.store_memory(
                content=content, vectors=vectors
            )
            memories.append((memory_id, content))

        # Query with vectors that should match first memory best
        query_vectors = {
            "semantic": [0.1] * 384,
            "temporal": [0.2] * 20,
            "contextual": [0.3] * 100,
            "role": [1.0] * 1,
        }
        retrieved = await memory_system.retrieve_memories(query_vectors, limit=10)

        # Verify sorting - scores should be in descending order
        assert len(retrieved) >= 2
        scores = [mem["score"] for mem in retrieved]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_retrieve_memories_limit(self, memory_system):
        """Test that limit parameter is respected."""
        # Store multiple memories
        for i, (content, vectors) in enumerate(self.test_memories):
            await memory_system.store_memory(content=f"{content} {i}", vectors=vectors)

        # Retrieve with small limit
        query_vectors = {
            "semantic": [0.1] * 384,
            "temporal": [0.2] * 20,
            "contextual": [0.3] * 100,
            "role": [1.0] * 1,
        }
        retrieved = await memory_system.retrieve_memories(query_vectors, limit=2)

        assert len(retrieved) <= 2

    @pytest.mark.asyncio
    async def test_retrieve_memories_empty_collection(self, memory_system):
        """Test retrieval from empty collection."""
        query_vectors = {
            "semantic": [0.1] * 384,
            "temporal": [0.2] * 20,
            "contextual": [0.3] * 100,
            "role": [1.0] * 1,
        }
        retrieved = await memory_system.retrieve_memories(query_vectors, limit=5)

        assert retrieved == []


class TestMemoryStrengthCalculation:
    """Test cases for memory strength calculations."""

    @pytest.mark.asyncio
    async def test_memory_strength_recency_factor(self, memory_system):
        """Test that recency affects memory strength correctly."""
        current_time = time.time()

        # Create payload for recent memory
        recent_payload = {
            "content": "Recent memory",
            "created_at": current_time,
            "last_accessed": current_time,
            "retrieval_count": 0,
            "emotional_charge": 0.0,
        }

        # Create payload for old memory
        old_time = current_time - memory_system.decay_constant  # 1 week old
        old_payload = {
            "content": "Old memory",
            "created_at": old_time,
            "last_accessed": old_time,
            "retrieval_count": 0,
            "emotional_charge": 0.0,
        }

        recent_strength = memory_system._calculate_memory_strength(
            recent_payload, current_time
        )
        old_strength = memory_system._calculate_memory_strength(
            old_payload, current_time
        )

        # Recent memory should have higher strength
        assert recent_strength > old_strength

    @pytest.mark.asyncio
    async def test_memory_strength_frequency_factor(self, memory_system):
        """Test that retrieval frequency affects memory strength."""
        current_time = time.time()

        # Create payload for frequently accessed memory
        frequent_payload = {
            "content": "Frequently accessed",
            "created_at": current_time,
            "last_accessed": current_time,
            "retrieval_count": 50,
            "emotional_charge": 0.0,
        }

        # Create payload for rarely accessed memory
        rare_payload = {
            "content": "Rarely accessed",
            "created_at": current_time,
            "last_accessed": current_time,
            "retrieval_count": 1,
            "emotional_charge": 0.0,
        }

        frequent_strength = memory_system._calculate_memory_strength(
            frequent_payload, current_time
        )
        rare_strength = memory_system._calculate_memory_strength(
            rare_payload, current_time
        )

        # Frequently accessed memory should have higher strength
        assert frequent_strength > rare_strength

    @pytest.mark.asyncio
    async def test_memory_strength_emotional_factor(self, memory_system):
        """Test that emotional charge affects memory strength."""
        current_time = time.time()

        # Create payload for emotional memory
        emotional_payload = {
            "content": "Highly emotional memory",
            "created_at": current_time,
            "last_accessed": current_time,
            "retrieval_count": 0,
            "emotional_charge": 0.9,
        }

        # Create payload for neutral memory
        neutral_payload = {
            "content": "Neutral memory",
            "created_at": current_time,
            "last_accessed": current_time,
            "retrieval_count": 0,
            "emotional_charge": 0.0,
        }

        emotional_strength = memory_system._calculate_memory_strength(
            emotional_payload, current_time
        )
        neutral_strength = memory_system._calculate_memory_strength(
            neutral_payload, current_time
        )

        # Emotional memory should have higher strength
        assert emotional_strength > neutral_strength

    @pytest.mark.asyncio
    async def test_memory_strength_normalization(self, memory_system):
        """Test that memory strength is normalized to [0, 1] range."""
        current_time = time.time()

        # Create payload for maximum strength memory
        max_payload = {
            "content": "Maximum strength memory",
            "created_at": current_time,
            "last_accessed": current_time,
            "retrieval_count": 1000,  # Very high
            "emotional_charge": 1.0,  # Maximum
        }

        # Create payload for minimum strength memory
        old_time = current_time - (memory_system.decay_constant * 10)  # Very old
        min_payload = {
            "content": "Minimum strength memory",
            "created_at": old_time,
            "last_accessed": old_time,
            "retrieval_count": 0,
            "emotional_charge": 0.0,
        }

        max_strength = memory_system._calculate_memory_strength(
            max_payload, current_time
        )
        min_strength = memory_system._calculate_memory_strength(
            min_payload, current_time
        )

        # Both should be in [0, 1] range
        assert 0.0 <= max_strength <= 1.0
        assert 0.0 <= min_strength <= 1.0

    @pytest.mark.asyncio
    async def test_memory_strength_exponential_decay(self, memory_system):
        """Test that recency follows exponential decay pattern."""
        current_time = time.time()

        # Test memories at different time intervals
        times = [
            current_time,
            current_time - memory_system.decay_constant / 4,  # 1/4 decay period
            current_time - memory_system.decay_constant / 2,  # 1/2 decay period
            current_time - memory_system.decay_constant,  # 1 decay period
        ]

        strengths = []
        for test_time in times:
            payload = {
                "content": "Test memory",
                "created_at": test_time,
                "last_accessed": test_time,
                "retrieval_count": 0,
                "emotional_charge": 0.0,
            }
            strength = memory_system._calculate_memory_strength(payload, current_time)
            strengths.append(strength)

        # Strengths should decrease as memories get older
        for i in range(len(strengths) - 1):
            assert strengths[i] > strengths[i + 1]


class TestMemoryCleanup:
    """Test cases for memory cleanup operations."""

    @pytest.mark.asyncio
    async def test_cleanup_weak_memories_below_threshold(self, memory_system):
        """Test cleanup removes memories below strength threshold."""
        # Set a small limit to force cleanup
        original_max = memory_system.max_memories
        memory_system.max_memories = 5

        try:
            current_time = time.time()

            # Store some strong recent memories
            strong_memories = []
            for i in range(3):
                memory_id = await memory_system.store_memory(
                    content=f"Strong memory {i}",
                    vectors={
                        "semantic": [0.1] * 384,
                        "temporal": [0.2] * 20,
                        "contextual": [0.3] * 100,
                        "role": [1.0] * 1,
                    },
                )
                strong_memories.append(memory_id)

            # Manually store weak old memories - make them EXTREMELY old
            old_time = current_time - (
                memory_system.decay_constant * 50
            )  # Extremely old
            weak_memories = []
            for i in range(4):  # More than max_memories to force cleanup
                weak_memory_id = str(uuid.uuid4())
                weak_memory = PointStruct(
                    id=weak_memory_id,
                    vector={
                        "semantic": [0.4] * 384,
                        "temporal": [0.5] * 20,
                        "contextual": [0.6] * 100,
                        "role": [0.0] * 1,
                    },
                    payload={
                        "content": f"Weak memory {i}",
                        "created_at": old_time,
                        "last_accessed": old_time,
                        "retrieval_count": 0,
                        "emotional_charge": 0.0,
                        "context_tags": [],
                    },
                )
                await memory_system.client.upsert(
                    collection_name="test_memories", points=[weak_memory]
                )
                weak_memories.append(weak_memory_id)

            # Get initial count
            initial_count = (
                await memory_system.client.count(collection_name="test_memories")
            ).count

            # Trigger cleanup
            await memory_system._cleanup_weak_memories()

            # Check that memories were removed to stay within limit
            final_count = (
                await memory_system.client.count(collection_name="test_memories")
            ).count
            assert final_count <= memory_system.max_memories
            assert final_count < initial_count

            # Strong memories should still exist (they're stronger)
            remaining_memories = (
                await memory_system.client.scroll(
                    collection_name="test_memories", limit=100, with_payload=True
                )
            )[0]
            remaining_ids = [str(mem.id) for mem in remaining_memories]

            # At least some strong memories should still exist
            strong_remaining = sum(
                1 for strong_id in strong_memories if strong_id in remaining_ids
            )
            assert strong_remaining > 0

        finally:
            memory_system.max_memories = original_max

    @pytest.mark.asyncio
    async def test_cleanup_respects_max_memories_limit(self, memory_system):
        """Test cleanup when memory count exceeds max_memories."""
        # Set a small max_memories limit for testing
        original_max = memory_system.max_memories
        memory_system.max_memories = 5

        try:
            # Store more memories than the limit
            memory_ids = []
            for i in range(8):
                memory_id = await memory_system.store_memory(
                    content=f"Memory {i}",
                    vectors={
                        "semantic": [0.1 + i * 0.1] * 384,
                        "temporal": [0.2] * 20,
                        "contextual": [0.3] * 100,
                    },
                )
                memory_ids.append(memory_id)

            # Trigger cleanup
            await memory_system._cleanup_weak_memories()

            # Should not exceed max_memories
            final_count = (
                await memory_system.client.count(collection_name="test_memories")
            ).count
            assert final_count <= memory_system.max_memories

        finally:
            # Restore original limit
            memory_system.max_memories = original_max

    @pytest.mark.asyncio
    async def test_cleanup_no_action_when_under_limit(self, memory_system):
        """Test that cleanup doesn't remove memories when under limits."""
        # Store a few strong memories
        memory_ids = []
        for i in range(3):
            memory_id = await memory_system.store_memory(
                content=f"Good memory {i}",
                vectors={
                    "semantic": [0.1] * 384,
                    "temporal": [0.2] * 20,
                    "contextual": [0.3] * 100,
                    "role": [1.0] * 1,
                },
            )
            memory_ids.append(memory_id)

        initial_count = (
            await memory_system.client.count(collection_name="test_memories")
        ).count

        # Trigger cleanup
        await memory_system._cleanup_weak_memories()

        # Count should remain the same
        final_count = (
            await memory_system.client.count(collection_name="test_memories")
        ).count
        assert final_count == initial_count

        # All memories should still exist
        remaining_memories = (
            await memory_system.client.scroll(
                collection_name="test_memories", limit=100
            )
        )[0]
        remaining_ids = [str(mem.id) for mem in remaining_memories]

        for memory_id in memory_ids:
            assert memory_id in remaining_ids

    @pytest.mark.asyncio
    async def test_cleanup_preserves_strongest_memories(self, memory_system):
        """Test that cleanup preserves the strongest memories when at capacity."""
        # Set small limit
        original_max = memory_system.max_memories
        memory_system.max_memories = 3

        try:
            current_time = time.time()

            # Store memories with different strengths
            # High emotional charge memory
            emotional_id = await memory_system.store_memory(
                content="Highly emotional memory",
                vectors={
                    "semantic": [0.1] * 384,
                    "temporal": [0.2] * 20,
                    "contextual": [0.3] * 100,
                    "role": [1.0] * 1,
                },
            )

            # Update it to have high emotional charge
            await memory_system.client.upsert(
                collection_name="test_memories",
                points=[
                    PointStruct(
                        id=emotional_id,
                        vector={
                            "semantic": [0.1] * 384,
                            "temporal": [0.2] * 20,
                            "contextual": [0.3] * 100,
                            "role": [1.0] * 1,
                        },
                        payload={
                            "content": "Highly emotional memory",
                            "created_at": current_time,
                            "last_accessed": current_time,
                            "retrieval_count": 0,
                            "emotional_charge": 0.9,
                            "context_tags": [],
                        },
                    )
                ],
            )

            # Store several weaker memories
            weak_ids = []
            for i in range(5):
                old_time = current_time - (memory_system.decay_constant * 2)  # Old
                weak_memory_id = str(uuid.uuid4())
                weak_memory = PointStruct(
                    id=weak_memory_id,
                    vector={
                        "semantic": [0.4] * 384,
                        "temporal": [0.5] * 20,
                        "contextual": [0.6] * 100,
                        "role": [0.0] * 1,
                    },
                    payload={
                        "content": f"Weak memory {i}",
                        "created_at": old_time,
                        "last_accessed": old_time,
                        "retrieval_count": 0,
                        "emotional_charge": 0.0,
                        "context_tags": [],
                    },
                )
                await memory_system.client.upsert(
                    collection_name="test_memories", points=[weak_memory]
                )
                weak_ids.append(weak_memory_id)

            # Trigger cleanup
            await memory_system._cleanup_weak_memories()

            # Should not exceed limit
            final_count = (
                await memory_system.client.count(collection_name="test_memories")
            ).count
            assert final_count <= memory_system.max_memories

            # Strong emotional memory should be preserved
            remaining_memories = (
                await memory_system.client.scroll(
                    collection_name="test_memories", limit=100
                )
            )[0]
            remaining_ids = [str(mem.id) for mem in remaining_memories]
            assert emotional_id in remaining_ids

        finally:
            memory_system.max_memories = original_max

    @pytest.mark.asyncio
    async def test_cleanup_empty_collection(self, memory_system):
        """Test cleanup on empty collection doesn't cause errors."""
        # Ensure collection is empty
        initial_count = (
            await memory_system.client.count(collection_name="test_memories")
        ).count
        assert initial_count == 0

        # Should not raise an error
        await memory_system._cleanup_weak_memories()

        # Count should remain zero
        final_count = (
            await memory_system.client.count(collection_name="test_memories")
        ).count
        assert final_count == 0


class TestBulkOperations:
    """Test cases for bulk memory operations."""

    @pytest.mark.asyncio
    async def test_bulk_storage_validation(self, memory_system):
        """Test that bulk storage is only available in bulk mode."""
        # Regular memory system (not bulk mode)
        with pytest.raises(
            ValueError, match="Bulk storage only available in bulk_mode=True"
        ):
            await memory_system.store_memories_bulk([])

    @pytest.mark.asyncio
    async def test_bulk_storage_basic(self, bulk_memory_system, sample_vectors):
        """Test basic bulk memory storage."""
        memories_to_store = [
            ("First bulk memory", sample_vectors, ["bulk", "test"], "user"),
            ("Second bulk memory", sample_vectors, ["bulk", "test"], "user"),
            ("Third bulk memory", sample_vectors, ["bulk", "test"], "user"),
        ]

        memory_ids = await bulk_memory_system.store_memories_bulk(memories_to_store)

        assert len(memory_ids) == 3
        assert all(isinstance(mid, str) for mid in memory_ids)

        # Verify all memories were stored
        for i, memory_id in enumerate(memory_ids):
            stored_memory = (
                await bulk_memory_system.client.retrieve(
                    collection_name="test_bulk_memories", ids=[memory_id]
                )
            )[0]

            assert stored_memory.payload["content"] == f"{memories_to_store[i][0]}"
            assert stored_memory.payload["context_tags"] == memories_to_store[i][2]
            assert "emotional_charge" in stored_memory.payload

    @pytest.mark.asyncio
    async def test_bulk_storage_empty_list(self, bulk_memory_system):
        """Test bulk storage with empty list."""
        memory_ids = await bulk_memory_system.store_memories_bulk([])
        assert memory_ids == []

    @pytest.mark.asyncio
    async def test_bulk_storage_with_cleanup(self, bulk_memory_system):
        """Test that cleanup is triggered after bulk storage."""
        # Set small max limit
        original_max = bulk_memory_system.max_memories
        bulk_memory_system.max_memories = 5

        try:
            # Create more memories than the limit
            many_memories = []
            for i in range(10):
                vectors = {
                    "semantic": [i * 0.1] * 384,
                    "temporal": [i * 0.1] * 20,
                    "contextual": [i * 0.1] * 100,
                }
                many_memories.append((f"Memory {i}", vectors, ["bulk"], "user"))

            # Store in bulk
            await bulk_memory_system.store_memories_bulk(many_memories)

            # Should have triggered cleanup
            final_count = (
                await bulk_memory_system.client.count(
                    collection_name="test_bulk_memories"
                )
            ).count
            assert final_count <= bulk_memory_system.max_memories

        finally:
            bulk_memory_system.max_memories = original_max

    @pytest.mark.asyncio
    async def test_bulk_storage_maintains_timestamps(
        self, bulk_memory_system, sample_vectors
    ):
        """Test that bulk storage maintains consistent timestamps."""
        memories_to_store = [
            ("Memory 1", sample_vectors, ["test"], "user"),
            ("Memory 2", sample_vectors, ["test"], "user"),
            ("Memory 3", sample_vectors, ["test"], "user"),
        ]

        start_time = time.time()
        memory_ids = await bulk_memory_system.store_memories_bulk(memories_to_store)
        end_time = time.time()

        # Verify timestamps are within expected range
        for memory_id in memory_ids:
            stored_memory = (
                await bulk_memory_system.client.retrieve(
                    collection_name="test_bulk_memories", ids=[memory_id]
                )
            )[0]

            created_at = stored_memory.payload["created_at"]
            last_accessed = stored_memory.payload["last_accessed"]

            assert start_time <= created_at <= end_time
            assert start_time <= last_accessed <= end_time
            assert created_at == last_accessed  # Should be same for new memories

    @pytest.mark.asyncio
    async def test_bulk_storage_uuid_generation(
        self, bulk_memory_system, sample_vectors
    ):
        """Test that bulk storage generates valid UUIDs."""
        memories_to_store = [
            ("Memory 1", sample_vectors, ["test"], "user"),
            ("Memory 2", sample_vectors, ["test"], "user"),
        ]

        memory_ids = await bulk_memory_system.store_memories_bulk(memories_to_store)

        # All IDs should be valid UUIDs
        for memory_id in memory_ids:
            uuid.UUID(memory_id)  # Will raise if invalid

        # All IDs should be unique
        assert len(set(memory_ids)) == len(memory_ids)

    @pytest.mark.asyncio
    async def test_bulk_storage_vector_consistency(self, bulk_memory_system):
        """Test that vectors are stored correctly in bulk operations."""
        # Use distinct vectors for each memory
        memories_to_store = [
            (
                "Memory 1",
                {
                    "semantic": [0.1] * 384,
                    "temporal": [0.2] * 20,
                    "contextual": [0.3] * 100,
                    "role": [1.0] * 1,
                },
                ["test"],
                "user",
            ),
            (
                "Memory 2",
                {
                    "semantic": [0.4] * 384,
                    "temporal": [0.5] * 20,
                    "contextual": [0.6] * 100,
                    "role": [0.0] * 1,
                },
                ["test"],
                "user",
            ),
            (
                "Memory 3",
                {
                    "semantic": [0.7] * 384,
                    "temporal": [0.8] * 20,
                    "contextual": [0.9] * 100,
                    "role": [0.5] * 1,
                },
                ["test"],
                "user",
            ),
        ]

        memory_ids = await bulk_memory_system.store_memories_bulk(memories_to_store)

        # Verify vectors were stored and have the correct structure
        for i, memory_id in enumerate(memory_ids):
            stored_memory = (
                await bulk_memory_system.client.retrieve(
                    collection_name="test_bulk_memories",
                    ids=[memory_id],
                    with_vectors=True,
                )
            )[0]

            # Verify vector structure is correct
            assert "semantic" in stored_memory.vector
            assert "temporal" in stored_memory.vector
            assert "contextual" in stored_memory.vector

            # Verify vector dimensions
            assert len(stored_memory.vector["semantic"]) == 384
            assert len(stored_memory.vector["temporal"]) == 20
            assert len(stored_memory.vector["contextual"]) == 100


class TestMemoryStatistics:
    """Test cases for memory statistics and analysis."""

    @pytest.mark.asyncio
    async def test_get_memory_stats_empty_collection(self, memory_system):
        """Test memory statistics with empty collection."""
        stats = await memory_system.get_memory_stats()
        assert stats == {"total_memories": 0}

    @pytest.mark.asyncio
    async def test_get_memory_stats_with_memories(self, memory_system, sample_vectors):
        """Test memory statistics with some memories."""
        # Store a few memories
        for i in range(3):
            await memory_system.store_memory(
                content=f"Test memory {i}",
                vectors=sample_vectors,
                context_tags=[f"tag{i}"],
            )

        stats = await memory_system.get_memory_stats()

        assert stats["total_memories"] == 3
        assert "avg_strength" in stats
        assert "min_strength" in stats
        assert "max_strength" in stats
        assert "avg_age_days" in stats
        assert "weak_memories" in stats

        # Verify value ranges
        assert 0.0 <= stats["avg_strength"] <= 1.0
        assert 0.0 <= stats["min_strength"] <= 1.0
        assert 0.0 <= stats["max_strength"] <= 1.0
        assert stats["avg_age_days"] >= 0.0
        assert stats["weak_memories"] >= 0

    @pytest.mark.asyncio
    async def test_get_memory_stats_strength_calculation(
        self, memory_system, sample_vectors
    ):
        """Test that statistics correctly calculate strength ranges."""
        current_time = time.time()

        # Store a strong recent memory
        await memory_system.store_memory(
            content="Strong recent memory", vectors=sample_vectors
        )

        # Manually store a weak old memory
        old_time = current_time - (memory_system.decay_constant * 5)
        weak_memory_id = str(uuid.uuid4())
        weak_memory = PointStruct(
            id=weak_memory_id,
            vector=sample_vectors,
            payload={
                "content": "Weak old memory",
                "created_at": old_time,
                "last_accessed": old_time,
                "retrieval_count": 0,
                "emotional_charge": 0.0,
                "context_tags": [],
            },
        )
        await memory_system.client.upsert(
            collection_name="test_memories", points=[weak_memory]
        )

        stats = await memory_system.get_memory_stats()

        assert stats["total_memories"] == 2
        assert stats["max_strength"] > stats["min_strength"]
        assert stats["weak_memories"] >= 1  # At least the old memory should be weak
