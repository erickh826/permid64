"""
types.py — Shared dataclasses for id64.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DecodedId:
    """Result of Id64.decode()."""
    raw: int          # the raw 64-bit value before permutation
    instance_id: int  # the machine / process shard identifier
    sequence: int     # monotonically increasing counter value
