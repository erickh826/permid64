"""
test_counter.py — Unit tests for PersistentCounterSource.

Covers:
  - Basic monotonic increment
  - Block reservation on first call
  - Persistence across simulated restarts
  - Gap tolerance after simulated crash
  - Thread safety
"""
import threading
from pathlib import Path

import pytest
from id64.source import PersistentCounterSource


@pytest.fixture
def state_file(tmp_path):
    return str(tmp_path / "id64.state")


class TestPersistentCounterSource:
    def test_first_call_starts_at_zero(self, state_file):
        src = PersistentCounterSource(state_file, block_size=16)
        assert src.next() == 0

    def test_sequential_increment(self, state_file):
        src = PersistentCounterSource(state_file, block_size=16)
        vals = [src.next() for _ in range(8)]
        assert vals == list(range(8))

    def test_block_reservation_written_to_disk(self, state_file):
        src = PersistentCounterSource(state_file, block_size=16)
        src.next()  # trigger first reservation
        assert Path(state_file).exists()
        highwater = int(Path(state_file).read_text().strip())
        assert highwater == 16  # one block reserved

    def test_new_block_reserved_when_exhausted(self, state_file):
        src = PersistentCounterSource(state_file, block_size=4)
        vals = [src.next() for _ in range(8)]  # two full blocks
        assert vals == list(range(8))
        highwater = int(Path(state_file).read_text().strip())
        assert highwater == 8

    def test_restart_does_not_repeat(self, state_file):
        src1 = PersistentCounterSource(state_file, block_size=16)
        last = max(src1.next() for _ in range(16))

        # Simulate restart: create new instance reading same state file
        src2 = PersistentCounterSource(state_file, block_size=16)
        first_after_restart = src2.next()
        assert first_after_restart > last, (
            f"Expected sequence to not repeat: got {first_after_restart}, last was {last}"
        )

    def test_gap_after_crash_no_duplicate(self, state_file):
        """
        Simulate crash: highwater is already written but in-memory block
        is partially consumed. A new instance must start at highwater, not
        at the last in-memory value.
        """
        src1 = PersistentCounterSource(state_file, block_size=64)
        issued = [src1.next() for _ in range(10)]  # consume first 10

        # 'Crash': delete in-memory state, reload from disk
        src2 = PersistentCounterSource(state_file, block_size=64)
        after_crash = [src2.next() for _ in range(5)]

        # No overlap
        assert set(issued).isdisjoint(after_crash), (
            f"Overlap detected: issued={issued}, after_crash={after_crash}"
        )
        # Strict monotonicity: after_crash > all issued
        assert min(after_crash) > max(issued)

    def test_thread_safety_no_duplicates(self, state_file):
        src = PersistentCounterSource(state_file, block_size=64)
        results: list[int] = []
        lock = threading.Lock()
        n_threads, n_per_thread = 8, 500

        def worker():
            local = [src.next() for _ in range(n_per_thread)]
            with lock:
                results.extend(local)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total = n_threads * n_per_thread
        assert len(results) == total
        assert len(set(results)) == total, "Duplicate sequence numbers detected"

    def test_invalid_block_size_raises(self, state_file):
        with pytest.raises(ValueError):
            PersistentCounterSource(state_file, block_size=0)
