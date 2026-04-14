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

    # Fixed-width string tokens (same integer space as next_u64)
    tok = gen.next_base62()
    meta2 = gen.decode_base62(tok)

    # No permutation — layout + counter only (see IdentityPermutation)
    gen_plain = Id64.identity(instance_id=42, state_file="plain.state")
"""
from __future__ import annotations

from .codec import base62_to_u64, crockford32_to_u64, u64_to_base62, u64_to_crockford32
from .layout import Layout64
from .permutation import (
    Feistel64Permutation,
    IdentityPermutation,
    MultiplyOddPermutation,
    Permutation64Protocol,
)
from .source import PersistentCounterSource, ProcessSafeCounterSource
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
        source: "PersistentCounterSource | ProcessSafeCounterSource",
        permutation: Permutation64Protocol,
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

    @classmethod
    def identity(
        cls,
        instance_id: int,
        state_file: str,
        block_size: int = 4096,
    ) -> "Id64":
        """
        Create a generator with no bit mixing — ``forward`` / ``inverse`` are
        identity maps on 64 bits.  Counter + :class:`Layout64` only; useful
        for tests or when obfuscation is not required.
        """
        return cls(
            instance_id=instance_id,
            source=PersistentCounterSource(state_file, block_size),
            permutation=IdentityPermutation(),
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

    def next_base62(self) -> str:
        """
        Return :meth:`next_u64` encoded as a fixed-width 11-character Base62
        string (alphabet ``0-9A-Za-z``, case-sensitive).

        .. note::
            v0.2 exposes one method per encoding (``next_base62``,
            ``next_base32``).  A future version may unify these behind an
            ``encoding=`` parameter if the number of supported codecs grows.
        """
        return u64_to_base62(self.next_u64())

    def decode_base62(self, token: str) -> DecodedId:
        """Decode a Base62 token produced by :meth:`next_base62`."""
        return self.decode(base62_to_u64(token))

    def next_base32(self) -> str:
        """
        Return :meth:`next_u64` encoded as a fixed-width 13-character
        **Crockford Base32** string (uppercase, no I/L/O/U).

        .. note::
            v0.2 exposes one method per encoding (``next_base62``,
            ``next_base32``).  A future version may unify these behind an
            ``encoding=`` parameter if the number of supported codecs grows.
        """
        return u64_to_crockford32(self.next_u64())

    def decode_base32(self, token: str) -> DecodedId:
        """Decode a Crockford Base32 token produced by :meth:`next_base32`."""
        return self.decode(crockford32_to_u64(token))
