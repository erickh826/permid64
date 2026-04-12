"""
config.py — Serializable generator configuration (experimental in v0.2).

``Id64Config`` + :func:`build_id64` round-trip to a plain ``dict`` for docs,
CLI prototypes, and config files.  They do **not** replace careful key
management in production.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Literal, Optional, cast

from .generator import Id64
from .layout import Layout64
from .permutation import Feistel64Permutation, IdentityPermutation, MultiplyOddPermutation
from .source import PersistentCounterSource

Kind = Literal["multiplicative", "feistel", "identity"]

_DEFAULT_A = 0x9E3779B185EBCA87
_DEFAULT_B = 0x6A09E667F3BCC909
_DEFAULT_KEY = 0xDEADBEEFCAFEBABE


@dataclass
class Id64Config:
    """
    Parameters describing how to build an :class:`Id64`.

    This is intentionally small; it mirrors the three factory constructors on
    ``Id64`` plus optional non-default layout and permutation constants.
    """

    kind: Kind
    instance_id: int
    state_file: str
    block_size: int = 4096
    instance_bits: int = 16
    sequence_bits: int = 48
    a: Optional[int] = None
    b: Optional[int] = None
    key: Optional[int] = None
    rounds: int = 6

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict (``None`` values included)."""
        return cast(Dict[str, Any], asdict(self))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Id64Config":
        """Deserialize from :meth:`to_dict` output."""
        kind = data["kind"]
        if kind not in ("multiplicative", "feistel", "identity"):
            raise ValueError(f"unsupported kind: {kind!r}")
        return cls(
            kind=cast(Kind, kind),
            instance_id=int(data["instance_id"]),
            state_file=str(data["state_file"]),
            block_size=int(data.get("block_size", 4096)),
            instance_bits=int(data.get("instance_bits", 16)),
            sequence_bits=int(data.get("sequence_bits", 48)),
            a=(None if data.get("a") is None else int(data["a"])),
            b=(None if data.get("b") is None else int(data["b"])),
            key=(None if data.get("key") is None else int(data["key"])),
            rounds=int(data.get("rounds", 6)),
        )


def build_id64(cfg: Id64Config) -> Id64:
    """Construct :class:`Id64` from a configuration object."""
    if cfg.instance_bits + cfg.sequence_bits != 64:
        raise ValueError("instance_bits + sequence_bits must equal 64")
    layout: Optional[Layout64] = None
    if cfg.instance_bits != 16 or cfg.sequence_bits != 48:
        layout = Layout64(cfg.instance_bits, cfg.sequence_bits)

    source = PersistentCounterSource(cfg.state_file, cfg.block_size)

    if cfg.kind == "identity":
        return Id64(cfg.instance_id, source, IdentityPermutation(), layout)

    if cfg.kind == "multiplicative":
        a = _DEFAULT_A if cfg.a is None else cfg.a
        b = _DEFAULT_B if cfg.b is None else cfg.b
        return Id64(
            cfg.instance_id,
            source,
            MultiplyOddPermutation(a=a, b=b),
            layout,
        )

    if cfg.kind == "feistel":
        key = _DEFAULT_KEY if cfg.key is None else cfg.key
        return Id64(
            cfg.instance_id,
            source,
            Feistel64Permutation(key=key, rounds=cfg.rounds),
            layout,
        )

    raise AssertionError("unreachable")
