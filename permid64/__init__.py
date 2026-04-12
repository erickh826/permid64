"""
permid64 — Clock-free, persistent, obfuscated 64-bit ID generation.

Public API
----------
    from permid64 import Id64, DecodedId

    gen = Id64.multiplicative(instance_id=1, state_file="id64.state")
    uid = gen.next_u64()
    meta = gen.decode(uid)   # DecodedId(raw=..., instance_id=1, sequence=0)
"""
from .generator import Id64
from .types import DecodedId

__all__ = ["Id64", "DecodedId"]
__version__ = "0.1.0"
