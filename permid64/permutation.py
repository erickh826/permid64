"""
permutation.py — Invertible 64-bit permutations for id64.

Two implementations are provided:

MultiplyOddPermutation
    f(x) = (a·x + b) mod 2^64
    Requires a to be odd (guarantees the modular inverse exists).
    Extremely fast; statistical mixing is adequate for opaque IDs.

Feistel64Permutation
    A balanced 64-bit Feistel network (left/right each 32 bits).
    The network is inherently invertible regardless of the round function.
    Round keys are derived from a single 64-bit seed via a simple KDF.
    Default: 6 rounds (good mixing / speed trade-off).
"""
from __future__ import annotations

MASK64 = 0xFFFFFFFFFFFFFFFF
MASK32 = 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Multiply-odd (affine) permutation
# ---------------------------------------------------------------------------

class MultiplyOddPermutation:
    """
    f(x) = (a·x + b) mod 2^64

    ``a`` must be odd so that the modular inverse exists.
    ``b`` can be any 64-bit integer (acts as an additive offset / "salt").
    """

    def __init__(self, a: int, b: int) -> None:
        a = a & MASK64
        if a % 2 == 0:
            raise ValueError(
                f"'a' must be odd for the permutation to be invertible mod 2^64, got {a:#x}"
            )
        self.a: int = a
        self.b: int = b & MASK64
        # Compute modular inverse of a mod 2^64 via extended Euclidean algorithm.
        self.a_inv: int = pow(a, -1, 1 << 64)

    def forward(self, x: int) -> int:
        return (x * self.a + self.b) & MASK64

    def inverse(self, y: int) -> int:
        return ((y - self.b) * self.a_inv) & MASK64


# ---------------------------------------------------------------------------
# Feistel-64 permutation
# ---------------------------------------------------------------------------

class Feistel64Permutation:
    """
    A balanced Feistel network over 64-bit integers.

    The 64-bit block is split into two 32-bit halves (L, R).
    Each round:
        L', R' = R, L XOR F(R, round_key)

    Because F need not be invertible, the whole network is still
    a permutation — the inverse simply applies rounds in reverse
    order swapping the roles of L and R.

    Round keys are derived from ``key`` using a simple xorshift-multiply KDF.
    """

    def __init__(self, key: int, rounds: int = 6) -> None:
        if rounds < 1:
            raise ValueError("rounds must be >= 1")
        self.rounds = rounds
        self.round_keys = self._derive_round_keys(key & MASK64, rounds)

    # ------------------------------------------------------------------
    # Key derivation
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_round_keys(key: int, rounds: int) -> list[int]:
        """Derive ``rounds`` independent 32-bit sub-keys from a 64-bit seed."""
        keys: list[int] = []
        x = key & MASK64
        for _ in range(rounds):
            # xorshift64* step
            x ^= (x >> 12) & MASK64
            x ^= (x << 25) & MASK64
            x ^= (x >> 27) & MASK64
            x = (x * 0x2545F4914F6CDD1D) & MASK64
            keys.append(x & MASK32)
        return keys

    # ------------------------------------------------------------------
    # Round function  F: (32-bit half, 32-bit key) -> 32-bit output
    # ------------------------------------------------------------------

    @staticmethod
    def _round_f(r: int, k: int) -> int:
        x = (r ^ k) & MASK32
        x = (x * 0x9E3779B1) & MASK32
        x ^= (x >> 16)
        x = ((x << 5) | (x >> 27)) & MASK32   # left-rotate 5
        x = (x * 0x85EBCA6B) & MASK32
        x ^= (x >> 13)
        return x & MASK32

    # ------------------------------------------------------------------
    # Forward / inverse
    # ------------------------------------------------------------------

    def forward(self, x: int) -> int:
        l = (x >> 32) & MASK32
        r = x & MASK32
        for k in self.round_keys:
            l, r = r, (l ^ self._round_f(r, k)) & MASK32
        return ((l << 32) | r) & MASK64

    def inverse(self, y: int) -> int:
        l = (y >> 32) & MASK32
        r = y & MASK32
        for k in reversed(self.round_keys):
            l, r = (r ^ self._round_f(l, k)) & MASK32, l
        return ((l << 32) | r) & MASK64
