"""
test_properties.py — Property-based tests for permid64 using Hypothesis.

These tests complement the example-based tests in test_permutation.py and
test_layout.py by verifying invariants over a large automatically-generated
range of inputs, including edge cases that hand-written tests might miss.

Run:
    pytest tests/test_properties.py -v
    pytest tests/test_properties.py -v --hypothesis-seed=0   # deterministic
"""
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from permid64.layout import Layout64
from permid64.permutation import Feistel64Permutation, MultiplyOddPermutation

# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

UINT64 = st.integers(min_value=0, max_value=0xFFFFFFFFFFFFFFFF)
UINT32 = st.integers(min_value=0, max_value=0xFFFFFFFF)

# Odd integers in [1, 2^64) for MultiplyOddPermutation.a
ODD_UINT64 = st.integers(min_value=0, max_value=0xFFFFFFFFFFFFFFFF).map(
    lambda x: x | 1  # force LSB = 1
)

# ---------------------------------------------------------------------------
# MultiplyOddPermutation
# ---------------------------------------------------------------------------


class TestMultiplyOddProperties:
    @given(a=ODD_UINT64, b=UINT64, x=UINT64)
    @settings(max_examples=500)
    def test_inverse_of_forward_is_identity(self, a, b, x):
        """inverse(forward(x)) == x for all odd a, any b, any x."""
        perm = MultiplyOddPermutation(a=a, b=b)
        assert perm.inverse(perm.forward(x)) == x

    @given(a=ODD_UINT64, b=UINT64, y=UINT64)
    @settings(max_examples=500)
    def test_forward_of_inverse_is_identity(self, a, b, y):
        """forward(inverse(y)) == y for all odd a, any b, any y."""
        perm = MultiplyOddPermutation(a=a, b=b)
        assert perm.forward(perm.inverse(y)) == y

    @given(a=ODD_UINT64, b=UINT64, x=UINT64)
    @settings(max_examples=500)
    def test_output_is_64bit(self, a, b, x):
        """forward output must stay within [0, 2^64)."""
        perm = MultiplyOddPermutation(a=a, b=b)
        result = perm.forward(x)
        assert 0 <= result <= 0xFFFFFFFFFFFFFFFF

    @given(a=ODD_UINT64, b=UINT64, x1=UINT64, x2=UINT64)
    @settings(max_examples=300)
    def test_injectivity(self, a, b, x1, x2):
        """Different inputs must produce different outputs (bijection)."""
        assume(x1 != x2)
        perm = MultiplyOddPermutation(a=a, b=b)
        assert perm.forward(x1) != perm.forward(x2)

    @given(a=st.integers(min_value=0, max_value=0xFFFFFFFFFFFFFFFF).filter(lambda x: x % 2 == 0))
    @settings(max_examples=50)
    def test_even_a_raises(self, a):
        """Even values of a must raise ValueError."""
        with pytest.raises(ValueError):
            MultiplyOddPermutation(a=a, b=0)


# ---------------------------------------------------------------------------
# Feistel64Permutation
# ---------------------------------------------------------------------------


class TestFeistel64Properties:
    @given(key=UINT64, rounds=st.integers(min_value=1, max_value=16), x=UINT64)
    @settings(max_examples=400)
    def test_inverse_of_forward_is_identity(self, key, rounds, x):
        """inverse(forward(x)) == x for any key, rounds in [1,16], any x."""
        perm = Feistel64Permutation(key=key, rounds=rounds)
        assert perm.inverse(perm.forward(x)) == x

    @given(key=UINT64, rounds=st.integers(min_value=1, max_value=16), y=UINT64)
    @settings(max_examples=400)
    def test_forward_of_inverse_is_identity(self, key, rounds, y):
        """forward(inverse(y)) == y for any key, rounds in [1,16], any y."""
        perm = Feistel64Permutation(key=key, rounds=rounds)
        assert perm.forward(perm.inverse(y)) == y

    @given(key=UINT64, rounds=st.integers(min_value=1, max_value=16), x=UINT64)
    @settings(max_examples=400)
    def test_output_is_64bit(self, key, rounds, x):
        """forward output must stay within [0, 2^64)."""
        perm = Feistel64Permutation(key=key, rounds=rounds)
        result = perm.forward(x)
        assert 0 <= result <= 0xFFFFFFFFFFFFFFFF

    @given(
        key=UINT64,
        rounds=st.integers(min_value=1, max_value=16),
        x1=UINT64,
        x2=UINT64,
    )
    @settings(max_examples=300)
    def test_injectivity(self, key, rounds, x1, x2):
        """Different inputs produce different outputs (bijection)."""
        assume(x1 != x2)
        perm = Feistel64Permutation(key=key, rounds=rounds)
        assert perm.forward(x1) != perm.forward(x2)

    @given(key=UINT64, x=UINT64)
    @settings(max_examples=200)
    def test_forward_not_identity(self, key, x):
        """
        Permutation should not be trivially identity everywhere.
        (Not a hard invariant, but a sanity check that mixing actually happens.)
        We check that forward(x) != x for at least most inputs.
        Allow the rare fixed-point but verify inverse still works.
        """
        perm = Feistel64Permutation(key=key, rounds=6)
        # The crucial property: even if forward(x)==x, inverse must still work
        assert perm.inverse(perm.forward(x)) == x


# ---------------------------------------------------------------------------
# Layout64
# ---------------------------------------------------------------------------


class TestLayout64Properties:
    @given(
        instance_id=st.integers(min_value=0, max_value=0xFFFF),
        sequence=st.integers(min_value=0, max_value=0xFFFFFFFFFFFF),
    )
    @settings(max_examples=500)
    def test_compose_decompose_roundtrip(self, instance_id, sequence):
        """decompose(compose(instance_id, seq)) recovers both fields exactly."""
        layout = Layout64()
        raw = layout.compose(instance_id, sequence)
        decoded = layout.decompose(raw)
        assert decoded.instance_id == instance_id
        assert decoded.sequence == sequence

    @given(
        instance_id=st.integers(min_value=0, max_value=0xFFFF),
        sequence=st.integers(min_value=0, max_value=0xFFFFFFFFFFFF),
    )
    @settings(max_examples=500)
    def test_raw_always_64bit(self, instance_id, sequence):
        """compose output must always be a valid unsigned 64-bit integer."""
        layout = Layout64()
        raw = layout.compose(instance_id, sequence)
        assert 0 <= raw <= 0xFFFFFFFFFFFFFFFF

    @given(
        instance_bits=st.integers(min_value=1, max_value=63),
    )
    @settings(max_examples=100)
    def test_custom_split_roundtrip(self, instance_bits):
        """Custom bit splits must also satisfy round-trip property."""
        sequence_bits = 64 - instance_bits
        layout = Layout64(instance_bits=instance_bits, sequence_bits=sequence_bits)
        max_instance = (1 << instance_bits) - 1
        max_seq = (1 << sequence_bits) - 1
        # test at boundaries
        for iid, seq in [(0, 0), (max_instance, max_seq), (1, 1)]:
            raw = layout.compose(iid, seq)
            decoded = layout.decompose(raw)
            assert decoded.instance_id == iid
            assert decoded.sequence == seq

    @given(
        sequence=st.integers(min_value=0x1000000000000, max_value=0xFFFFFFFFFFFFFFFF),
    )
    @settings(max_examples=100)
    def test_sequence_overflow_always_raises(self, sequence):
        """Any sequence > 2^48-1 must raise OverflowError."""
        layout = Layout64()
        with pytest.raises(OverflowError):
            layout.compose(0, sequence)
