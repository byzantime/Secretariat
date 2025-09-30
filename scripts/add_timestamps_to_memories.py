#!/usr/bin/env python3
"""
Script to add Unix timestamps to sample data memories and export as CSV.

This script:
1. Loads memories from src/modules/sample_data.py
2. Adds random timestamps between 2025-01-01 and now
3. Ensures assistant responses are 30 seconds after user messages
4. Exports the data as CSV format
"""

import csv
import random
import sys
from datetime import datetime
from datetime import timezone
from pathlib import Path

from modules.sample_data import memories

# Add src directory to Python path to import sample_data
script_dir = Path(__file__).parent
src_dir = script_dir.parent / "src"
sys.path.insert(0, str(src_dir))


def generate_random_timestamp():
    """Generate a random Unix timestamp between 2025-01-01 and now."""
    # Start date: 2025-01-01 00:00:00 UTC
    start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    start_timestamp = int(start_date.timestamp())

    # Current date
    current_timestamp = int(datetime.now(timezone.utc).timestamp())

    # Generate random timestamp between start and now
    return random.randint(start_timestamp, current_timestamp)


def add_timestamps_to_memories():
    """
    Add timestamps to memories data.

    Returns:
        List of tuples: (utterance, role, unix_timestamp)
    """
    timestamped_memories = []

    # Process memories in pairs (user message followed by assistant response)
    i = 0
    while i < len(memories):
        if i + 1 < len(memories):
            user_utterance, user_role = memories[i]
            assistant_utterance, assistant_role = memories[i + 1]

            # Verify this is actually a user-assistant pair
            if user_role == "user" and assistant_role == "assistant":
                # Generate random timestamp for user message
                user_timestamp = generate_random_timestamp()

                # Assistant response is 30 seconds later
                assistant_timestamp = user_timestamp + 30

                # Add both to the list
                timestamped_memories.append((user_utterance, user_role, user_timestamp))
                timestamped_memories.append(
                    (assistant_utterance, assistant_role, assistant_timestamp)
                )

                i += 2  # Move to next pair
            else:
                # Handle case where pairing is broken (shouldn't happen with current data)
                print(
                    f"Warning: Unexpected role pairing at index {i}: {user_role},"
                    f" {assistant_role}"
                )
                timestamp = generate_random_timestamp()
                timestamped_memories.append((user_utterance, user_role, timestamp))
                i += 1
        else:
            # Handle last entry if odd number of entries
            utterance, role = memories[i]
            timestamp = generate_random_timestamp()
            timestamped_memories.append((utterance, role, timestamp))
            i += 1

    return timestamped_memories


def export_to_csv(timestamped_memories, output_file="memories_with_timestamps.csv"):
    """
    Export timestamped memories to CSV file.

    Args:
        timestamped_memories: List of tuples (utterance, role, unix_timestamp)
        output_file: Output CSV filename
    """
    output_path = script_dir / output_file

    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)

        # Write header
        writer.writerow(["utterance", "role", "unix_timestamp"])

        # Write data
        for utterance, role, timestamp in timestamped_memories:
            writer.writerow([utterance, role, timestamp])

    print(f"CSV file created: {output_path}")
    print(f"Total entries: {len(timestamped_memories)}")


def main():
    """Main function to execute the script."""
    print("Loading memories from sample_data.py...")
    print(f"Found {len(memories)} memory entries")

    print("Adding timestamps...")
    timestamped_memories = add_timestamps_to_memories()

    print("Exporting to CSV...")
    export_to_csv(timestamped_memories)

    print("Done!")


if __name__ == "__main__":
    main()
