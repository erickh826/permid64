"""
test_layout.py — Unit tests for Layout64.
"""
import pytest
from permid64.layout import Layout64


class TestLayout64:
    def setup_method(self):
        self.layout = Layout64()  # default: 16-bit instance, 48-bit sequence

    def test_compose_decompose_roundtrip(self):
        for instance_id, seq in [(0, 0), (1, 1), (42, 12345), (0xFFFF, 0xFFFFFFFFFFFF)]:
            raw = self.layout.compose(instance_id, seq)
            decoded = self.layout.decompose(raw)
            assert decoded.instance_id == instance_id
            assert decoded.sequence == seq
            assert decoded.raw == raw

    def test_compose_stays_within_64_bits(self):
        raw = self.layout.compose(0xFFFF, 0xFFFFFFFFFFFF)
        assert 0 <= raw <= 0xFFFFFFFFFFFFFFFF

    def test_instance_id_overflow_is_masked(self):
        # Values above 16-bit range should be masked, not raise
        raw = self.layout.compose(0x10001, 0)  # extra bit stripped
        decoded = self.layout.decompose(raw)
        assert decoded.instance_id == 1  # top bit masked off

    def test_sequence_overflow_raises(self):
        """Passing a sequence value beyond the bit width must now raise."""
        with pytest.raises(OverflowError):
            self.layout.compose(0, (1 << 48))  # one bit too many

    def test_custom_bit_split(self):
        layout = Layout64(instance_bits=8, sequence_bits=56)
        raw = layout.compose(255, 2**56 - 1)
        decoded = layout.decompose(raw)
        assert decoded.instance_id == 255
        assert decoded.sequence == 2**56 - 1

    def test_invalid_bit_split_raises(self):
        with pytest.raises(ValueError):
            Layout64(instance_bits=10, sequence_bits=10)

    def test_sequence_exhaustion_raises(self):
        """compose() must raise OverflowError when sequence exceeds bit width."""
        layout = Layout64()  # 48-bit sequence
        max_seq = layout.sequence_mask          # 2^48 - 1, still OK
        layout.compose(0, max_seq)              # should not raise
        with pytest.raises(OverflowError, match="exhausted"):
            layout.compose(0, max_seq + 1)      # one over the limit
