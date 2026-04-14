"""
source.py — Counter sources for permid64.

PersistentCounterSource
  - Single-process only (best-effort flock, not fork-safe).
  - Kept for backward compatibility; emits a UserWarning on first use.
  - For multi-process deployments, use ProcessSafeCounterSource.

ProcessSafeCounterSource
  - Multi-process safe on POSIX (Gunicorn prefork, uWSGI, multiprocessing).
  - Uses a sidecar .lock file with fcntl.lockf (OFD semantics) so that
    locks are per-open-file-description, not per-process — survives fork.
  - Fork safety: lazy reopen on first _reserve_block() call in the child
    process (PID check), avoiding deadlock from inheriting a held mutex.
  - Windows: best-effort via msvcrt.locking; no multi-process guarantee.
  - Thread-safe via threading.Lock.
  - Atomic state write via temp-file + rename (already in v0.2).
  - NFS/CIFS detection at startup: emits UserWarning (does not raise).
"""
from __future__ import annotations

import os
import sys
import threading
import warnings
from pathlib import Path

# ---------------------------------------------------------------------------
# Platform capability flags
# ---------------------------------------------------------------------------
try:
    import fcntl as _fcntl
    _HAS_LOCKF = True
except ImportError:
    _HAS_LOCKF = False  # Windows

try:
    import msvcrt as _msvcrt
    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False  # POSIX

# ---------------------------------------------------------------------------
# NFS detection (POSIX only)
# ---------------------------------------------------------------------------
_NFS_SUPER_MAGIC = 0x6969
_CIFS_SUPER_MAGIC = 0xFF534D42

if sys.platform != "win32":
    try:
        import ctypes
        import ctypes.util

        _libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

        class _StatfsResult(ctypes.Structure):
            _fields_ = [
                ("f_type",    ctypes.c_long),
                ("f_bsize",   ctypes.c_long),
                ("f_blocks",  ctypes.c_ulong),
                ("f_bfree",   ctypes.c_ulong),
                ("f_bavail",  ctypes.c_ulong),
                ("f_files",   ctypes.c_ulong),
                ("f_ffree",   ctypes.c_ulong),
                ("f_fsid",    ctypes.c_long * 2),
                ("f_namelen", ctypes.c_long),
                ("f_frsize",  ctypes.c_long),
                ("f_flags",   ctypes.c_long),
                ("f_spare",   ctypes.c_long * 4),
            ]

        def _get_fs_type(path: str) -> int | None:
            buf = _StatfsResult()
            ret = _libc.statfs(path.encode(), ctypes.byref(buf))
            if ret != 0:
                return None
            return buf.f_type & 0xFFFFFFFF

        _HAS_STATFS = True
    except Exception:
        _HAS_STATFS = False
else:
    _HAS_STATFS = False


def _is_network_fs(path: str) -> bool:
    """Return True if *path* is on a network filesystem (NFS or CIFS)."""
    if not _HAS_STATFS:
        return False
    try:
        ftype = _get_fs_type(path)
        if ftype is None:
            return False
        return ftype in (_NFS_SUPER_MAGIC, _CIFS_SUPER_MAGIC)
    except Exception:
        return False


def _warn_network_fs(path: str) -> None:
    """
    Emit a one-time UserWarning if *path* is on NFS/CIFS.

    POSIX advisory locks (lockf/flock) over NFS/CIFS are unreliable on many
    server configurations.  This warning is emitted once per process (module-
    level flag) so it does not spam logs.
    """
    global _nfs_warned  # noqa: PLW0603
    if _nfs_warned:
        return
    if _is_network_fs(path):
        _nfs_warned = True
        warnings.warn(
            f"State file '{path}' appears to be on a network filesystem "
            "(NFS or CIFS). POSIX advisory locks (lockf) are unreliable on "
            "many NFS/CIFS server configurations, which may allow duplicate "
            "IDs in multi-process deployments. "
            "Consider moving the state file to a local filesystem. "
            "A ReservedBlockSource with a central coordinator is planned "
            "for v0.5.",
            UserWarning,
            stacklevel=4,  # surface at user call site (ProcessSafeCounterSource.__init__)
        )


_nfs_warned: bool = False

# ---------------------------------------------------------------------------
# Emit-once warning for PersistentCounterSource
# ---------------------------------------------------------------------------
_persistent_warned: bool = False


# ---------------------------------------------------------------------------
# PersistentCounterSource (v0.2 compat, now with deprecation-style warning)
# ---------------------------------------------------------------------------

class PersistentCounterSource:
    """
    A monotonically increasing counter backed by a file.

    .. deprecated::
        ``PersistentCounterSource`` is **unsafe** for multi-process
        deployments (Gunicorn prefork, uWSGI, ``multiprocessing``).
        Use :class:`ProcessSafeCounterSource` instead.

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
        global _persistent_warned  # noqa: PLW0603
        if not _persistent_warned:
            warnings.warn(
                "PersistentCounterSource is unsafe for multi-process "
                "deployments (Gunicorn prefork, uWSGI, multiprocessing). "
                "Use ProcessSafeCounterSource instead. "
                "See https://github.com/erickh826/permid64#migration for details.",
                UserWarning,
                stacklevel=2,
            )
            _persistent_warned = True

        if block_size < 1:
            raise ValueError("block_size must be >= 1")
        self.path = Path(state_file)
        self.block_size = block_size
        self._lock = threading.Lock()
        self._next: int = 0
        self._limit: int = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_highwater(self) -> int:
        if not self.path.exists():
            return 0
        text = self.path.read_text().strip()
        return int(text) if text else 0

    def _write_highwater(self, value: int) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(str(value))
        tmp.replace(self.path)

    def _reserve_block(self) -> None:
        lock_fd = None
        try:
            if _HAS_LOCKF:
                lock_fd = open(self.path, "a")  # noqa: WPS515
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


# ---------------------------------------------------------------------------
# ProcessSafeCounterSource (v0.3 new)
# ---------------------------------------------------------------------------

class ProcessSafeCounterSource:
    """
    A multi-process–safe, monotonically increasing counter backed by a file.

    Guarantees (POSIX)
    ------------------
    - No duplicate sequence numbers across any number of processes sharing
      the same ``state_file``, including Gunicorn prefork and uWSGI.
    - Fork-safe: a child process that inherits an open instance will lazily
      reopen the lock file on its first ``next()`` call (PID check), instead
      of inheriting a potentially deadlocked mutex.
    - Thread-safe within each process via ``threading.Lock``.
    - No duplicate IDs after a crash (gaps are allowed).

    Windows
    -------
    Best-effort only (``msvcrt.locking``).  Multi-process safety is not
    guaranteed.  Use distinct ``state_file`` paths per process until v0.5.

    NFS / CIFS
    ----------
    A ``UserWarning`` is emitted once per process if the state file is
    detected to be on a network filesystem.  IDs may still be unique in
    practice, but the lock reliability is server-dependent.

    Parameters
    ----------
    state_file:
        Path to the persistent state file.  A sidecar ``<state_file>.lock``
        file is created automatically.
    block_size:
        Number of sequence numbers reserved per disk round-trip (default 256).
        Higher values reduce I/O but increase the gap after a crash.
    """

    def __init__(self, state_file: str, block_size: int = 256) -> None:
        if block_size < 1:
            raise ValueError("block_size must be >= 1")

        self.path = Path(state_file)
        self.lock_path = Path(str(state_file) + ".lock")
        self.block_size = block_size

        self._thread_lock = threading.Lock()
        self._next: int = 0
        self._limit: int = 0

        # PID tracking for fork safety
        self._pid: int = os.getpid()
        self._lock_fd: "int | None" = None  # raw file descriptor

        # Ensure directories exist
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # NFS warning (once per process)
        _warn_network_fs(str(self.path.parent))

        # Open the lock file eagerly in the parent process
        self._open_lock_fd()

    # ------------------------------------------------------------------
    # Lock file management
    # ------------------------------------------------------------------

    def _open_lock_fd(self) -> None:
        """Open (or reopen) the sidecar lock file and record our PID."""
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
        fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o600)
        self._lock_fd = fd
        self._pid = os.getpid()

    def _acquire_lock(self) -> None:
        """Acquire the exclusive file lock (POSIX: lockf; Windows: msvcrt)."""
        if _HAS_LOCKF:
            # lockf = OFD (open-file-description) lock on Linux ≥ 3.15,
            # POSIX record lock on older kernels — both survive fork correctly
            # because each open() creates a new file description.
            _fcntl.lockf(self._lock_fd, _fcntl.LOCK_EX)  # type: ignore[arg-type]
        elif _HAS_MSVCRT:
            _msvcrt.locking(self._lock_fd, _msvcrt.LK_LOCK, 1)

    def _release_lock(self) -> None:
        """Release the exclusive file lock."""
        if _HAS_LOCKF:
            _fcntl.lockf(self._lock_fd, _fcntl.LOCK_UN)  # type: ignore[arg-type]
        elif _HAS_MSVCRT:
            _msvcrt.locking(self._lock_fd, _msvcrt.LK_UNLCK, 1)

    # ------------------------------------------------------------------
    # State file I/O
    # ------------------------------------------------------------------

    def _read_highwater(self) -> int:
        """Return the persisted high-water mark (0 if file absent/empty)."""
        if not self.path.exists():
            return 0
        text = self.path.read_text().strip()
        return int(text) if text else 0

    def _write_highwater(self, value: int) -> None:
        """Atomically write the new high-water mark via temp-file + rename."""
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(str(value))
        tmp.replace(self.path)  # atomic on POSIX; best-effort on Windows

    # ------------------------------------------------------------------
    # Block reservation
    # ------------------------------------------------------------------

    def _reserve_block(self) -> None:
        """
        Reserve the next block of sequence numbers.

        Must be called under ``self._thread_lock``.

        Fork-safety: if we detect we are in a child process (PID mismatch),
        we reopen the lock file before acquiring the lock.  This is safe
        because:
          - The child calls _reserve_block() for the first time only after
            fork() completes.
          - The inherited _thread_lock is not held at this point (the child
            gets a fresh copy of the mutex in an unlocked state).
          - Reopening creates a brand-new file description, so the child's
            lock is fully independent of the parent's.
        """
        # --- Fork-safety: lazy reopen in child process ---
        if self._lock_fd is not None and self._pid != os.getpid():
            self._open_lock_fd()

        self._acquire_lock()
        try:
            highwater = self._read_highwater()
            new_highwater = highwater + self.block_size
            self._write_highwater(new_highwater)
            self._next = highwater
            self._limit = new_highwater
        finally:
            self._release_lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def next(self) -> int:
        """Return the next unique sequence number (thread- and process-safe)."""
        with self._thread_lock:
            # Fork-safety: if we are in a child process, the inherited in-memory
            # block is shared with the parent, so we must discard it and reserve
            # a fresh block from disk.  We detect this by comparing our recorded
            # PID to the current PID.
            if self._pid != os.getpid():
                self._next = self._limit  # invalidate inherited block
            if self._next >= self._limit:
                self._reserve_block()
            val = self._next
            self._next += 1
            return val

    @property
    def current_highwater(self) -> int:
        """Return the persisted high-water mark (for inspection / testing)."""
        return self._read_highwater()

    def close(self) -> None:
        """Release the lock file descriptor.  Safe to call multiple times."""
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None

    def __enter__(self) -> "ProcessSafeCounterSource":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
