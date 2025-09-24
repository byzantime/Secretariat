"""
Conversational AI memory system.

Memories have the following vectors:
- role - user or assistant;
- semantic - an utterance by one of the roles;
- temporal - using cyclical features;
- contextual - tbd but perhaps tools used at the time.

Memory strength (resistance to decay/being forgotten) factors:
- recency of occurrence;
- frequency of retrieval;
- emotional charge;

Once memories fall below a certain strength threshold they are forgotten (deleted).
"""

import asyncio
import math
import random
import time
import uuid
from datetime import datetime
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from qdrant_client.async_qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance
from qdrant_client.models import Filter
from qdrant_client.models import PointStruct
from qdrant_client.models import VectorParams
from quart import current_app
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from src.modules.vector_generator import VectorGenerator


class MemoryService:
    """Quart extension for conversational AI memory system."""

    def __init__(self, app=None):
        self.client = None
        self.collection_name = "memories"
        self.analyzer = None
        self.vector_generator = None
        self.bulk_mode = False

        # Decay parameters
        self.decay_constant = 86400 * 7  # 1 week in seconds
        self.min_strength_threshold = 0.1
        self.max_memories = 10000

        # Strength weights
        self.recency_weight = 1.0
        self.frequency_weight = 0.5
        self.emotional_weight = 2.0

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the memory service with the application."""
        # Get configuration
        host = app.config["QDRANT_HOST"]
        port = app.config["QDRANT_PORT"]
        api_key = app.config["QDRANT_API_KEY"]
        self.collection_name = app.config["MEMORY_COLLECTION_NAME"]

        # Initialize Qdrant client
        if host == ":memory:":
            self.client = AsyncQdrantClient(":memory:")
        elif api_key:  # Use cloud Qdrant with API key
            self.client = AsyncQdrantClient(url=host, api_key=api_key)
        else:
            # Use local Qdrant with host/port
            self.client = AsyncQdrantClient(host=host, port=port)

        # Initialize components
        self.analyzer = SentimentIntensityAnalyzer()
        self.vector_generator = VectorGenerator()

        # Subscribe to LLM events for automatic memory storage
        self._subscribe_to_events(app)

        # Set up collection on app startup
        @app.before_serving
        async def setup_memory_collection():
            """Ensure the memory collection exists on startup."""
            await self._setup_collection()

        app.logger.info(
            f"Memory service initialized with collection: {self.collection_name}"
        )
        app.extensions["memory"] = self

    def init_standalone(self):
        """Initialize the memory service for standalone usage without Quart app."""
        # Use hardcoded local Docker instance settings for standalone mode
        host = "localhost"
        port = 6333
        self.collection_name = "memories"

        # Initialize Qdrant client for local Docker instance
        self.client = AsyncQdrantClient(host=host, port=port)

        # Initialize components
        self.analyzer = SentimentIntensityAnalyzer()
        self.vector_generator = VectorGenerator()

        print(
            "Memory service initialized standalone with local Docker Qdrant at"
            f" {host}:{port} using collection: {self.collection_name}"
        )

    def is_available(self) -> bool:
        """Check if the memory service is available."""
        return self.client is not None and self.analyzer is not None

    def _subscribe_to_events(self, app):
        """Subscribe to relevant events for automatic memory storage."""
        event_handler = app.extensions["event_handler"]
        event_handler.on("llm.message.complete", self._handle_assistant_message)
        event_handler.on("chat.message", self._handle_user_message)

    async def _handle_message(
        self, data: Optional[Dict] = None, role: str = "assistant"
    ):
        """Handle message events by storing messages in memory."""
        # Determine the content key based on role
        content_key = "content" if role == "assistant" else "message"

        if not data or not data.get(content_key):
            current_app.logger.debug(f"No {role} message found in event data: {data}")
            return

        # Extract conversation context from current app state
        communication_service = current_app.extensions["communication_service"]
        if communication_service.current_conversation:
            conversation_id = communication_service.current_conversation.id

            # Store the message in memory
            await self.add(
                conversation_id=conversation_id,
                utterance=data[content_key],
                role=role,
                timestamp=datetime.now(),
            )

            current_app.logger.debug(
                f"Stored {role} message in memory for conversation {conversation_id}"
            )
        else:
            current_app.logger.debug(
                f"No current conversation found for {role} message: {data}"
            )

    async def _handle_assistant_message(self, data: Dict):
        """Handle LLM message complete event by storing assistant message in memory."""
        await self._handle_message(data, role="assistant")

    async def _handle_user_message(self, data: Dict):
        """Handle user message event by storing user message in memory."""
        await self._handle_message(data, role="user")

    async def _setup_collection(self):
        """Initialise Qdrant collection with multiple vector configurations."""
        try:
            await self.client.get_collection(self.collection_name)
        except Exception:
            # Create collection with multiple named vectors
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "semantic": VectorParams(size=384, distance=Distance.COSINE),
                    "temporal": VectorParams(size=20, distance=Distance.COSINE),
                    "contextual": VectorParams(size=100, distance=Distance.COSINE),
                    "role": VectorParams(size=1, distance=Distance.COSINE),
                },
            )
            current_app.logger.info(
                f"Memory collection '{self.collection_name}' setup complete"
            )

    def _calculate_emotional_charge(self, content: str) -> float:
        """Calculate emotional charge using VADER sentiment analysis."""
        scores = self.analyzer.polarity_scores(content)
        # Use compound score, amplified by intensity
        return abs(scores["compound"])

    async def generate_vectors(
        self,
        content: str,
        role: str,
        timestamp: Optional[float] = None,
        context_tags: Optional[List[str]] = None,
    ) -> Dict[str, List[float]]:
        """Generate all vector types for the given content.

        Args:
            content: Text content to encode
            timestamp: Unix timestamp (uses current time if None)
            context_tags: List of context tags
            role: Role of the speaker ("user" or "assistant")

        Returns:
            Dictionary with 'semantic', 'temporal', 'contextual', and 'role' vectors
        """
        return await asyncio.to_thread(
            self.vector_generator.generate_all,
            content=content,
            timestamp=timestamp,
            context_tags=context_tags,
            role=role,
        )

    def _calculate_memory_strength(
        self, payload: Dict[str, Any], current_time: Optional[float] = None
    ) -> float:
        """Calculate current memory strength based on recency, frequency, and emotional charge."""
        if current_time is None:
            current_time = time.time()
        time_since_access = current_time - payload["last_accessed"]

        # Recency factor (exponential decay)
        recency_factor = math.exp(-time_since_access / self.decay_constant)

        # Frequency factor (logarithmic with diminishing returns) - normalised to [0, 1]
        max_expected_retrievals = 100  # Assume 100 retrievals = max frequency score
        frequency_factor = min(
            1.0,
            math.log(1 + payload["retrieval_count"])
            / math.log(1 + max_expected_retrievals),
        )

        # Emotional factor
        emotional_factor = payload["emotional_charge"]

        # Calculate weighted sum
        raw_strength = (
            self.recency_weight * recency_factor
            + self.frequency_weight * frequency_factor
            + self.emotional_weight * emotional_factor
        )

        # Normalize by total possible weight to ensure [0, 1] range
        total_weight = (
            self.recency_weight + self.frequency_weight + self.emotional_weight
        )

        normalized_strength = raw_strength / total_weight

        return max(0.0, min(1.0, normalized_strength))

    async def store_memory(
        self,
        content: str,
        vectors: Dict[str, List[float]],
        context_tags: Optional[List[str]] = None,
        role: str = "user",
        **kwargs,
    ) -> str:
        """Store a new memory in the system."""
        memory_id = str(uuid.uuid4())
        current_time = time.time()

        emotional_charge = self._calculate_emotional_charge(content)

        # Store in Qdrant
        point = PointStruct(
            id=memory_id,
            vector=vectors,
            payload={
                "content": content,
                "created_at": current_time,
                "last_accessed": current_time,
                "retrieval_count": 0,
                "emotional_charge": emotional_charge,
                "context_tags": context_tags or [],
                "role": role,
                **kwargs,  # Merge in any additional payload data
            },
        )

        await self.client.upsert(collection_name=self.collection_name, points=[point])

        # Clean up weak memories if we're at capacity
        await self._cleanup_weak_memories()

        return memory_id

    async def add(
        self,
        conversation_id: str,
        utterance: str,
        role: str,
        timestamp: datetime,
        context_tags: Optional[List[str]] = None,
    ) -> str:
        """Convenient method to add a memory with automatic vector generation.

        Args:
            conversation_id: ID of the conversation this memory belongs to
            utterance: The text content of the memory
            role: Role of the speaker ("user" or "assistant")
            timestamp: When the utterance occurred
            context_tags: Optional list of context tags for categorization

        Returns:
            The memory ID of the stored memory
        """
        if not self.is_available():
            return None
        vectors = await self.generate_vectors(
            content=utterance,
            role=role,
            timestamp=timestamp.timestamp(),
            context_tags=context_tags,
        )
        return await self.store_memory(
            content=utterance,
            vectors=vectors,
            context_tags=context_tags,
            role=role,
            conversation_id=conversation_id,
        )

    async def store_memories_bulk(
        self,
        memories: List[tuple],  # List of (content, vectors, context_tags, role) tuples
    ) -> List[str]:
        """Store multiple memories efficiently in bulk mode."""
        if not self.bulk_mode:
            raise ValueError("Bulk storage only available in bulk_mode=True")

        if not memories:
            return []

        current_time = time.time()
        memory_ids = []
        points = []

        # Prepare all memories for batch insert
        for content, vectors, context_tags, role in memories:
            memory_id = str(uuid.uuid4())
            memory_ids.append(memory_id)

            emotional_charge = self._calculate_emotional_charge(content)

            point = PointStruct(
                id=memory_id,
                vector=vectors,
                payload={
                    "content": content,
                    "created_at": current_time,
                    "last_accessed": current_time,
                    "retrieval_count": 0,
                    "emotional_charge": emotional_charge,
                    "context_tags": context_tags or [],
                    "role": role,
                },
            )
            points.append(point)

        # Single batch upsert
        await self.client.upsert(collection_name=self.collection_name, points=points)

        # Clean up weak memories once at the end
        await self._cleanup_weak_memories()

        return memory_ids

    async def retrieve_memories(
        self,
        query_vectors: Dict[str, List[float]],
        limit: int = 10,
        query_filter: Optional[Filter] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve most relevant memories and update their strength."""
        # For simplicity, use the first vector type for initial search
        vector_name = list(query_vectors.keys())[0]
        query_vector = query_vectors[vector_name]

        results = await self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            using=vector_name,
            limit=limit,
            with_payload=True,
            query_filter=query_filter,
        )
        results = results.points

        current_time = time.time()
        memories_to_update = []
        retrieved_memories = []

        for result in results:
            memory_id = result.id
            payload = result.payload

            strength = self._calculate_memory_strength(payload, current_time)

            # Update access stats for all retrieved memories
            payload["last_accessed"] = current_time
            payload["retrieval_count"] += 1
            memories_to_update.append({"id": memory_id, "payload": payload})

            retrieved_memories.append({
                "id": memory_id,
                "strength": strength,
                "score": result.score,
                "payload": payload,
            })

        # Update accessed memories in background (non-blocking)
        if memories_to_update:
            asyncio.create_task(self._update_accessed_memories(memories_to_update))

        # Sort by similarity score only
        retrieved_memories.sort(key=lambda x: x["score"], reverse=True)

        return retrieved_memories

    async def _update_accessed_memories(self, memories_to_update: List[Dict[str, Any]]):
        """Asynchronously update access stats for retrieved memories.

        Args:
            memories_to_update: List of dicts containing 'id' and 'payload' keys
        """
        if not memories_to_update:
            return

        try:
            points = [
                PointStruct(
                    id=mem["id"],
                    payload=mem["payload"],
                    vector={},  # Keep existing vectors
                )
                for mem in memories_to_update
            ]

            await self.client.upsert(
                collection_name=self.collection_name, points=points
            )
        except Exception as e:
            current_app.logger.error(f"Failed to update accessed memories: {e}")

    async def _cleanup_weak_memories(self):
        """Remove memories below strength threshold or when at capacity."""
        # Get all memories to check their strength
        scroll_result = await self.client.scroll(
            collection_name=self.collection_name,
            limit=self.max_memories + 1000,  # Get more than max to find weak ones
            with_payload=True,
        )
        all_memories = scroll_result[0]

        if len(all_memories) <= self.max_memories:
            return

        # Calculate strength for all memories
        memory_strengths = []
        for memory_point in all_memories:
            payload = memory_point.payload
            strength = self._calculate_memory_strength(payload)
            memory_strengths.append((memory_point.id, strength))

        # Sort by strength and remove weakest
        memory_strengths.sort(key=lambda x: x[1])

        # Delete memories below threshold or excess memories
        to_delete = []
        for memory_id, strength in memory_strengths:
            if (
                strength < self.min_strength_threshold
                or len(memory_strengths) - len(to_delete) > self.max_memories
            ):
                to_delete.append(memory_id)

        if to_delete:
            await self.client.delete(
                collection_name=self.collection_name,
                points_selector=to_delete,
            )
            print(f"Deleted {len(to_delete)} weak memories")


# Standalone script execution
if __name__ == "__main__":

    async def main():
        import csv
        import os

        # Load conversation data from CSV file
        csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "scripts",
            "memories_with_timestamps.csv",
        )

        conversation_data = []
        print(f"Loading conversation data from {csv_path}...")

        with open(csv_path, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                conversation_data.append({
                    "content": row["utterance"],
                    "role": row["role"],
                    "timestamp": float(row["unix_timestamp"]),
                })

        print(f"Loaded {len(conversation_data)} conversation entries")

        # Initialise memory system in bulk mode for fast testing
        print("Initializing memory system in bulk mode...")
        memory_sys = MemoryService()
        memory_sys.bulk_mode = True
        memory_sys.init_standalone()
        await memory_sys._setup_collection()

        # Prepare all memories for bulk storage using real vectors
        print(f"Preparing {len(conversation_data)} memories for bulk storage...")
        start_time = time.time()

        memories_to_store = []
        for i, entry in enumerate(conversation_data):
            # Generate real vectors for each piece of content
            vectors = await memory_sys.generate_vectors(
                content=entry["content"],
                role=entry["role"],
                timestamp=entry["timestamp"],
                context_tags=["conversation", "csv_data"],
            )
            memories_to_store.append(
                (entry["content"], vectors, ["conversation", "csv_data"], entry["role"])
            )

            # Print progress for longer operations
            if (i + 1) % 50 == 0:
                print(
                    "  Generated vectors for"
                    f" {i + 1}/{len(conversation_data)} memories..."
                )

        prep_time = time.time() - start_time
        print(f"Memory preparation took: {prep_time:.2f} seconds")

        # Bulk store all memories
        print("Bulk storing memories...")
        storage_start = time.time()
        memory_ids = await memory_sys.store_memories_bulk(memories_to_store)
        storage_time = time.time() - storage_start

        print(
            f"Bulk storage of {len(memory_ids)} memories took:"
            f" {storage_time:.2f} seconds"
        )
        print(
            f"Average time per memory: {storage_time / len(memory_ids) * 1000:.1f} ms"
        )

        # Retrieve memories using real query vectors
        print("\nRetrieving memories...")
        query_entry = random.choice(conversation_data)
        query_vectors = await memory_sys.generate_vectors(
            content=query_entry["content"],
            role=query_entry["role"],
            timestamp=query_entry["timestamp"],
            context_tags=["conversation", "query"],
        )
        print(f"Query: '{query_entry['content']}' (role: {query_entry['role']})")

        retrieved = await memory_sys.retrieve_memories(query_vectors, limit=5)
        print(f"Retrieved {len(retrieved)} memories:")
        for mem in retrieved:
            print(f"- {mem['payload']['content']}")
            print(f"  {mem}")

        # Get all memories with strength for analysis
        print("\nMemory analysis:")
        scroll_result = await memory_sys.client.scroll(
            collection_name=memory_sys.collection_name,
            limit=memory_sys.max_memories,
            with_payload=True,
        )
        all_memories = scroll_result[0]

        if all_memories:
            # Calculate strength for all memories
            memory_analysis = []
            current_time = time.time()

            for memory_point in all_memories:
                payload = memory_point.payload
                strength = memory_sys._calculate_memory_strength(payload, current_time)
                memory_analysis.append({
                    "content": (
                        payload["content"][:100] + "..."
                        if len(payload["content"]) > 100
                        else payload["content"]
                    ),
                    "strength": strength,
                })

            # Sort by strength
            strongest = max(memory_analysis, key=lambda x: x["strength"])
            weakest = min(memory_analysis, key=lambda x: x["strength"])

            print(f"\nStrongest memory (strength: {strongest['strength']:.3f}):")
            print(f"  {strongest['content']}")

            print(f"\nWeakest memory (strength: {weakest['strength']:.3f}):")
            print(f"  {weakest['content']}")

    asyncio.run(main())
