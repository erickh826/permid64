"""
permid64 — Clock-free, persistent, obfuscated 64-bit ID generation.

Public API
----------
    from permid64 import Id64, DecodedId

    gen = Id64.multiplicative(instance_id=1, state_file="id64.state")
    uid = gen.next_u64()
    meta = gen.decode(uid)   # DecodedId(raw=..., instance_id=1, sequence=0)

    tok = gen.next_base62()
    meta = gen.decode_base62(tok)
"""
from .codec import base62_to_u64, crockford32_to_u64, u64_to_base62, u64_to_crockford32
from .config import Id64Config, build_id64
from .generator import Id64
from .permutation import IdentityPermutation, Permutation64Protocol
from .types import DecodedId

__all__ = [
    "Id64",
    "Id64Config",
    "build_id64",
    "DecodedId",
    "Permutation64Protocol",
    "IdentityPermutation",
    "u64_to_base62",
    "base62_to_u64",
    "u64_to_crockford32",
    "crockford32_to_u64",
]
__version__ = "0.2.0"
