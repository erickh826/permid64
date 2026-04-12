"""
codec.py — Fixed-width Base62 and Crockford Base32 for unsigned 64-bit integers.

These codecs are **representation only**: they do not add secrecy.  Any
token can be converted back to a bare integer offline.

Base62
------
Default alphabet: ``0-9``, ``A-Z``, ``a-z`` (62 symbols).  Output is always
11 characters (leading ``0`` padding).  Case-sensitive.

Crockford Base32
----------------
Alphabet ``0123456789ABCDEFGHJKMNPQRSTVWXYZ`` (no I, L, O, U).  Output is
always 13 uppercase characters.

Decoding is strict by default (``strict=True``): only uppercase alphabet
characters are accepted.  Pass ``strict=False`` for spec-compliant lenient
mode: input is uppercased before decoding and the Crockford substitutions
``I``/``L`` -> ``1`` and ``O`` -> ``0`` are applied automatically.
"""
from __future__ import annotations

from ._constants import MASK64

# 0-9, A-Z, a-z — fixed order for stable encoding
_BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_BASE62_WIDTH = 11
_BASE62_INDEX = {c: i for i, c in enumerate(_BASE62_ALPHABET)}

# Crockford: excludes I, L, O, U from letters
_CROCKFORD32_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CROCKFORD32_WIDTH = 13
_CROCKFORD32_INDEX = {c: i for i, c in enumerate(_CROCKFORD32_ALPHABET)}


def _require_u64(name: str, n: int) -> int:
    if not isinstance(n, int):
        raise TypeError(f"{name} must be int, got {type(n).__name__}")
    if n < 0 or n > MASK64:
        raise ValueError(f"{name} must be in [0, 2^64-1], got {n}")
    return n


def u64_to_base62(n: int) -> str:
    """Encode ``n`` as a fixed-width 11-character Base62 string."""
    v = _require_u64("n", n)
    digits: list[str] = []
    for _ in range(_BASE62_WIDTH):
        v, r = divmod(v, 62)
        digits.append(_BASE62_ALPHABET[r])
    return "".join(reversed(digits))


def base62_to_u64(s: str) -> int:
    """Decode a Base62 string produced by :func:`u64_to_base62`."""
    if not isinstance(s, str):
        raise TypeError(f"s must be str, got {type(s).__name__}")
    if len(s) != _BASE62_WIDTH:
        raise ValueError(f"Base62 token must be length {_BASE62_WIDTH}, got {len(s)}")
    v = 0
    for c in s:
        if c not in _BASE62_INDEX:
            raise ValueError(f"invalid Base62 character: {c!r}")
        v = v * 62 + _BASE62_INDEX[c]
        if v > MASK64:
            raise ValueError("Base62 value overflows unsigned 64-bit range")
    return v


def u64_to_crockford32(n: int) -> str:
    """Encode ``n`` as a fixed-width 13-character Crockford Base32 string."""
    v = _require_u64("n", n)
    digits: list[str] = []
    for _ in range(_CROCKFORD32_WIDTH):
        v, r = divmod(v, 32)
        digits.append(_CROCKFORD32_ALPHABET[r])
    return "".join(reversed(digits))


# Crockford substitution map for lenient decoding (I/L -> 1, O -> 0)
_CROCKFORD32_SUBSTITUTIONS = str.maketrans("IiLlOo", "111100")


def crockford32_to_u64(s: str, *, strict: bool = True) -> int:
    """
    Decode a Crockford Base32 string to an unsigned 64-bit integer.

    Parameters
    ----------
    s:
        The token to decode.  Must be exactly 13 characters.
    strict:
        If ``True`` (default), only characters in the uppercase Crockford
        alphabet are accepted.  If ``False``, the full Crockford spec is
        applied: input is uppercased first, and ``I``/``L`` are treated as
        ``1`` while ``O`` is treated as ``0`` before decoding.
    """
    if not isinstance(s, str):
        raise TypeError(f"s must be str, got {type(s).__name__}")
    if not strict:
        s = s.upper().translate(_CROCKFORD32_SUBSTITUTIONS)
    if len(s) != _CROCKFORD32_WIDTH:
        raise ValueError(
            f"Crockford Base32 token must be length {_CROCKFORD32_WIDTH}, got {len(s)}"
        )
    v = 0
    for c in s:
        if c not in _CROCKFORD32_INDEX:
            raise ValueError(f"invalid Crockford Base32 character: {c!r}")
        v = v * 32 + _CROCKFORD32_INDEX[c]
        # 32^13 = 2^65 > 2^64, so certain 13-char strings are out of range.
        # Check after each step so we fail fast on the first overflowing digit.
        if v > MASK64:
            raise ValueError("Crockford Base32 value overflows unsigned 64-bit range")
    return v

