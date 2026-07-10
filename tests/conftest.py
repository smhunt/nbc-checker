"""Shared pytest fixtures.

The wave-2 extraction cache (`extractors/extract_cache.py`) is wired into
`extract`/`extract_tiled` as the default behind `select_runner(...)`, keyed
to `reports/extract_cache` unless `NBC_EXTRACT_CACHE_DIR` overrides it. Any
test that resolves a runner via the factory path (`runner=None`) would
otherwise read/write the real project's `reports/` directory. This autouse
fixture redirects every test to a fresh tmp cache dir so the suite never
touches real on-disk state. Tests that build their own `cached(...)` wrapper
explicitly (passing their own `cache_dir=tmp_path`) are unaffected — an
explicit `cache_dir` argument always wins over the env var.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_extract_cache_dir(tmp_path_factory, monkeypatch):
    cache_dir = tmp_path_factory.mktemp("extract_cache")
    monkeypatch.setenv("NBC_EXTRACT_CACHE_DIR", str(cache_dir))
