"""Tests for Id64Config and build_id64."""
from __future__ import annotations

import pytest

from permid64 import Id64, Id64Config, build_id64


def test_id64_config_dict_roundtrip():
    cfg = Id64Config(
        kind="multiplicative",
        instance_id=7,
        state_file="/tmp/x.state",
        block_size=2048,
        a=0x9E3779B185EBCA87,
        b=None,
    )
    cfg2 = Id64Config.from_dict(cfg.to_dict())
    assert cfg2 == cfg


def test_from_dict_rejects_bad_kind():
    with pytest.raises(ValueError, match="unsupported kind"):
        Id64Config.from_dict(
            {
                "kind": "nope",
                "instance_id": 1,
                "state_file": "x",
            }
        )


def test_build_id64_multiplicative_matches_factory(tmp_path):
    p1 = str(tmp_path / "a.state")
    p2 = str(tmp_path / "b.state")
    cfg = Id64Config(
        kind="multiplicative",
        instance_id=3,
        state_file=p1,
        a=0x9E3779B185EBCA87,
        b=0x6A09E667F3BCC909,
    )
    g = build_id64(cfg)
    h = Id64.multiplicative(instance_id=3, state_file=p2, block_size=4096)
    assert g.next_u64() == h.next_u64()


def test_build_id64_feistel_matches_factory(tmp_path):
    p1 = str(tmp_path / "c.state")
    p2 = str(tmp_path / "d.state")
    key = 0x123456789ABCDEF0
    cfg = Id64Config(
        kind="feistel",
        instance_id=2,
        state_file=p1,
        key=key,
        rounds=4,
    )
    g = build_id64(cfg)
    h = Id64.feistel(instance_id=2, state_file=p2, block_size=4096, key=key, rounds=4)
    assert g.next_u64() == h.next_u64()


def test_build_id64_custom_layout(tmp_path):
    cfg = Id64Config(
        kind="identity",
        instance_id=1,
        state_file=str(tmp_path / "e.state"),
        instance_bits=8,
        sequence_bits=56,
    )
    g = build_id64(cfg)
    uid = g.next_u64()
    meta = g.decode(uid)
    assert meta.instance_id == 1
    assert meta.sequence == 0


def test_from_dict_rejects_negative_instance_id():
    with pytest.raises(ValueError, match="out of range"):
        Id64Config.from_dict(
            {"kind": "multiplicative", "instance_id": -1, "state_file": "x"}
        )


def test_from_dict_rejects_oversized_instance_id():
    """instance_id >= 2^16 is out of range for default 16-bit layout."""
    with pytest.raises(ValueError, match="out of range"):
        Id64Config.from_dict(
            {"kind": "multiplicative", "instance_id": 65536, "state_file": "x"}
        )


def test_repr_redacts_secrets():
    cfg = Id64Config(
        kind="feistel",
        instance_id=1,
        state_file="x.state",
        key=0xDEADBEEFCAFEBABE,
    )
    r = repr(cfg)
    assert "DEADBEEF" not in r.upper()
    assert "<redacted>" in r
    assert "instance_id=1" in r
    assert "kind='feistel'" in r


def test_repr_shows_none_for_unset_secrets():
    cfg = Id64Config(kind="identity", instance_id=0, state_file="x")
    r = repr(cfg)
    assert "None" in r  # unset key/a/b shown as None, not <redacted>
