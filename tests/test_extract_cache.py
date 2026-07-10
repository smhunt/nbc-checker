"""extract_cache.py — raw-response cache: key composition, hit/miss/bypass
counting, atomic writes, fail-open paths. All tests use tmp cache dirs; no
real runner (CLI/API) calls happen here.
"""
import json

import pytest

from extractors.extract_cache import cache_key, cached


def counting_runner(response="RESPONSE", identity="cli:claude"):
    """A fake runner that records every call and always answers `response`."""
    calls = []

    def runner(prompt, path):
        calls.append((prompt, path))
        return response

    runner.calls = calls
    runner.identity = identity
    return runner


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("NBC_EXTRACT_CACHE", raising=False)
    monkeypatch.delenv("NBC_EXTRACT_CACHE_DIR", raising=False)


def _input_file(tmp_path, content=b"tile-bytes"):
    p = tmp_path / "tile.png"
    p.write_bytes(content)
    return str(p)


def test_miss_calls_runner_and_writes_entry(tmp_path):
    runner = counting_runner("R1")
    wrapped = cached(runner, cache_dir=str(tmp_path))
    path = _input_file(tmp_path)

    out = wrapped("PROMPT", path)

    assert out == "R1"
    assert len(runner.calls) == 1
    assert wrapped.stats == {"hits": 0, "misses": 1, "bypassed": 0}
    entries = list(tmp_path.glob("*.json"))
    assert len(entries) == 1
    entry = json.loads(entries[0].read_text())
    assert entry["response"] == "R1"
    assert entry["runner_id"] == "cli:claude"
    assert entry["version"] == "1"
    assert "created_at" in entry


def test_hit_returns_identical_text_without_calling_runner(tmp_path):
    runner = counting_runner("R1")
    wrapped = cached(runner, cache_dir=str(tmp_path))
    path = _input_file(tmp_path)

    first = wrapped("PROMPT", path)
    second = wrapped("PROMPT", path)

    assert first == second == "R1"
    assert len(runner.calls) == 1  # second call served entirely from cache
    assert wrapped.stats == {"hits": 1, "misses": 1, "bypassed": 0}


def test_prompt_change_invalidates(tmp_path):
    runner = counting_runner("R1")
    wrapped = cached(runner, cache_dir=str(tmp_path))
    path = _input_file(tmp_path)

    wrapped("PROMPT A", path)
    wrapped("PROMPT B", path)

    assert len(runner.calls) == 2
    assert wrapped.stats["misses"] == 2


def test_input_bytes_change_invalidates(tmp_path):
    runner = counting_runner("R1")
    wrapped = cached(runner, cache_dir=str(tmp_path))
    p = tmp_path / "tile.png"

    p.write_bytes(b"AAAA")
    wrapped("PROMPT", str(p))
    p.write_bytes(b"BBBB")
    wrapped("PROMPT", str(p))

    assert len(runner.calls) == 2
    assert wrapped.stats["misses"] == 2


def test_runner_cache_id_change_invalidates(tmp_path):
    path = _input_file(tmp_path)
    runner_a = counting_runner("R1", identity=None)
    runner_a.cache_id = "model-v1"
    runner_b = counting_runner("R1", identity=None)
    runner_b.cache_id = "model-v2"

    cached(runner_a, cache_dir=str(tmp_path))("PROMPT", path)
    cached(runner_b, cache_dir=str(tmp_path))("PROMPT", path)

    assert len(runner_a.calls) == 1
    assert len(runner_b.calls) == 1  # different cache_id -> different key -> both miss


def test_env_disable_bypasses(tmp_path, monkeypatch):
    monkeypatch.setenv("NBC_EXTRACT_CACHE", "0")
    runner = counting_runner("R1")
    wrapped = cached(runner, cache_dir=str(tmp_path))
    path = _input_file(tmp_path)

    wrapped("PROMPT", path)
    wrapped("PROMPT", path)

    assert len(runner.calls) == 2  # never served from cache
    assert wrapped.stats == {"hits": 0, "misses": 0, "bypassed": 2}
    assert list(tmp_path.glob("*.json")) == []  # nothing written either


def test_unreadable_input_file_bypasses_fail_open(tmp_path):
    runner = counting_runner("R1")
    wrapped = cached(runner, cache_dir=str(tmp_path))

    out = wrapped("PROMPT", "/tmp/nbc-cache-test-does-not-exist.png")

    assert out == "R1"
    assert len(runner.calls) == 1
    assert wrapped.stats == {"hits": 0, "misses": 0, "bypassed": 1}
    assert list(tmp_path.glob("*.json")) == []


def test_corrupt_entry_is_a_miss_and_rewritten(tmp_path):
    runner = counting_runner("R1")
    path = _input_file(tmp_path)
    wrapped = cached(runner, cache_dir=str(tmp_path))
    key = cache_key("cli:claude", "PROMPT", open(path, "rb").read())
    entry_path = tmp_path / f"{key}.json"
    entry_path.write_text("{ not valid json")

    out = wrapped("PROMPT", path)

    assert out == "R1"
    assert len(runner.calls) == 1
    assert wrapped.stats == {"hits": 0, "misses": 1, "bypassed": 0}
    assert json.loads(entry_path.read_text())["response"] == "R1"  # rewritten


def test_runner_exception_not_cached(tmp_path):
    def boom(prompt, path):
        raise RuntimeError("model unavailable")

    boom.identity = "cli:claude"
    wrapped = cached(boom, cache_dir=str(tmp_path))
    path = _input_file(tmp_path)

    with pytest.raises(RuntimeError, match="model unavailable"):
        wrapped("PROMPT", path)

    assert list(tmp_path.glob("*.json")) == []
    assert wrapped.stats == {"hits": 0, "misses": 0, "bypassed": 0}


def test_cache_dir_env_var_used_when_arg_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("NBC_EXTRACT_CACHE_DIR", str(tmp_path))
    runner = counting_runner("R1")
    wrapped = cached(runner)  # no explicit cache_dir -> falls back to env var

    wrapped("PROMPT", _input_file(tmp_path))

    assert len(list(tmp_path.glob("*.json"))) == 1


def test_cache_key_is_a_deterministic_pure_function():
    a = cache_key("cli:claude", "PROMPT", b"bytes")
    b = cache_key("cli:claude", "PROMPT", b"bytes")
    assert a == b
    assert cache_key("cli:claude", "PROMPT", b"other-bytes") != a
    assert cache_key("api:claude-sonnet-4-6", "PROMPT", b"bytes") != a


def test_wrapped_identity_and_inner_seams():
    runner = counting_runner("R1", identity="api:claude-sonnet-4-6")
    wrapped = cached(runner)
    assert wrapped.identity == "api:claude-sonnet-4-6"
    assert wrapped.inner is runner


def test_wrapped_identity_falls_back_to_unknown_without_inner_identity():
    def plain(prompt, path):
        return "R"

    wrapped = cached(plain)
    assert wrapped.identity == "unknown"
