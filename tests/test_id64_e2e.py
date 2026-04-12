"""
test_id64_e2e.py — End-to-end tests for the Id64 public API.

Covers the five MVP acceptance criteria:
  1. Uniqueness         — 1 million IDs with no duplicates
  2. Invertibility      — decode(next_u64()) round-trips correctly
  3. Restart safety     — sequence does not reset after restart
  4. Gap tolerance      — sequence skips but never repeats after a crash
  5. Thread safety      — multi-thread uniqueness
"""
import threading

import pytest
from permid64 import Id64


@pytest.fixture
def state_file(tmp_path):
    return str(tmp_path / "id64.state")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_multiplicative(state_file, instance_id=1):
    return Id64.multiplicative(
        instance_id=instance_id,
        state_file=state_file,
        block_size=4096,
    )


def make_feistel(state_file, instance_id=1):
    return Id64.feistel(
        instance_id=instance_id,
        state_file=state_file,
        block_size=4096,
    )


# ---------------------------------------------------------------------------
# 1. Uniqueness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("factory", [make_multiplicative, make_feistel])
def test_uniqueness_1m(state_file, factory):
    gen = factory(state_file)
    ids = [gen.next_u64() for _ in range(1_000_000)]
    assert len(set(ids)) == len(ids), "Duplicate IDs detected"


# ---------------------------------------------------------------------------
# 2. Invertibility
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("factory", [make_multiplicative, make_feistel])
def test_invertibility(state_file, factory):
    gen = factory(state_file)
    for _ in range(1000):
        uid = gen.next_u64()
        meta = gen.decode(uid)
        assert meta.instance_id == 1
        # Re-encode and check we get back the same id
        from permid64.layout import Layout64
        layout = Layout64()
        reencoded = gen.permutation.forward(layout.compose(meta.instance_id, meta.sequence))
        assert reencoded == uid


# ---------------------------------------------------------------------------
# 3. Restart safety
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("factory", [make_multiplicative, make_feistel])
def test_restart_safety(state_file, factory):
    gen1 = factory(state_file)
    ids_before = {gen1.next_u64() for _ in range(100)}

    # Simulate restart by creating a new generator from the same state file
    gen2 = factory(state_file)
    ids_after = {gen2.next_u64() for _ in range(100)}

    overlap = ids_before & ids_after
    assert not overlap, f"IDs repeated after restart: {overlap}"


# ---------------------------------------------------------------------------
# 4. Gap tolerance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("factory", [make_multiplicative, make_feistel])
def test_gap_tolerance(state_file, factory):
    gen1 = factory(state_file)
    ids_before = {gen1.next_u64() for _ in range(10)}

    # 'Crash': abandon gen1, create fresh generator (simulates restart mid-block)
    gen2 = factory(state_file)
    ids_after = {gen2.next_u64() for _ in range(10)}

    # There may be a gap but there must be no overlap
    assert ids_before.isdisjoint(ids_after), "Duplicate IDs after simulated crash"


# ---------------------------------------------------------------------------
# 5. Thread safety
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("factory", [make_multiplicative, make_feistel])
def test_thread_safety(state_file, factory):
    gen = factory(state_file)
    results: list[int] = []
    lock = threading.Lock()
    n_threads, n_per_thread = 8, 500

    def worker():
        local = [gen.next_u64() for _ in range(n_per_thread)]
        with lock:
            results.extend(local)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total = n_threads * n_per_thread
    assert len(results) == total
    assert len(set(results)) == total, "Duplicate IDs under concurrent access"


# ---------------------------------------------------------------------------
# decode() output fields
# ---------------------------------------------------------------------------

def test_decode_returns_correct_instance_id(state_file):
    gen = make_multiplicative(state_file, instance_id=42)
    uid = gen.next_u64()
    meta = gen.decode(uid)
    assert meta.instance_id == 42


def test_decode_sequence_is_monotonic(state_file):
    gen = make_multiplicative(state_file, instance_id=1)
    metas = [gen.decode(gen.next_u64()) for _ in range(100)]
    seqs = [m.sequence for m in metas]
    assert seqs == sorted(seqs), "Sequences are not monotonically increasing"
