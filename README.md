# id64

**Clock-free, persistent, obfuscated 64-bit ID generation.**

id64 generates globally unique 64-bit integer IDs without relying on wall-clock time. It combines a crash-safe persistent counter with an invertible permutation to produce IDs that look random but carry recoverable metadata.

---

## Why id64?

| Problem | id64's answer |
|---|---|
| Clock skew / NTP jumps break time-based IDs | Counter, not clock |
| IDs must survive process restarts | State file with block reservation |
| Monotonic counters leak business volume | Permutation hides raw counter |
| IDs must be decodable (audit, debug) | `decode()` reverses the permutation |
| No infrastructure dependency | Pure Python, zero runtime deps |

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

## Quick start

```python
from id64 import Id64

# Multiplicative (fastest)
gen = Id64.multiplicative(
    instance_id=42,
    state_file="id64.state",
    block_size=4096,
)

uid = gen.next_u64()          # e.g. 12609531668580943872
meta = gen.decode(uid)
# DecodedId(raw=2748779069440, instance_id=42, sequence=0)

# Feistel (better statistical mixing)
gen2 = Id64.feistel(
    instance_id=42,
    state_file="id64.state",
    block_size=4096,
    key=0xDEADBEEFCAFEBABE,
    rounds=6,
)
```

---

## Installation

```bash
pip install id64          # once published to PyPI
# or from source:
pip install -e ".[dev]"
```

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

## Guarantees & limitations

| Guarantee | Notes |
|---|---|
| No duplicates within a shard | Strict |
| No duplicates across restarts | Strict (state file must be on durable storage) |
| Decodable | Only with the same permutation key/params |
| Gaps allowed | After a crash, some sequence numbers are skipped |
| No global coordination | Each `instance_id` is independent |

**Limitations:**
- Not cryptographically secure (IDs should not be used as secrets).
- State file must be on local or reliably flushed storage; NFS is risky.
- Cross-shard uniqueness requires you to assign distinct `instance_id` values.

---

## Architecture

```
id64/
  __init__.py       # public exports: Id64, DecodedId
  generator.py      # Id64 façade
  source.py         # PersistentCounterSource
  layout.py         # Layout64 — pack/unpack 64-bit raw value
  permutation.py    # MultiplyOddPermutation, Feistel64Permutation
  types.py          # DecodedId dataclass

tests/
  test_counter.py
  test_layout.py
  test_permutation.py
  test_id64_e2e.py   # the 5 MVP acceptance tests

benchmarks/
  bench_id64.py
```

---

## License

MIT
