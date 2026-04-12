"""
test_permutation.py — Unit tests for MultiplyOddPermutation and Feistel64Permutation.
"""
import pytest
from permid64.permutation import (
    Feistel64Permutation,
    IdentityPermutation,
    MultiplyOddPermutation,
)

MASK64 = 0xFFFFFFFFFFFFFFFF

SAMPLE_VALUES = [0, 1, 42, 0xDEADBEEF, 0xFFFFFFFFFFFFFFFF, 123456789012345678]


class TestIdentityPermutation:
    def test_forward_inverse_are_identity_masked(self):
        perm = IdentityPermutation()
        for v in SAMPLE_VALUES:
            assert perm.forward(v) == (v & MASK64)
            assert perm.inverse(v) == (v & MASK64)

    def test_roundtrip(self):
        perm = IdentityPermutation()
        for v in SAMPLE_VALUES:
            assert perm.inverse(perm.forward(v)) == (v & MASK64)


class TestMultiplyOddPermutation:
    def _make(self, a=0x9E3779B185EBCA87, b=0x6A09E667F3BCC909):
        return MultiplyOddPermutation(a=a, b=b)

    def test_forward_inverse_roundtrip(self):
        perm = self._make()
        for v in SAMPLE_VALUES:
            assert perm.inverse(perm.forward(v)) == v, f"Failed at {v:#x}"

    def test_inverse_forward_roundtrip(self):
        perm = self._make()
        for v in SAMPLE_VALUES:
            assert perm.forward(perm.inverse(v)) == v, f"Failed at {v:#x}"

    def test_output_in_64bit_range(self):
        perm = self._make()
        for v in SAMPLE_VALUES:
            out = perm.forward(v)
            assert 0 <= out <= MASK64

    def test_even_a_raises(self):
        with pytest.raises(ValueError):
            MultiplyOddPermutation(a=2, b=0)

    def test_different_keys_give_different_outputs(self):
        p1 = MultiplyOddPermutation(a=0x9E3779B185EBCA87, b=0)
        p2 = MultiplyOddPermutation(a=0x6C62272E07BB0143, b=0)  # must be odd
        assert p1.forward(42) != p2.forward(42)

    def test_bijection_over_small_range(self):
        """forward must be a bijection: no two inputs map to same output."""
        perm = self._make()
        outputs = {perm.forward(i) for i in range(10_000)}
        assert len(outputs) == 10_000


class TestFeistel64Permutation:
    def _make(self, key=0xDEADBEEFCAFEBABE, rounds=6):
        return Feistel64Permutation(key=key, rounds=rounds)

    def test_forward_inverse_roundtrip(self):
        perm = self._make()
        for v in SAMPLE_VALUES:
            assert perm.inverse(perm.forward(v)) == v, f"Failed at {v:#x}"

    def test_inverse_forward_roundtrip(self):
        perm = self._make()
        for v in SAMPLE_VALUES:
            assert perm.forward(perm.inverse(v)) == v, f"Failed at {v:#x}"

    def test_output_in_64bit_range(self):
        perm = self._make()
        for v in SAMPLE_VALUES:
            out = perm.forward(v)
            assert 0 <= out <= MASK64

    def test_different_keys_give_different_outputs(self):
        p1 = Feistel64Permutation(key=0xDEADBEEFCAFEBABE)
        p2 = Feistel64Permutation(key=0xCAFEBABEDEADBEEF)
        assert p1.forward(42) != p2.forward(42)

    def test_rounds_parameter(self):
        for rounds in [1, 2, 4, 6, 8, 12]:
            perm = Feistel64Permutation(key=0x1234, rounds=rounds)
            for v in SAMPLE_VALUES:
                assert perm.inverse(perm.forward(v)) == v

    def test_invalid_rounds_raises(self):
        with pytest.raises(ValueError):
            Feistel64Permutation(key=0x1234, rounds=0)

    def test_bijection_over_small_range(self):
        perm = self._make()
        outputs = {perm.forward(i) for i in range(10_000)}
        assert len(outputs) == 10_000
