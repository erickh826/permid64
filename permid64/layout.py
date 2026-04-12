"""
layout.py — Pack / unpack instance_id + sequence into a single 64-bit integer.

Default split: 16 bits for instance_id  (up to 65 535 shards)
               48 bits for sequence      (up to 281 trillion IDs per shard)
"""
from .types import DecodedId

MASK64 = 0xFFFFFFFFFFFFFFFF


class Layout64:
    """
    Bit-layout for the 64-bit raw value.

    instance_id occupies the top `instance_bits` bits.
    sequence    occupies the bottom `sequence_bits` bits.
    """

    def __init__(self, instance_bits: int = 16, sequence_bits: int = 48) -> None:
        if instance_bits + sequence_bits != 64:
            raise ValueError(
                f"instance_bits ({instance_bits}) + sequence_bits ({sequence_bits}) must equal 64"
            )
        self.instance_bits = instance_bits
        self.sequence_bits = sequence_bits
        self.sequence_mask = (1 << sequence_bits) - 1
        self.instance_mask = (1 << instance_bits) - 1

    def compose(self, instance_id: int, sequence: int) -> int:
        """
        Pack instance_id and sequence into a single 64-bit integer.

        Both values are silently masked to their configured bit widths.
        Values exceeding the field width (e.g. instance_id >= 2^instance_bits)
        will have their high bits truncated without raising an error.
        Use ``instance_mask`` / ``sequence_mask`` to validate inputs if
        strict overflow detection is required.
        """
        if sequence > self.sequence_mask:
            raise OverflowError(
                f"sequence {sequence} exceeds {self.sequence_bits}-bit maximum "
                f"({self.sequence_mask}). The ID space for this shard is exhausted."
            )
        return (
            ((instance_id & self.instance_mask) << self.sequence_bits)
            | (sequence & self.sequence_mask)
        ) & MASK64

    def decompose(self, raw: int) -> DecodedId:
        """Unpack a raw 64-bit integer back into instance_id and sequence."""
        seq = raw & self.sequence_mask
        instance_id = (raw >> self.sequence_bits) & self.instance_mask
        return DecodedId(raw=raw, instance_id=instance_id, sequence=seq)
