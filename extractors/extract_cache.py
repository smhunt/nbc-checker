"""Raw-response extraction cache (wave 2, EO1-safe).

Wraps a runner (`(prompt, path) -> str`) so identical (runner identity,
prompt, input-file bytes) calls replay the model's RAW response text instead
of re-running the LLM. Only the raw text is cached — never parsed facts.
Parser fixes, the EO1 confidence cap, and bbox-mapping changes all live
downstream of the runner call and re-apply to a cached response on replay
exactly as they would to a fresh one; caching parsed facts would freeze old
bugs (or old caps) into stale entries, which is an EO1 hazard as much as a
correctness one.

`reports/extract_cache/` (override: `NBC_EXTRACT_CACHE_DIR`) is a flat
directory of `{key}.json` entries with no index and no eviction policy — it
is always safe to delete (same precedent as `reports/page_cache/`).
`NBC_EXTRACT_CACHE=0` disables the wrapper entirely (passthrough to the
runner, no reads or writes).
"""

from __future__ import annotations

import hashlib
import json
import os
import time

DEFAULT_CACHE_DIR = "reports/extract_cache"

# Bump on any change to what a cached response MEANS relative to the raw
# response text (e.g. a future entry-shape change) — invalidates every
# existing entry without touching the cache directory. NOT bumped for CLI
# model drift (the CLI's underlying model is unpinned; `.identity` stays
# "cli:claude" regardless of which model actually answered) — that is a
# documented weakness with no automatic lever; `.cache_id` on a runner is the
# manual bump path for a specific runner if ever needed.
CACHE_SCHEMA = "1"


def _cache_dir(cache_dir: str | None) -> str:
    return cache_dir or os.environ.get("NBC_EXTRACT_CACHE_DIR", DEFAULT_CACHE_DIR)


def _cache_disabled() -> bool:
    return os.environ.get("NBC_EXTRACT_CACHE", "1").strip() == "0"


def _runner_id(runner) -> str:
    """Cache-key identity for a runner: `.identity`, else `.cache_id`, else
    `__qualname__`. Wave 1 stamps `.identity` on every factory-built runner
    ("cli:claude" / "api:<model>"), so by construction an API-model change
    invalidates the cache (the model id is IN the identity string); the
    CLI's underlying model is unpinned and NOT reflected in "cli:claude" —
    `.cache_id` is the manual invalidation lever for that case."""
    return (getattr(runner, "identity", None)
            or getattr(runner, "cache_id", None)
            or getattr(runner, "__qualname__", None)
            or repr(runner))


def cache_key(runner_id: str, prompt: str, input_bytes: bytes) -> str:
    """Deterministic cache key: sha256 over schema version + runner identity
    + prompt + sha256(input bytes). Pure — no filesystem, no env reads."""
    input_sha = hashlib.sha256(input_bytes).hexdigest()
    payload = "\0".join((f"nbc-extract-cache/{CACHE_SCHEMA}", runner_id, prompt, input_sha))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_entry(path: str) -> str | None:
    """Cached response text, or None on miss / missing / corrupt entry.

    A corrupt or unreadable entry is treated as a plain miss — the caller
    re-runs the LLM and overwrites the entry, so a damaged cache directory
    self-heals rather than wedging extraction.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            entry = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(entry, dict) or not isinstance(entry.get("response"), str):
        return None
    return entry["response"]


def _write_entry(path: str, entry: dict) -> None:
    """Atomic write: write to a `.tmp` sibling then `os.replace` into place,
    so a concurrent reader never observes a partially-written entry."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(entry, fh)
    os.replace(tmp_path, path)


def cached(runner, cache_dir: str | None = None):
    """Wrap `runner` with the raw-response cache. Same signature as a runner
    (`(prompt, path) -> str`), so it's a drop-in replacement anywhere a
    runner is used.

    `.stats` = {"hits", "misses", "bypassed"} — call counts, for
    observability only; NEVER read by the extraction pipeline and NEVER
    written into the facts output (a hit/miss count would break run-to-run
    report identity, EO4). `.inner` is the wrapped runner (test seam).
    `.identity` mirrors the inner runner's so provenance (`project.extractor`)
    is unaffected by caching.

    Fail-open (falls straight through to `runner`, counted as "bypassed",
    nothing read or written): `NBC_EXTRACT_CACHE=0`, or the input file can't
    be read (covers fake `/tmp` tile paths used throughout the test suite).
    A runner exception always propagates and is never cached.
    """
    runner_id = _runner_id(runner)
    stats = {"hits": 0, "misses": 0, "bypassed": 0}

    def wrapped(prompt: str, path: str) -> str:
        if _cache_disabled():
            stats["bypassed"] += 1
            return runner(prompt, path)
        try:
            with open(path, "rb") as fh:
                input_bytes = fh.read()
        except OSError:
            stats["bypassed"] += 1
            return runner(prompt, path)

        key = cache_key(runner_id, prompt, input_bytes)
        entry_path = os.path.join(_cache_dir(cache_dir), f"{key}.json")

        hit = _read_entry(entry_path)
        if hit is not None:
            stats["hits"] += 1
            return hit

        # Miss (fresh key, or a corrupt entry _read_entry already discarded).
        # An exception from the runner propagates untouched; nothing is
        # written on failure, so a failed call is never cached.
        response = runner(prompt, path)
        stats["misses"] += 1
        _write_entry(entry_path, {
            "version": CACHE_SCHEMA,
            "runner_id": runner_id,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
            "created_at": time.time(),
            "response": response,
        })
        return response

    wrapped.stats = stats
    wrapped.inner = runner
    wrapped.identity = getattr(runner, "identity", "unknown")
    return wrapped
