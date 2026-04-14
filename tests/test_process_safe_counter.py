"""
test_process_safe_counter.py — v0.3 tests for ProcessSafeCounterSource.

Test plan (7 cases):
  T1  Basic single-process uniqueness (1000 IDs)
  T2  multiprocessing.Pool — 4 workers × 250 IDs = 1000, 0 duplicates
  T3  Fork-safety — child process gets independent counter after os.fork()
  T4  Lock contention — 8 processes × 1000 IDs = 8000, 0 duplicates
  T5  Crash mid-reservation — state file survives, no duplicate IDs after restart
  T6  NFS detection mock — UserWarning emitted when fs_type matches NFS magic
  T7  PersistentCounterSource UserWarning — emit-once, UserWarning category
"""
from __future__ import annotations

import os
import sys
import warnings

import pytest

from permid64.source import (
    ProcessSafeCounterSource,
    PersistentCounterSource,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _worker_next(args: tuple) -> list:
    """Subprocess worker: create a fresh source and pull n IDs."""
    state_file, n, block_size = args
    src = ProcessSafeCounterSource(state_file, block_size=block_size)
    ids = [src.next() for _ in range(n)]
    src.close()
    return ids


# ---------------------------------------------------------------------------
# T1 — Basic single-process uniqueness
# ---------------------------------------------------------------------------

def test_t1_single_process_uniqueness(tmp_path):
    """1000 IDs from a single process must all be unique and monotone."""
    state = str(tmp_path / "counter.state")
    src = ProcessSafeCounterSource(state, block_size=64)
    ids = [src.next() for _ in range(1000)]
    src.close()

    assert len(ids) == len(set(ids)), "Duplicate IDs detected"
    assert ids == sorted(ids), "IDs are not monotonically increasing"


# ---------------------------------------------------------------------------
# T2 — multiprocessing.Pool, 4 workers × 250 IDs
# ---------------------------------------------------------------------------

def test_t2_multiprocessing_pool_no_duplicates(tmp_path):
    """4 processes × 250 IDs = 1000 total; must be globally unique."""
    import multiprocessing

    state = str(tmp_path / "counter.state")
    n_procs = 4
    ids_per_proc = 250

    with multiprocessing.Pool(processes=n_procs) as pool:
        results = pool.map(
            _worker_next,
            [(state, ids_per_proc, 32)] * n_procs,
        )

    all_ids = [i for batch in results for i in batch]
    assert len(all_ids) == n_procs * ids_per_proc
    assert len(all_ids) == len(set(all_ids)), (
        f"Duplicates found: {len(all_ids) - len(set(all_ids))} duplicates"
    )


# ---------------------------------------------------------------------------
# T3 — Fork safety (POSIX only)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="fork not available on Windows")
def test_t3_fork_safety_no_duplicates(tmp_path):
    """
    Parent opens ProcessSafeCounterSource, forks a child.
    Both parent and child pull IDs; there must be zero duplicates.
    """
    state = str(tmp_path / "fork.state")
    src = ProcessSafeCounterSource(state, block_size=16)

    # parent grabs a few IDs before fork
    parent_pre = [src.next() for _ in range(5)]

    # Use a pipe to collect child IDs
    r_fd, w_fd = os.pipe()
    pid = os.fork()

    if pid == 0:
        # --- child ---
        os.close(r_fd)
        child_ids = [src.next() for _ in range(10)]
        w = os.fdopen(w_fd, "w")
        w.write(",".join(map(str, child_ids)))
        w.close()
        src.close()
        os._exit(0)
    else:
        # --- parent ---
        os.close(w_fd)
        parent_post = [src.next() for _ in range(5)]
        os.waitpid(pid, 0)

        r = os.fdopen(r_fd)
        raw = r.read()
        r.close()
        child_ids = list(map(int, raw.split(",")))

    src.close()

    all_ids = parent_pre + parent_post + child_ids
    assert len(all_ids) == len(set(all_ids)), (
        f"Fork produced duplicates: {sorted(set(all_ids) - set(set(all_ids)))}"
    )


# ---------------------------------------------------------------------------
# T4 — High-contention: 8 processes × 1000 IDs
# ---------------------------------------------------------------------------

def test_t4_high_contention_no_duplicates(tmp_path):
    """8 processes × 1000 IDs = 8000; must be globally unique."""
    import multiprocessing

    state = str(tmp_path / "contention.state")
    n_procs = 8
    ids_per_proc = 1000

    with multiprocessing.Pool(processes=n_procs) as pool:
        results = pool.map(
            _worker_next,
            [(state, ids_per_proc, 64)] * n_procs,
        )

    all_ids = [i for batch in results for i in batch]
    total = n_procs * ids_per_proc
    assert len(all_ids) == total
    assert len(all_ids) == len(set(all_ids)), (
        f"Contention produced {len(all_ids) - len(set(all_ids))} duplicate(s)"
    )


# ---------------------------------------------------------------------------
# T5 — Crash mid-reservation: no duplicates after restart
# ---------------------------------------------------------------------------

def test_t5_crash_recovery_no_duplicates(tmp_path):
    """
    Simulate a crash by pre-writing a highwater mark, then instantiating a
    fresh source.  The new source must start above the pre-existing mark.
    """
    state = str(tmp_path / "crash.state")

    # Simulate a previous run that wrote highwater=500 (mid-block reservation)
    from pathlib import Path
    Path(state).write_text("500\n")

    src = ProcessSafeCounterSource(state, block_size=64)
    first_id = src.next()
    src.close()

    assert first_id >= 500, (
        f"After crash recovery, first ID {first_id} is below pre-existing highwater 500"
    )


# ---------------------------------------------------------------------------
# T6 — NFS detection mock
# ---------------------------------------------------------------------------

def test_t6_nfs_warning_emitted(tmp_path, monkeypatch):
    """
    When the filesystem reports NFS magic, a UserWarning must be emitted.
    The warning must mention 'NFS' and be of type UserWarning.
    """
    import permid64.source as src_mod

    # Reset the module-level guard so the warning fires in this test
    monkeypatch.setattr(src_mod, "_nfs_warned", False)

    # Patch _is_network_fs to always return True (simulate NFS mount)
    monkeypatch.setattr(src_mod, "_is_network_fs", lambda path: True)

    state = str(tmp_path / "nfs.state")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        src_mod._warn_network_fs(state)

    nfs_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
    assert len(nfs_warnings) == 1, f"Expected 1 UserWarning, got {len(nfs_warnings)}"
    msg = str(nfs_warnings[0].message)
    assert "NFS" in msg or "network filesystem" in msg.lower(), (
        f"Warning message does not mention NFS: {msg}"
    )
    assert "v0.5" in msg, "Warning should mention v0.5 roadmap item"


def test_t6b_nfs_warning_emitted_once(tmp_path, monkeypatch):
    """NFS warning is emitted at most once per process (module-level flag)."""
    import permid64.source as src_mod

    monkeypatch.setattr(src_mod, "_nfs_warned", False)
    monkeypatch.setattr(src_mod, "_is_network_fs", lambda path: True)

    state = str(tmp_path / "nfs2.state")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        src_mod._warn_network_fs(state)
        src_mod._warn_network_fs(state)
        src_mod._warn_network_fs(state)

    nfs_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
    assert len(nfs_warnings) == 1, (
        f"NFS warning emitted {len(nfs_warnings)} times; expected exactly 1"
    )


def test_t6c_no_nfs_warning_on_local_fs(tmp_path, monkeypatch):
    """No UserWarning when filesystem is local (not NFS/CIFS)."""
    import permid64.source as src_mod

    monkeypatch.setattr(src_mod, "_nfs_warned", False)
    # Default _is_network_fs returns False for local fs; no monkeypatching needed

    state = str(tmp_path / "local.state")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        src_mod._warn_network_fs(state)

    nfs_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
    assert len(nfs_warnings) == 0, (
        "Unexpected UserWarning on local filesystem"
    )


# ---------------------------------------------------------------------------
# T7 — PersistentCounterSource UserWarning (emit-once)
# ---------------------------------------------------------------------------

def test_t7_persistent_counter_warning_emit_once(tmp_path, monkeypatch):
    """
    PersistentCounterSource emits a UserWarning on first instantiation,
    then stays silent.  Category must be UserWarning (not DeprecationWarning).
    """
    import permid64.source as src_mod

    # Reset guard
    monkeypatch.setattr(src_mod, "_persistent_warned", False)

    state = str(tmp_path / "persist.state")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        PersistentCounterSource(state, block_size=16)
        PersistentCounterSource(state, block_size=16)  # second call: silent

    user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
    assert len(user_warnings) == 1, (
        f"Expected exactly 1 UserWarning, got {len(user_warnings)}"
    )
    msg = str(user_warnings[0].message)
    assert "ProcessSafeCounterSource" in msg, (
        "Warning should mention ProcessSafeCounterSource as the replacement"
    )
    assert "unsafe" in msg.lower(), (
        "Warning should say PersistentCounterSource is 'unsafe'"
    )


def test_t7b_persistent_warning_is_user_warning_not_deprecation(tmp_path, monkeypatch):
    """Category is UserWarning, not DeprecationWarning (more visible by default)."""
    import permid64.source as src_mod

    monkeypatch.setattr(src_mod, "_persistent_warned", False)

    state = str(tmp_path / "persist2.state")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        PersistentCounterSource(state, block_size=16)

    assert any(w.category is UserWarning for w in caught), (
        "Warning must be UserWarning, not DeprecationWarning"
    )
    assert not any(w.category is DeprecationWarning for w in caught), (
        "Warning must NOT be DeprecationWarning"
    )


# ---------------------------------------------------------------------------
# T_extra — context manager (close)
# ---------------------------------------------------------------------------

def test_context_manager_closes_fd(tmp_path):
    """ProcessSafeCounterSource closes the lock fd on __exit__."""
    state = str(tmp_path / "cm.state")
    with ProcessSafeCounterSource(state, block_size=16) as src:
        _ = src.next()
    assert src._lock_fd is None, "lock_fd should be None after close()"


def test_lock_path_property(tmp_path):
    """lock_path points to the sidecar .lock file."""
    state = str(tmp_path / "lp.state")
    src = ProcessSafeCounterSource(state)
    assert str(src.lock_path) == state + ".lock"
    src.close()
