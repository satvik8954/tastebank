"""Single entry point for writing client feedback into a bank."""

from __future__ import annotations

from ..data import MemoryItem
from .client import hindsight


def retain_item(bank_id: str, item: MemoryItem) -> None:
    # retain_batch rather than retain(): only the batch form accepts observation_scopes.
    hindsight().retain_batch(
        bank_id=bank_id,
        items=[
            {
                "content": item.content,
                "timestamp": item.timestamp,
                "context": item.context,
                "document_id": item.document_id,
                "metadata": item.metadata,
                "tags": item.tags,
                "observation_scopes": item.observation_scopes,
            }
        ],
    )
