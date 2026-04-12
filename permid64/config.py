"""
config.py — Serializable generator configuration (experimental in v0.2).

``Id64Config`` + :func:`build_id64` round-trip to a plain ``dict`` for docs,
CLI prototypes, and config files.  They do **not** replace careful key
management in production.

.. note::
    ``build_id64`` currently hard-codes a dispatch table over the three
    built-in permutation kinds (``"multiplicative"``, ``"feistel"``,
    ``"identity"``).
    A future release will replace this with a **registry pattern** so that
    third-party permutation implementations can be registered and resolved by
    name without modifying this module.
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


@dataclass(frozen=True, repr=False)
class Id64Config:
    """
    Parameters describing how to build an :class:`Id64`.

    This is intentionally small; it mirrors the three factory constructors on
    ``Id64`` plus optional non-default layout and permutation constants.
    """

    kind: Kind
    instance_id: int
    state_file: str
    """Path to the counter state file.  May be relative or absolute.  Relative
    paths are resolved against the working directory at the time
    :func:`build_id64` is called, not at config construction time.  Use an
    absolute path for production deployments to avoid ambiguity."""
    block_size: int = 4096
    instance_bits: int = 16
    sequence_bits: int = 48
    a: Optional[int] = None
    b: Optional[int] = None
    key: Optional[int] = None
    rounds: int = 6

    def __repr__(self) -> str:
        """Log-safe representation — permutation secrets (a, b, key) are redacted."""
        return (
            f"Id64Config(kind={self.kind!r}, instance_id={self.instance_id}, "
            f"state_file={self.state_file!r}, block_size={self.block_size}, "
            f"instance_bits={self.instance_bits}, sequence_bits={self.sequence_bits}, "
            f"a={'<redacted>' if self.a is not None else None}, "
            f"b={'<redacted>' if self.b is not None else None}, "
            f"key={'<redacted>' if self.key is not None else None}, "
            f"rounds={self.rounds})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-friendly dict (``None`` values included)."""
        return cast(Dict[str, Any], asdict(self))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Id64Config":
        """
        Deserialize from :meth:`to_dict` output.

        Validates ``instance_id`` against the configured ``instance_bits``
        range so that misconfigured files surface a clear error here rather
        than producing silent bit-truncation at :meth:`Layout64.compose` time.
        """
        kind = data["kind"]
        if kind not in ("multiplicative", "feistel", "identity"):
            raise ValueError(f"unsupported kind: {kind!r}")
        instance_id = int(data["instance_id"])
        instance_bits = int(data.get("instance_bits", 16))
        max_instance_id = (1 << instance_bits) - 1
        if not (0 <= instance_id <= max_instance_id):
            raise ValueError(
                f"instance_id {instance_id} is out of range for "
                f"{instance_bits}-bit layout [0, {max_instance_id}]."
            )
        return cls(
            kind=cast(Kind, kind),
            instance_id=instance_id,
            state_file=str(data["state_file"]),
            block_size=int(data.get("block_size", 4096)),
            instance_bits=instance_bits,
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
        if a % 2 == 0:
            # build_id64 surfaces this as a config-layer error with a clearer
            # message than MultiplyOddPermutation.__init__ would produce.
            # MultiplyOddPermutation remains the authoritative mathematical
            # validator; this guard exists solely for DX.
            raise ValueError(
                f"Id64Config.a must be odd for multiplicative permutation, got {a:#x}. "
                "Choose an odd constant (e.g. the default 0x9E3779B185EBCA87)."
            )
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

    raise ValueError(f"unknown kind: {cfg.kind!r}")
