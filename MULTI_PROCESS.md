# Multi-Process Deployment Guide

## ProcessSafeCounterSource

`ProcessSafeCounterSource` is the recommended counter source for any deployment
that involves more than one OS process sharing the same state file — Gunicorn
prefork, uWSGI, `multiprocessing`, or any other fork-based model.

```python
from permid64.source import ProcessSafeCounterSource

src = ProcessSafeCounterSource("/var/lib/myapp/counter.state", block_size=256)
```

---

## How it works

| Mechanism | Purpose |
|-----------|---------|
| `fcntl.lockf` (OFD lock, POSIX) | Serialises block reservations across processes |
| `threading.Lock` | Serialises within a single process across threads |
| Sidecar `.lock` file | Holds the lock; separate from the state file to avoid contention with the atomic rename |
| PID check in `next()` | Detects fork and discards the inherited in-memory block before the first ID is served in the child |
| Temp-file + `rename` | Atomic state write — a crash mid-write never corrupts the state file |

---

## The sidecar `.lock` file

Every `ProcessSafeCounterSource` creates a sidecar file at
`<state_file>.lock` (e.g. `counter.state.lock`).  This file holds no useful
data — it is only used as a target for `fcntl.lockf`.

### Safe to delete

The `.lock` sidecar **may be deleted while the service is fully stopped**.
The next process to instantiate `ProcessSafeCounterSource` will recreate it
automatically.

### Must NOT be deleted while workers are running

**Do not delete the `.lock` file while any worker process is live.**

A worker that holds the lock keeps an open file description to the inode of
the `.lock` file.  If the file is deleted and recreated on disk, subsequent
workers open a *new* inode while the first worker still holds the lock on the
*old* (now unlinked) inode.  The two workers now hold locks on different
inodes — the mutual-exclusion guarantee is broken, and duplicate IDs can be
issued.

The failure mode is silent: no exception is raised, locks appear to be
acquired and released normally, but two processes can hold "the lock"
simultaneously.

**Correct procedure for maintenance rotation:**

1. Gracefully stop all workers.
2. Delete or archive the `.lock` sidecar (and optionally the `.state` file if
   resetting the counter).
3. Start workers.

---

## NFS / CIFS deployments

`ProcessSafeCounterSource` emits a `UserWarning` (once per process) if the
state file is detected to be on an NFS or CIFS mount:

```
UserWarning: State file '...' appears to be on a network filesystem (NFS or
CIFS). POSIX advisory locks (lockf) are unreliable on many NFS/CIFS server
configurations, which may allow duplicate IDs in multi-process deployments.
Consider moving the state file to a local filesystem. A ReservedBlockSource
with a central coordinator is planned for v0.5.
```

**Recommendation:** store the state file on a local filesystem (tmpfs, local
SSD, or a volume that is local to the host).  NFS lock support varies widely
by server configuration and kernel version; do not rely on it for correctness.

A `ReservedBlockSource` backed by a central coordinator service (Redis,
etcd, or a dedicated HTTP endpoint) is planned for **v0.5** and will be the
recommended path for multi-host deployments.

---

## Windows

`ProcessSafeCounterSource` falls back to `msvcrt.locking` on Windows.
Multi-process safety is **not guaranteed** on Windows.  Use distinct
`state_file` paths per process, or wait for the v0.5 coordinator-backed
source.
