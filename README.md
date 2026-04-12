# permid64

[![CI](https://github.com/erickh826/permid64/actions/workflows/test.yml/badge.svg)](https://github.com/erickh826/permid64/actions/workflows/test.yml)
[![PyPI version](https://img.shields.io/pypi/v/permid64)](https://pypi.org/project/permid64/)
[![Python versions](https://img.shields.io/pypi/pyversions/permid64)](https://pypi.org/project/permid64/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](https://pypi.org/project/permid64/)

**Clock-free, persistent, reversible-permutation 64-bit ID generation.**

> *Counter in, permutation out.*

permid64 generates unique 64-bit integer IDs without relying on wall-clock time. It combines a crash-safe persistent counter with an invertible permutation to produce IDs that look random but carry recoverable metadata.

```
# Raw counter (leaks business volume at a glance)
1001, 1002, 1003 ...

# permid64 (shuffled surface, recoverable structure)
12609531668580943872, 7349201938475629, 3847291038012847 ...
# decode(12609531668580943872)  →  instance_id=42, sequence=0
```

---

## Why permid64?

| Problem | permid64's answer |
|---|---|
| Clock skew / NTP jumps break time-based IDs | Counter, not clock |
| Monotonic counters leak business volume | Permutation hides raw counter |
| IDs must survive process restarts | State file with block reservation |
| IDs must be decodable (audit, debug) | `decode()` reverses the permutation |
| No infrastructure dependency | Pure Python, **zero runtime deps** |

---

## permid64 vs Snowflake vs UUID

| | permid64 | Snowflake ID | UUID v4 |
|---|---|---|---|
| **Bit width** | 64 | 64 | 128 |
| **Core dependency** | Persistent counter (file) | System clock (NTP) | Random source |
| **Clock rollback risk** | None | High | None |
| **External appearance** | Shuffled (random-looking) | Roughly increasing | Random |
| **DB index friendliness** | Moderate (random writes) | Excellent (sequential) | Poor (random writes) |
| **Decodable** | Yes (`instance_id` + `sequence`) | Yes (`timestamp` + `worker_id`) | No |
| **Infrastructure needed** | Local durable storage | Worker ID coordination (ZK/etcd) | None |
| **Best for** | External-facing IDs, anti-scraping | Internal logs, time-ordered streams | Globally unique tokens |

---

## What it is

- A **clock-free** 64-bit ID generator — no timestamp, no NTP dependency
- IDs are **unique** because the source is a monotonically increasing counter
- IDs **look shuffled** because they pass through a reversible permutation
- The permutation is **invertible** — `decode()` recovers the original metadata

## What it is not

- **Not a timestamp-based scheme** — there is no time component in the ID
- **Not a UUID replacement for every scenario** — if you need a globally unique random token with no infrastructure at all, UUID v4 is simpler
- **Not cryptographic encryption** — the permutation is an obfuscation layer, not authenticated encryption; do not use IDs as secrets or security tokens
- **Not safe for multiple processes sharing one state file** — `PersistentCounterSource` is single-process only; concurrent writes from multiple processes to the same state file will cause duplicates (see [Limitations](#limitations))

---

## Installation

```bash
pip install permid64
```

For development (tests, linting, type checking):

```bash
pip install -e ".[dev]"
```

---

## Quick start

```python
from permid64 import Id64

# Multiplicative (fastest)
gen = Id64.multiplicative(
    instance_id=42,
    state_file="permid64.state",
    block_size=4096,
)

uid = gen.next_u64()          # e.g. 12609531668580943872
meta = gen.decode(uid)
# DecodedId(raw=2748779069440, instance_id=42, sequence=0)
print(meta.instance_id, meta.sequence)

# Feistel (better statistical mixing)
gen2 = Id64.feistel(
    instance_id=42,
    state_file="permid64.state",
    block_size=4096,
    key=0xDEADBEEFCAFEBABE,
    rounds=6,
)
```

### String tokens (Base62 and Crockford Base32)

For order numbers, invite codes, and shareable URLs, fixed-width alphanumeric tokens are easier to read than a 19-digit decimal. They encode the **same** `next_u64()` value — no second ID space.

```python
# 11 chars: 0-9, A-Z, a-z (case-sensitive in URLs and logs)
token = gen.next_base62()
meta = gen.decode_base62(token)

# 13 chars: Crockford Base32 (uppercase only; excludes I, L, O, U)
tok32 = gen.next_base32()
meta = gen.decode_base32(tok32)
```

Stateless integer codecs (for storage or custom pipelines):

```python
from permid64 import u64_to_base62, base62_to_u64

s = u64_to_base62(12345678901234567890)
n = base62_to_u64(s)
```

Strings are **not** secrets: anyone who knows the alphabet and (for `decode`) the same permutation parameters can map tokens back to integers and metadata.

### Why decode() matters

In production, when an anomalous ID appears in a log or alert, you can decode it instantly — no DB lookup needed:

```python
meta = gen.decode(12609531668580943872)
print(f"Issued by instance {meta.instance_id}, sequence #{meta.sequence}")
# Issued by instance 42, sequence #0
```

This makes incident tracing dramatically faster: you immediately know which shard issued the ID and its approximate position in the issuance history.

### Assigning instance_id

Assign each process or deployment unit a distinct `instance_id`. Common patterns:

```python
import os

# From environment variable (works in Docker / K8s)
instance_id = int(os.environ.get("INSTANCE_ID", "0"))

# From K8s StatefulSet pod name (e.g. "worker-3" -> 3)
import re
pod_name = os.environ.get("POD_NAME", "worker-0")
instance_id = int(re.search(r"(\d+)$", pod_name).group(1))
```

Each `instance_id` gets its own independent sequence space — no coordination needed between shards.

---

## Design

```
seq  = source.next()                    # monotonic counter (persistent)
raw  = layout.compose(instance_id, seq) # pack 16-bit shard + 48-bit seq
id64 = permutation.forward(raw)         # obfuscate with invertible bijection
```

**Layout** — default 64-bit split:

```
[ instance_id : 16 bits ][ sequence : 48 bits ]
```

- Up to **65 535** independent shards
- Up to **281 trillion** IDs per shard

**Permutations** — both are bijections over `[0, 2^64)`:

| Mode | Formula | Speed | Mixing |
|---|---|---|---|
| `multiplicative` | `f(x) = (a·x + b) mod 2^64` | ~500 M/s | Good |
| `feistel` | 64-bit Feistel network | ~150 M/s | Excellent |

**Persistence** — block reservation strategy:
1. On startup, read high-water mark from state file.
2. Reserve a block of N sequence numbers, write new high-water mark.
3. Serve IDs from memory until block exhausted.
4. If the process crashes, the unused block is lost (gap), but **no duplicate is ever issued**.

---

## Running tests

```bash
pytest
```

Five acceptance criteria are checked:

1. **Uniqueness** — 1 million IDs, zero duplicates
2. **Invertibility** — `decode(next_u64())` recovers `instance_id` and `sequence`
3. **Restart safety** — sequence never resets across process restarts
4. **Gap tolerance** — crash causes a gap, never a duplicate
5. **Thread safety** — concurrent generation remains unique

---

## Benchmark

```bash
python benchmarks/bench_id64.py
```

Sample output (Apple M2):

```
[Permutation comparison — block_size=4096]
  multiplicative (default keys)          ~480,000,000 IDs/sec
  feistel (6 rounds)                     ~140,000,000 IDs/sec
  feistel (12 rounds)                     ~80,000,000 IDs/sec
```

---

## Guarantees

| Guarantee | Notes |
|---|---|
| No duplicate IDs within a shard | Strict |
| No duplicates across restarts | Strict — state file must be on durable storage |
| Decodable | Only with the same permutation key / params |
| Gaps allowed | After a crash, some sequence numbers are skipped |
| No global coordination | Each `instance_id` is fully independent |

---

## Limitations

### Single-process only

`PersistentCounterSource` is **not safe for concurrent use across multiple processes** sharing the same state file. A best-effort `fcntl.flock` advisory lock is applied during block reservation on POSIX systems, but this is not a hard guarantee — do not rely on it as a substitute for proper shard isolation.

The correct pattern for multiple processes is to assign each a **distinct `instance_id`** and a **distinct state file**. Multi-process file locking is planned for v0.4, and a central block allocator (`ReservedBlockSource`) is planned for v0.5.

### Feistel is obfuscation, not encryption

The Feistel permutation provides strong mixing and is reversible, but it is not a formally audited cryptographic primitive. Do not rely on it for access control, token authentication, or any security-sensitive use case.

### instance_id must be assigned manually

There is no automatic shard coordination. Assign `instance_id` values via config or environment variables and ensure they are unique across your deployment.

### Sequence space is large but finite

The default 48-bit sequence space supports ~281 trillion IDs per shard. This is enough for virtually all workloads, but it is not infinite.

---

## Architecture

```
permid64/
  __init__.py       # public exports: Id64, DecodedId, codecs, Id64Config, …
  generator.py      # Id64 façade
  source.py         # PersistentCounterSource
  layout.py         # Layout64 — pack/unpack 64-bit raw value
  permutation.py    # MultiplyOddPermutation, Feistel64Permutation, IdentityPermutation
  codec.py          # fixed-width Base62 / Crockford Base32 for u64
  config.py         # Id64Config + build_id64 (experimental)
  types.py          # DecodedId dataclass

tests/
  test_counter.py
  test_layout.py
  test_permutation.py
  test_codec.py
  test_config.py
  test_id64_e2e.py   # the 5 MVP acceptance tests

benchmarks/
  bench_id64.py
```

---

## Roadmap

| Version | Theme | What's included | Status |
|---|---|---|---|
| **v0.1** | Core primitives | `PersistentCounterSource`, Feistel / Multiplicative permutation, `decode()` | ✅ Released |
| **v0.2** | Encoding & Config | `IdentityPermutation`, fixed-width Base62 + Crockford Base32 (`next_base62` / `decode_base62`, `next_base32` / `decode_base32`), `Id64Config` + `build_id64` | ✅ Released |
| **v0.3** | Human-friendly output | Check digit (+1 char checksum), `PrefixedEncoder` (`ORD_` / `TKT_` / …), `FormatSpec` (segmented display, ambiguity-free charset) | 🔜 Next |
| **v0.4** | Multi-process safety | File locking (`fcntl` / `msvcrt`), single-machine multi-process guarantee (gunicorn / prefork) | Planned |
| **v0.5** | Distributed source | `ReservedBlockSource` (Redis / PG block rental), `instance_id` helpers (hostname hash, env var, StatefulSet ordinal) | Planned |
| **v0.6** | Solution presets | `OrderIdGenerator`, `TicketIdGenerator`, `CorrelationIdGenerator`, `IoTEventIdGenerator` — ready-made recipes for common use cases | Planned |
| **v0.7** | Formal spec | Cross-language bit-layout specification, profile aliases (`m1` / `f6` / `human32`), compatibility guarantee document | Planned |
| **v1.0** | Reference impls | Go reference implementation, Rust reference implementation, three-language cross-decode test suite | Planned |

---

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

```bash
# Clone and set up dev environment
git clone https://github.com/erickh826/permid64.git
cd permid64
pip install -e ".[dev]"

# Run checks before submitting a PR
pytest tests/ -v
ruff check permid64/ tests/
mypy permid64/ --ignore-missing-imports
```

---

## License

MIT
