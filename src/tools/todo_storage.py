"""Shared storage for simplified todo tools."""

from typing import Dict, List
from uuid import UUID

# Shared in-memory storage for todos per conversation
todos_storage: Dict[UUID, List[Dict[str, str]]] = {}
