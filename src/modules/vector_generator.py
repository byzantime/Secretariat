"""
Vector generation module for the memory system.

Provides semantic, temporal, and contextual vector generation capabilities
for creating meaningful embeddings from text content and metadata.
"""

import math
import time
from datetime import datetime
from typing import Dict
from typing import List
from typing import Optional

from sentence_transformers import SentenceTransformer


class SemanticVectorGenerator:
    """Generates semantic embeddings from text content."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialise semantic vector generator.

        Args:
            model_name: Name of the sentence transformer model to use.
                       Default is all-MiniLM-L6-v2 (384 dimensions).
        """
        self.model = SentenceTransformer(model_name)
        self.vector_size = self.model.get_sentence_embedding_dimension()

    def generate(self, text: str) -> List[float]:
        """Generate semantic embedding for given text.

        Args:
            text: Input text to encode

        Returns:
            List of floats representing the semantic embedding
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.vector_size

        embedding = self.model.encode([text.strip()])[0]
        return embedding.tolist()


class TemporalVectorGenerator:
    """Generates temporal embeddings from time information."""

    def __init__(self, vector_size: int = 20):
        """Initialise temporal vector generator.

        Args:
            vector_size: Size of the temporal vector
        """
        self.vector_size = vector_size

    def generate(self, timestamp: Optional[float] = None) -> List[float]:
        """Generate temporal embedding from timestamp.

        Encodes time patterns using cyclical features:
        - Hour of day (0-23)
        - Day of week (0-6)
        - Day of month (1-31)
        - Month of year (1-12)

        Args:
            timestamp: Unix timestamp. If None, uses current time.

        Returns:
            List of floats representing temporal patterns
        """
        if timestamp is None:
            timestamp = time.time()

        dt = datetime.fromtimestamp(timestamp)

        # Create cyclical features using sine/cosine encoding
        # This ensures similar times are close in vector space
        features = []

        # Hour of day (0-23) -> 2 features
        hour_radians = 2 * math.pi * dt.hour / 24
        features.extend([math.sin(hour_radians), math.cos(hour_radians)])

        # Day of week (0-6) -> 2 features
        dow_radians = 2 * math.pi * dt.weekday() / 7
        features.extend([math.sin(dow_radians), math.cos(dow_radians)])

        # Day of month (1-31) -> 2 features
        dom_radians = 2 * math.pi * (dt.day - 1) / 31
        features.extend([math.sin(dom_radians), math.cos(dom_radians)])

        # Month of year (1-12) -> 2 features
        month_radians = 2 * math.pi * (dt.month - 1) / 12
        features.extend([math.sin(month_radians), math.cos(month_radians)])

        # Minute of hour (0-59) -> 2 features
        minute_radians = 2 * math.pi * dt.minute / 60
        features.extend([math.sin(minute_radians), math.cos(minute_radians)])

        # Second of minute (0-59) -> 2 features
        second_radians = 2 * math.pi * dt.second / 60
        features.extend([math.sin(second_radians), math.cos(second_radians)])

        # Time of day as continuous value -> 2 features
        time_of_day = (dt.hour * 3600 + dt.minute * 60 + dt.second) / 86400
        tod_radians = 2 * math.pi * time_of_day
        features.extend([math.sin(tod_radians), math.cos(tod_radians)])

        # Week of year -> 2 features
        week_of_year = dt.isocalendar()[1]
        week_radians = 2 * math.pi * (week_of_year - 1) / 52
        features.extend([math.sin(week_radians), math.cos(week_radians)])

        # Quarter of year -> 2 features
        quarter = (dt.month - 1) // 3
        quarter_radians = 2 * math.pi * quarter / 4
        features.extend([math.sin(quarter_radians), math.cos(quarter_radians)])

        # Day of year -> 2 features
        day_of_year = dt.timetuple().tm_yday
        doy_radians = 2 * math.pi * (day_of_year - 1) / 365
        features.extend([math.sin(doy_radians), math.cos(doy_radians)])

        # Pad or trim to exact vector size
        if len(features) < self.vector_size:
            features.extend([0.0] * (self.vector_size - len(features)))
        elif len(features) > self.vector_size:
            features = features[: self.vector_size]

        return features


class ContextualVectorGenerator:
    """Generates contextual embeddings from context tags and metadata."""

    def __init__(self, vector_size: int = 100):
        """Initialise the contextual vector generator.

        Args:
            vector_size: Size of the contextual vector
        """
        self.vector_size = vector_size
        self.tag_to_index = {}  # Cache for consistent tag encoding
        self.next_index = 0

    def generate(
        self,
        context_tags: Optional[List[str]] = None,
        emotional_charge: float = 0.0,
        distinctiveness: float = 1.0,
    ) -> List[float]:
        """Generate contextual embedding from tags and metadata.

        Args:
            context_tags: List of context tags (tools used, etc.)
            emotional_charge: Emotional intensity (0.0 to 1.0)
            distinctiveness: How distinct this memory is (0.0 to 1.0)

        Returns:
            List of floats representing contextual features
        """
        vector = [0.0] * self.vector_size

        if context_tags:
            # Hash-based encoding for tags
            for tag in context_tags:
                if tag not in self.tag_to_index:
                    self.tag_to_index[tag] = self.next_index % (self.vector_size - 10)
                    self.next_index += 1

                # Set feature for this tag
                index = self.tag_to_index[tag]
                if index < len(vector) - 10:  # Reserve last 10 for metadata
                    vector[index] = 1.0

        # Reserve last few dimensions for metadata
        if self.vector_size >= 3:
            vector[-3] = emotional_charge  # Emotional intensity
            vector[-2] = distinctiveness  # Memory distinctiveness
            vector[-1] = len(context_tags) / 10.0 if context_tags else 0.0  # Tag count

        return vector


class RoleVectorGenerator:
    """Generates role embeddings for user/assistant distinction."""

    def __init__(self):
        """Initialise role vector generator."""
        self.vector_size = 1

    def generate(self, role: str) -> List[float]:
        """Generate role embedding for given role.

        Args:
            role: Role string ("user" or "assistant")

        Returns:
            Single-element list representing the role
        """
        if role == "user":
            return [1.0]
        elif role == "assistant":
            return [0.0]
        else:
            # Fallback for any future roles
            return [0.5]


class VectorGenerator:
    """Main vector generator that combines all vector types."""

    def __init__(
        self,
        semantic_model: str = "all-MiniLM-L6-v2",
        temporal_size: int = 20,
        contextual_size: int = 100,
    ):
        """Initialise combined vector generator.

        Args:
            semantic_model: Sentence transformer model name
            temporal_size: Size of temporal vectors
            contextual_size: Size of contextual vectors
        """
        self.semantic_generator = SemanticVectorGenerator(semantic_model)
        self.temporal_generator = TemporalVectorGenerator(temporal_size)
        self.contextual_generator = ContextualVectorGenerator(contextual_size)
        self.role_generator = RoleVectorGenerator()

    def generate_all(
        self,
        content: str,
        timestamp: Optional[float] = None,
        context_tags: Optional[List[str]] = None,
        emotional_charge: float = 0.0,
        distinctiveness: float = 1.0,
        role: str = "user",
    ) -> Dict[str, List[float]]:
        """Generate all vector types for the given content and metadata.

        Args:
            content: Text content to encode
            timestamp: Unix timestamp (uses current time if None)
            context_tags: List of context tags
            emotional_charge: Emotional intensity (0.0 to 1.0)
            distinctiveness: Memory distinctiveness (0.0 to 1.0)
            role: Role of the speaker ("user" or "assistant")

        Returns:
            Dictionary with 'semantic', 'temporal', 'contextual', and 'role' vectors
        """
        return {
            "semantic": self.semantic_generator.generate(content),
            "temporal": self.temporal_generator.generate(timestamp),
            "contextual": self.contextual_generator.generate(
                context_tags, emotional_charge, distinctiveness
            ),
            "role": self.role_generator.generate(role),
        }

    def get_vector_sizes(self) -> Dict[str, int]:
        """Get the sizes of each vector type."""
        return {
            "semantic": self.semantic_generator.vector_size,
            "temporal": self.temporal_generator.vector_size,
            "contextual": self.contextual_generator.vector_size,
            "role": self.role_generator.vector_size,
        }


# Convenience function for easy usage
def generate_vectors(
    content: str,
    timestamp: Optional[float] = None,
    context_tags: Optional[List[str]] = None,
    emotional_charge: float = 0.0,
    distinctiveness: float = 1.0,
    role: str = "user",
) -> Dict[str, List[float]]:
    """
    Convenience function to generate all vector types.

    Creates a VectorGenerator instance and generates vectors for the given content.

    Args:
        content: Text content to encode
        timestamp: Unix timestamp (uses current time if None)
        context_tags: List of context tags
        emotional_charge: Emotional intensity (0.0 to 1.0)
        distinctiveness: Memory distinctiveness (0.0 to 1.0)
        role: Role of the speaker ("user" or "assistant")

    Returns:
        Dictionary with 'semantic', 'temporal', 'contextual', and 'role' vectors
    """
    generator = VectorGenerator()
    return generator.generate_all(
        content, timestamp, context_tags, emotional_charge, distinctiveness, role
    )


if __name__ == "__main__":
    # Example usage and testing
    print("Testing vector generation...")

    # Test individual generators
    semantic_gen = SemanticVectorGenerator()
    temporal_gen = TemporalVectorGenerator()
    contextual_gen = ContextualVectorGenerator()

    # Test semantic generation
    semantic_vec = semantic_gen.generate("How do I learn to code?")
    print(f"Semantic vector size: {len(semantic_vec)}")
    print(f"Semantic vector (first 5): {semantic_vec[:5]}")

    # Test temporal generation
    temporal_vec = temporal_gen.generate()
    print(f"Temporal vector size: {len(temporal_vec)}")
    print(f"Temporal vector: {temporal_vec}")

    # Test contextual generation
    contextual_vec = contextual_gen.generate(
        context_tags=["coding", "learning", "help"],
        emotional_charge=0.3,
        distinctiveness=0.8,
    )
    print(f"Contextual vector size: {len(contextual_vec)}")
    print(f"Contextual vector (last 5): {contextual_vec[-5:]}")

    # Test combined generation
    print("\nTesting combined vector generation...")
    vectors = generate_vectors(
        "Can you help me learn Python programming?",
        context_tags=["programming", "python", "help"],
        emotional_charge=0.2,
        distinctiveness=0.7,
    )

    for vector_type, vector in vectors.items():
        print(f"{vector_type}: {len(vector)} dimensions")

    print("\nVector generation test completed!")
