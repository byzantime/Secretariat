"""Memory search tools for agent."""

from datetime import datetime

from pydantic_ai import RunContext
from pydantic_ai.toolsets import FunctionToolset
from quart import current_app

# Create toolset for memory tools
memory_toolset = FunctionToolset()

try:
    from qdrant_client.models import FieldCondition
    from qdrant_client.models import Filter
    from qdrant_client.models import MatchValue

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    # Create stub classes for when qdrant is not available
    Filter = None
    FieldCondition = None
    MatchValue = None


# Only register memory tool if dependencies available
if QDRANT_AVAILABLE:

    @memory_toolset.tool
    async def memory_search(ctx: RunContext[dict], query: str) -> str:
        """Use this tool to search through past conversation memories using semantic search.

        This tool searches across all previous conversations (excluding the current one)
        to find relevant memories that match the semantic meaning of your query. This is
        useful for:

        **When to use this tool:**
        - Finding information discussed in previous conversations
        - Locating past decisions or agreements made with the user
        - Searching for specific topics or concepts mentioned before
        - Retrieving context from earlier interactions
        - Looking up previous explanations or solutions provided

        **Examples of good queries:**
        - "project deadlines mentioned last week"
        - "user's preferences for communication style"
        - "previous discussions about budget constraints"
        - "technical solutions we explored for database issues"
        - "meeting notes from client presentations"

        Args:
            query: The search query to find relevant memories. Use descriptive
                   phrases that capture the semantic meaning of what you're looking for.

        Returns:
            A markdown-formatted list of relevant memories with timestamps, roles,
            and utterances, or a message if no memories are found.
        """
        current_app.logger.info(f"🔧 TOOL CALLED: memory_search - query: {query}")

        memory_service = current_app.extensions["memory"]
        if not memory_service.is_available():
            return "Memory search is not available at the moment."

        # Generate query vectors for semantic search
        query_vectors = await memory_service.generate_vectors(
            content=query,
            role="user",  # Role for query doesn't matter much for semantic search
            timestamp=None,  # Current time will be used
            context_tags=["search_query"],
        )

        # Get current conversation ID to exclude from results
        conversation = ctx.deps.get("conversation")
        current_conversation_id = None
        if conversation:
            current_conversation_id = getattr(conversation, "id", None)

        # Create filter to exclude current conversation
        query_filter = None
        if current_conversation_id:
            query_filter = Filter(
                must_not=[
                    FieldCondition(
                        key="conversation_id",
                        match=MatchValue(value=str(current_conversation_id)),
                    )
                ]
            )

        # Retrieve relevant memories (limit to 15 for reasonable response size)
        memories = await memory_service.retrieve_memories(
            query_vectors=query_vectors, limit=15, query_filter=query_filter
        )

        if not memories:
            return "No relevant memories found from previous conversations."

        # Format results as markdown
        result = f'## Memory Search Results for: "{query}"\n\n'
        result += (
            f"Found {len(memories)} relevant memories from previous conversations:\n\n"
        )

        for i, memory in enumerate(memories, 1):
            payload = memory["payload"]
            content = payload["content"]
            role = payload.get("role", "unknown")
            created_at = payload.get("created_at")

            # Format timestamp
            timestamp = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M")
            result += f"**{i}.** `{timestamp}` **{role}**: {content}\n"

        current_app.logger.info(result)
        return result.strip()
