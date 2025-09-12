"""
Utility functions for working with text.
"""

import re

# Common abbreviations that shouldn't trigger sentence breaks
ABBREVIATIONS = {
    "mr",
    "mrs",
    "ms",
    "dr",
    "prof",
    "st",
    "ave",
    "blvd",
    "rd",
    "ln",
    "ltd",
    "co",
    "jr",
    "sr",
    "vs",
    "etc",
    "i.e",
    "e.g",
    "a.m",
    "p.m",
}

# Precompile regex for performance
SENTENCE_PATTERN = re.compile(r"([.!?]+)(\s+|$)|\n")
ABBREV_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(abbr) for abbr in ABBREVIATIONS) + r")\.$",
    re.IGNORECASE,
)
TRAILING_PUNCTUATION = re.compile(r"[.!?]+$")


def normalise_text(text: str) -> str:
    """Normalise text for intent processing by converting to lowercase and stripping trailing punctuation."""
    if not text:
        return text
    text = text.lower().strip()
    return TRAILING_PUNCTUATION.sub("", text)


def chunk_text_by_sentence(text: str) -> list:
    """Split text into chunks based on sentence boundaries, handling abbreviations.

    This function splits text on sentence endings (.!?) while being smart about
    common abbreviations that shouldn't trigger splits. Optimized for real-time
    TTS applications.
    """
    if not text:
        return []

    chunks = []
    current_pos = 0

    # Find all potential sentence endings
    for match in SENTENCE_PATTERN.finditer(text):
        if match.group() == "\n":
            # Handle newline case
            end_pos = match.start()
            candidate = text[current_pos:end_pos].strip()
        else:
            # Handle punctuation case
            end_pos = match.start() + len(match.group(1))  # Position after punctuation
            candidate = text[current_pos:end_pos].strip()

            # Skip if this looks like an abbreviation
            if match.group(1) == "." and ABBREV_PATTERN.search(candidate):
                continue

        # Ensure minimum chunk length for TTS quality
        if len(candidate) > 5:
            chunks.append(candidate)
            current_pos = match.end()

    # Add any remaining text
    remaining = text[current_pos:].strip()
    if remaining:
        chunks.append(remaining)

    return [c for c in chunks if c]


def format_numbers(text: str) -> str:
    """Removes whitespaces between numbers in strings."""
    if not any(c.isdigit() for c in text):
        return text

    # Pattern matches consecutive groups of:
    # 1. One or more digits with optional whitespace
    # 2. Followed by optional punctuation
    pattern = r"(\d+(?:\s+\d+)*)([\W_]*)"

    def replace(match):
        numbers, punct = match.groups()
        return numbers.replace(" ", "") + punct

    return re.sub(pattern, replace, text)
