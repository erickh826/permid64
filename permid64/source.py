"""
source.py — Counter sources for id64.

PersistentCounterSource
  - Reads / writes a plain-text state file to survive restarts.
  - Uses block reservation to minimise fsync overhead.
  - Guarantees: no duplicates across restarts; gaps are allowed after a crash.
  - Thread-safe via a threading.Lock.
"""
from __future__ import annotations

import threading
from pathlib import Path

try:
    import fcntl as _fcntl
    _HAS_FLOCK = True
except ImportError:
    _HAS_FLOCK = False  # Windows: flock not available


class PersistentCounterSource:
    """
    A monotonically increasing counter backed by a file.

    On startup it reads ``state_file`` to find the last reserved high-water
    mark, then immediately reserves the next block of ``block_size`` values
    and writes the new high-water mark back to disk.  Subsequent calls to
    ``next()`` are served from memory until the block is exhausted, at which
    point a new block is reserved.

    If the process crashes mid-block the unused sequence numbers in that
    block are lost (gaps), but sequence numbers already issued are never
    reused.
    """

    def __init__(self, state_file: str, block_size: int = 4096) -> None:
        if block_size < 1:
            raise ValueError("block_size must be >= 1")
        self.path = Path(state_file)
        self.block_size = block_size
        self._lock = threading.Lock()
        self._next: int = 0
        self._limit: int = 0  # _next < _limit while block is live
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_highwater(self) -> int:
        """Return the persisted high-water mark (0 if file absent/empty)."""
        if not self.path.exists():
            return 0
        text = self.path.read_text().strip()
        return int(text) if text else 0

    def _write_highwater(self, value: int) -> None:
        """Atomically write the new high-water mark."""
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(str(value))
        tmp.replace(self.path)  # atomic rename on POSIX

    def _reserve_block(self) -> None:
        """
        Reserve the next block; must be called under self._lock.

        Uses ``fcntl.flock`` (POSIX only) as a best-effort advisory lock
        during the read-modify-write cycle.  This reduces — but does not
        fully eliminate — the risk of two processes accidentally sharing the
        same state file.  For guaranteed multi-process safety, assign each
        process a distinct state file and instance_id.
        """
        lock_fd = None
        try:
            if _HAS_FLOCK:
                lock_fd = open(self.path, "a")  # open/create for locking
                _fcntl.flock(lock_fd, _fcntl.LOCK_EX)
            highwater = self._read_highwater()
            new_highwater = highwater + self.block_size
            self._write_highwater(new_highwater)
            self._next = highwater
            self._limit = new_highwater
        finally:
            if lock_fd is not None:
                _fcntl.flock(lock_fd, _fcntl.LOCK_UN)
                lock_fd.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def next(self) -> int:
        """Return the next unique sequence number."""
        with self._lock:
            if self._next >= self._limit:
                self._reserve_block()
            val = self._next
            self._next += 1
            return val

    @property
    def current_highwater(self) -> int:
        """Return the persisted high-water mark (for inspection / testing)."""
        return self._read_highwater()
