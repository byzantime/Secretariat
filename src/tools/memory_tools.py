"""Memory search tools for agent."""

from datetime import datetime

from pydantic_ai import RunContext
from quart import current_app


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

    # Get current conversation ID to exclude from results
    conversation = ctx.deps.get("conversation")
    current_conversation_id = None
    if conversation:
        current_conversation_id = getattr(conversation, "id", None)

    try:
        # Generate query vectors for semantic search
        query_vectors = await memory_service.generate_vectors(
            content=query,
            role="user",  # Role for query doesn't matter much for semantic search
            timestamp=None,  # Current time will be used
            context_tags=["search_query"],
        )

        # Retrieve relevant memories (limit to 15 for reasonable response size)
        memories = await memory_service.retrieve_memories(
            query_vectors=query_vectors, limit=15
        )

        if not memories:
            return "No relevant memories found for your search query."

        # Filter out memories from current conversation
        filtered_memories = []
        for memory in memories:
            memory_conversation_id = memory["payload"].get("conversation_id")
            if memory_conversation_id != current_conversation_id:
                filtered_memories.append(memory)

        if not filtered_memories:
            return "No relevant memories found from previous conversations."

        # Format results as markdown
        result = f'## Memory Search Results for: "{query}"\n\n'
        result += (
            f"Found {len(filtered_memories)} relevant memories from previous"
            " conversations:\n\n"
        )

        for i, memory in enumerate(filtered_memories, 1):
            payload = memory["payload"]
            content = payload["content"]
            role = payload.get("role", "unknown")
            created_at = payload.get("created_at")
            similarity_score = memory.get("score", 0)

            # Format timestamp
            if created_at:
                try:
                    timestamp = datetime.fromtimestamp(created_at).strftime(
                        "%Y-%m-%d %H:%M"
                    )
                except (ValueError, TypeError):
                    timestamp = "unknown time"
            else:
                timestamp = "unknown time"

            result += f"**{i}.** `{timestamp}` **{role}**: {content}\n"

        current_app.logger.info(result)
        return result.strip()

    except Exception as e:
        current_app.logger.error(f"Error in memory search: {str(e)}")
        return f"Error occurred while searching memories: {str(e)}"
