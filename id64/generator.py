"""
generator.py — Id64: the main public façade.

Usage
-----
    # Multiplicative (fast, simpler)
    gen = Id64.multiplicative(
        instance_id=42,
        state_file="id64.state",
        block_size=4096,
        a=0x9E3779B185EBCA87,
        b=0x6A09E667F3BCC909,
    )

    # Feistel (better statistical mixing)
    gen = Id64.feistel(
        instance_id=42,
        state_file="id64.state",
        block_size=4096,
        key=0xDEADBEEFCAFEBABE,
        rounds=6,
    )

    id_val = gen.next_u64()      # -> int  (unsigned 64-bit)
    meta   = gen.decode(id_val)  # -> DecodedId(raw, instance_id, sequence)
"""
from __future__ import annotations

from .layout import Layout64
from .permutation import Feistel64Permutation, MultiplyOddPermutation
from .source import PersistentCounterSource
from .types import DecodedId


class Id64:
    """
    Clock-free 64-bit ID generator.

    Architecture
    ------------
    seq  = source.next()                    # monotonic counter (persistent)
    raw  = layout.compose(instance_id, seq) # pack bits
    id64 = permutation.forward(raw)         # obfuscate

    Decode
    ------
    raw  = permutation.inverse(id64)
    meta = layout.decompose(raw)
    """

    def __init__(
        self,
        instance_id: int,
        source: PersistentCounterSource,
        permutation: MultiplyOddPermutation | Feistel64Permutation,
        layout: Layout64 | None = None,
    ) -> None:
        self.instance_id = instance_id
        self.source = source
        self.permutation = permutation
        self.layout = layout or Layout64()

    # ------------------------------------------------------------------
    # Factory constructors
    # ------------------------------------------------------------------

    @classmethod
    def multiplicative(
        cls,
        instance_id: int,
        state_file: str,
        block_size: int = 4096,
        a: int = 0x9E3779B185EBCA87,
        b: int = 0x6A09E667F3BCC909,
    ) -> "Id64":
        """
        Create a generator backed by a multiply-odd (affine) permutation.

        ``a`` defaults to the 64-bit golden-ratio constant; ``b`` adds a
        second independent mixing constant.  Both can be overridden.
        """
        return cls(
            instance_id=instance_id,
            source=PersistentCounterSource(state_file, block_size),
            permutation=MultiplyOddPermutation(a=a, b=b),
        )

    @classmethod
    def feistel(
        cls,
        instance_id: int,
        state_file: str,
        block_size: int = 4096,
        key: int = 0xDEADBEEFCAFEBABE,
        rounds: int = 6,
    ) -> "Id64":
        """
        Create a generator backed by a 64-bit Feistel-network permutation.

        ``key`` is a 64-bit seed from which round keys are derived.
        ``rounds`` defaults to 6 (good mixing / speed balance).
        """
        return cls(
            instance_id=instance_id,
            source=PersistentCounterSource(state_file, block_size),
            permutation=Feistel64Permutation(key=key, rounds=rounds),
        )

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def next_u64(self) -> int:
        """Return the next unique, obfuscated 64-bit ID."""
        seq = self.source.next()
        raw = self.layout.compose(self.instance_id, seq)
        return self.permutation.forward(raw)

    def decode(self, id64: int) -> DecodedId:
        """Reverse a previously generated ID back to its metadata."""
        raw = self.permutation.inverse(id64)
        return self.layout.decompose(raw)
