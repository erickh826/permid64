# Changelog

## 0.3.0

### New: ProcessSafeCounterSource

Added `ProcessSafeCounterSource` — a multi-process–safe counter source for
Gunicorn prefork, uWSGI, and `multiprocessing` deployments.

- Uses `fcntl.lockf` (OFD semantics on Linux ≥ 3.15) via a sidecar `.lock`
  file, so locks are per-open-file-description and survive fork without
  deadlock.
- Thread-safe via `threading.Lock`.
- Atomic state writes via temp-file + rename (carried over from v0.2).
- Emits a `UserWarning` (once per process) when the state file is on NFS/CIFS
  (detected via `statfs(2)` `f_type`; no false positives on Docker overlay).
- `PersistentCounterSource` now emits a `UserWarning` on first use, directing
  users to `ProcessSafeCounterSource`.

### Implementation note: PID check must live in `next()`, not `_reserve_block()`

The fork-safety PID check is intentionally placed in `next()` rather than in
`_reserve_block()`.  This is a non-obvious correctness requirement:

If a child process inherits a live in-memory block (`_next < _limit`),
`_reserve_block()` is never reached — the child would silently serve IDs from
the same block as the parent, producing duplicates.  By invalidating the block
in `next()`, a fresh block reservation is forced on the child's very first call,
regardless of how full the inherited block was.

Moving this check into `_reserve_block()` re-introduces the fork-mid-block
duplicate-ID bug.  The comment in `source.py` documents this explicitly to
guard against future "simplification" refactors.

### No API breaking changes

`PersistentCounterSource` remains available.  `PermId64ConfigError` is added
to the public API (not yet raised; reserved for the v0.5 `ReservedBlockSource`
coordinator path).

## 0.2.0

- Added fixed-width **Base62** (11 characters, `0-9A-Za-z`) and **Crockford Base32** (13 uppercase characters) codecs in `permid64.codec`, with `u64_to_*` / `*_to_u64` helpers.
- Extended `Id64` with `next_base62`, `decode_base62`, `next_base32`, `decode_base32`, and factory `Id64.identity` (uses `IdentityPermutation`).
- Added experimental `Id64Config` and `build_id64` in `permid64.config` for JSON-friendly configuration round-trips.

## 0.1.0

- Initial release: persistent counter, `Layout64`, multiplicative and Feistel permutations, `Id64`, `decode`.
