"""
test_layout.py — Unit tests for Layout64.
"""
import pytest
from id64.layout import Layout64


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

    def test_sequence_overflow_is_masked(self):
        raw = self.layout.compose(0, (1 << 48))  # one bit too many
        decoded = self.layout.decompose(raw)
        assert decoded.sequence == 0  # overflow bit stripped

    def test_custom_bit_split(self):
        layout = Layout64(instance_bits=8, sequence_bits=56)
        raw = layout.compose(255, 2**56 - 1)
        decoded = layout.decompose(raw)
        assert decoded.instance_id == 255
        assert decoded.sequence == 2**56 - 1

    def test_invalid_bit_split_raises(self):
        with pytest.raises(ValueError):
            Layout64(instance_bits=10, sequence_bits=10)
