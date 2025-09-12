"""Unit tests for text_utils module."""

import pytest

from src.modules.text_utils import chunk_text_by_sentence


@pytest.mark.asyncio
async def test_chunk_text_by_sentence_min_chunk():
    """Test basic sentence splitting."""
    text = "Hello world. This is a test. Goodbye!"
    result = chunk_text_by_sentence(text)
    assert result == ["Hello world.", "This is a test.", "Goodbye!"]


@pytest.mark.asyncio
async def test_chunk_text_by_sentence_abbreviations():
    """Test handling of abbreviations."""
    text = "Thank you for calling Pacific Paradoxes, Mr. Baldwin. I'll connect you now."
    result = chunk_text_by_sentence(text)
    assert result == [
        "Thank you for calling Pacific Paradoxes, Mr. Baldwin.",
        "I'll connect you now.",
    ]


@pytest.mark.asyncio
async def test_chunk_text_by_sentence_edge_cases():
    """Test edge cases."""
    # Empty string
    assert chunk_text_by_sentence("") == []

    # No punctuation
    text = "This has no sentence endings"
    assert chunk_text_by_sentence(text) == [text]

    # Mixed abbreviations and normal sentences
    text = "Dr. Smith is here. The meeting starts at 2 p.m. Be on time."
    result = chunk_text_by_sentence(text)
    assert result == ["Dr. Smith is here.", "The meeting starts at 2 p.m. Be on time."]


@pytest.mark.asyncio
async def test_chunk_text_by_sentence_newlines():
    """Test sentence splitting with newline characters."""
    # Basic newline splitting
    text = "First sentence.\nSecond sentence!\nThird sentence?"
    result = chunk_text_by_sentence(text)
    assert result == ["First sentence.", "Second sentence!", "Third sentence?"]

    # Mixed punctuation and newlines
    text = "Hello world.\nHow are you?\nI am fine! Thanks."
    result = chunk_text_by_sentence(text)
    assert result == ["Hello world.", "How are you?", "I am fine!", "Thanks."]

    # Abbreviations with newlines
    text = "Dr. Smith is here.\nMr. Jones arrived."
    result = chunk_text_by_sentence(text)
    assert result == ["Dr. Smith is here.", "Mr. Jones arrived."]

    # Multiple newlines
    text = "First line.\n\nSecond line after blank line."
    result = chunk_text_by_sentence(text)
    assert result == ["First line.", "Second line after blank line."]

    # Newline without other punctuation
    text = "Line one\nLine two\nLine three"
    result = chunk_text_by_sentence(text)
    assert result == ["Line one", "Line two", "Line three"]
