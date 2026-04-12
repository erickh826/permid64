# Changelog

## 0.2.0

- Added fixed-width **Base62** (11 characters, `0-9A-Za-z`) and **Crockford Base32** (13 uppercase characters) codecs in `permid64.codec`, with `u64_to_*` / `*_to_u64` helpers.
- Extended `Id64` with `next_base62`, `decode_base62`, `next_base32`, `decode_base32`, and factory `Id64.identity` (uses `IdentityPermutation`).
- Added experimental `Id64Config` and `build_id64` in `permid64.config` for JSON-friendly configuration round-trips.

## 0.1.0

- Initial release: persistent counter, `Layout64`, multiplicative and Feistel permutations, `Id64`, `decode`.
