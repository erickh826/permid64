"""
test_codec.py — Base62 and Crockford Base32 codecs.
"""
import pytest
from hypothesis import given
import hypothesis.strategies as st

from permid64.codec import (
    base62_to_u64,
    crockford32_to_u64,
    u64_to_base62,
    u64_to_crockford32,
)

MASK64 = 0xFFFFFFFFFFFFFFFF


@pytest.mark.parametrize(
    "n",
    [0, 1, 42, 0xFFFFFFFF, 0x100000000, MASK64],
)
def test_base62_roundtrip_fixed_width(n):
    s = u64_to_base62(n)
    assert len(s) == 11
    assert base62_to_u64(s) == n


@pytest.mark.parametrize(
    "n",
    [0, 1, 42, 0xFFFFFFFF, MASK64],
)
def test_crockford32_roundtrip_fixed_width(n):
    s = u64_to_crockford32(n)
    assert len(s) == 13
    assert s == s.upper()
    assert crockford32_to_u64(s) == n


@given(st.integers(min_value=0, max_value=MASK64))
def test_base62_hypothesis_roundtrip(n):
    assert base62_to_u64(u64_to_base62(n)) == n


@given(st.integers(min_value=0, max_value=MASK64))
def test_crockford32_hypothesis_roundtrip(n):
    assert crockford32_to_u64(u64_to_crockford32(n)) == n


def test_base62_invalid_length():
    with pytest.raises(ValueError, match="length"):
        base62_to_u64("0" * 10)
    with pytest.raises(ValueError, match="length"):
        base62_to_u64("0" * 12)


def test_base62_invalid_char():
    with pytest.raises(ValueError, match="invalid"):
        base62_to_u64("0000000000!")


def test_base62_overflow_token():
    # Eleven max digits in base62 exceeds 2^64-1
    token = "z" * 11
    with pytest.raises(ValueError, match="overflow"):
        base62_to_u64(token)


def test_crockford32_invalid_char():
    with pytest.raises(ValueError, match="invalid"):
        crockford32_to_u64("000000000000I")


def test_crockford32_lowercase_rejected_strict():
    """Default strict=True rejects lowercase input."""
    with pytest.raises(ValueError):
        crockford32_to_u64("000000000000f")


def test_crockford32_lenient_accepts_lowercase():
    """strict=False normalises to uppercase per Crockford spec."""
    s = u64_to_crockford32(42)
    assert crockford32_to_u64(s.lower(), strict=False) == 42


def test_crockford32_lenient_substitutes_i_l_o():
    """strict=False maps I/L -> 1, O -> 0 per Crockford spec."""
    # Build a token and manually replace characters with spec-legal substitutes
    s = u64_to_crockford32(0)
    # s is all '0's; replace first char with 'O' (Crockford substitute for 0)
    lenient_s = "O" + s[1:]
    assert crockford32_to_u64(lenient_s, strict=False) == 0


def test_crockford32_overflow_token():
    """
    32^13 = 2^65 > 2^64 - 1.
    The maximum 13-char Crockford string 'ZZZZZZZZZZZZZ' decodes to
    32^13 - 1 which exceeds the 64-bit range and must raise.
    """
    token = "Z" * 13  # all max symbols: 32^13 - 1 ≈ 3.6 × 10^19 > 2^64 - 1
    with pytest.raises(ValueError, match="overflow"):
        crockford32_to_u64(token)


def test_u64_type_errors():
    with pytest.raises(TypeError):
        u64_to_base62("1")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        base62_to_u64(123)  # type: ignore[arg-type]


def test_u64_range_errors():
    with pytest.raises(ValueError):
        u64_to_base62(-1)
    with pytest.raises(ValueError):
        u64_to_base62(MASK64 + 1)
