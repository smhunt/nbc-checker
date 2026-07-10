"""Runner factory tests — selection matrix, mocked API runner, error mapping.

No real API calls and no `claude` CLI calls happen here: the API runner is
exercised through the `_client_factory` seam with a fake client, and CLI
runners are only inspected (identity), never invoked.

ANTHROPIC_API_KEY is always monkeypatched — tests must never depend on (or
read) any key material present elsewhere on the machine.
"""
import base64
import importlib
import sys
from types import SimpleNamespace

import pytest

from extractors import runners
from extractors.runners import (
    API_MAX_RETRIES,
    API_TIMEOUT_S,
    DEFAULT_EXTRACT_MODEL,
    MAX_PDF_BYTES,
    MAX_TOKENS_PDF,
    MAX_TOKENS_TILE,
    get_extract_model,
    make_api_runner,
    make_cli_runner,
    select_runner,
)

FAKE_KEY = "sk-ant-test-FAKE-KEY-not-real"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Every test starts with no runner-related env vars set."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NBC_RUNNER", raising=False)
    monkeypatch.delenv("NBC_EXTRACT_MODEL", raising=False)


# --------------------------------------------------------------------------
# Fake anthropic client (injected via the _client_factory seam)
# --------------------------------------------------------------------------

def fake_response(texts=("{}",), stop_reason="end_turn", extra_blocks=()):
    blocks = [SimpleNamespace(type="text", text=t) for t in texts]
    blocks.extend(extra_blocks)
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response or fake_response()
        self.error = error
        self.create_calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.create_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def factory_for(client, seen_kwargs=None):
    def _factory(**kwargs):
        if seen_kwargs is not None:
            seen_kwargs.update(kwargs)
        return client

    return _factory


# --------------------------------------------------------------------------
# Selection matrix
# --------------------------------------------------------------------------

def test_default_without_key_selects_cli():
    runner = select_runner("image")
    assert runner.identity == "cli:claude"


def test_key_present_selects_api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    runner = select_runner("image")
    assert runner.identity == f"api:{DEFAULT_EXTRACT_MODEL}"


def test_nbc_runner_cli_overrides_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("NBC_RUNNER", "cli")
    assert select_runner("pdf").identity == "cli:claude"


def test_nbc_runner_api_without_key_raises(monkeypatch):
    monkeypatch.setenv("NBC_RUNNER", "api")
    with pytest.raises(RuntimeError, match="NBC_RUNNER=api but ANTHROPIC_API_KEY is not set"):
        select_runner("image")


def test_invalid_nbc_runner_raises_value_error(monkeypatch):
    monkeypatch.setenv("NBC_RUNNER", "turbo")
    with pytest.raises(ValueError, match="NBC_RUNNER"):
        select_runner("image")


def test_invalid_kind_raises_value_error():
    with pytest.raises(ValueError, match="kind"):
        select_runner("video")
    with pytest.raises(ValueError, match="kind"):
        make_cli_runner("video")


def test_nbc_extract_model_overrides_default(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("NBC_EXTRACT_MODEL", "claude-haiku-4-5-20251001")
    assert get_extract_model() == "claude-haiku-4-5-20251001"
    runner = select_runner("image")
    assert runner.identity == "api:claude-haiku-4-5-20251001"


# --------------------------------------------------------------------------
# API runner behavior (mocked client)
# --------------------------------------------------------------------------

def test_api_runner_image_sends_base64_png_block_then_prompt_text(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    png = tmp_path / "tile_r1c1.png"
    png_bytes = b"\x89PNG\r\n\x1a\nfake-tile-bytes"
    png.write_bytes(png_bytes)

    client = FakeClient(response=fake_response(texts=('{"entities": []}',)))
    seen = {}
    runner = make_api_runner("image", model="test-model",
                             _client_factory=factory_for(client, seen))

    out = runner("EXTRACT PROMPT", str(png))
    assert out == '{"entities": []}'

    # client constructed once with explicit key + timeouts/retries
    assert seen == {"api_key": FAKE_KEY, "timeout": API_TIMEOUT_S,
                    "max_retries": API_MAX_RETRIES}

    (call,) = client.create_calls
    assert call["model"] == "test-model"
    assert call["max_tokens"] == MAX_TOKENS_TILE
    assert "temperature" not in call and "thinking" not in call
    (msg,) = call["messages"]
    assert msg["role"] == "user"
    media, text = msg["content"]  # media block FIRST, then the prompt text
    assert media == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.standard_b64encode(png_bytes).decode("ascii"),
        },
    }
    assert text == {"type": "text", "text": "EXTRACT PROMPT"}
    # The CLI's path suffix must NOT be appended — the payload travels inline.
    assert "to read is at" not in text["text"]


def test_api_runner_pdf_sends_document_block(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    pdf = tmp_path / "plan.pdf"
    pdf_bytes = b"%PDF-1.4 fake"
    pdf.write_bytes(pdf_bytes)

    client = FakeClient(response=fake_response(texts=('{"entities": []}',)))
    runner = make_api_runner("pdf", model="test-model",
                             _client_factory=factory_for(client))
    runner("PDF PROMPT", str(pdf))

    (call,) = client.create_calls
    assert call["max_tokens"] == MAX_TOKENS_PDF
    media, text = call["messages"][0]["content"]
    assert media == {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": base64.standard_b64encode(pdf_bytes).decode("ascii"),
        },
    }
    assert text == {"type": "text", "text": "PDF PROMPT"}


def test_api_runner_oversized_pdf_raises_clear_error(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    pdf = tmp_path / "huge.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setattr("os.path.getsize", lambda p: MAX_PDF_BYTES + 1)

    client = FakeClient()
    runner = make_api_runner("pdf", model="m", _client_factory=factory_for(client))
    with pytest.raises(RuntimeError, match="30MB"):
        runner("PROMPT", str(pdf))
    assert client.create_calls == []  # rejected before any request


def test_api_runner_concatenates_text_blocks(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    png = tmp_path / "t.png"
    png.write_bytes(b"png")
    non_text = SimpleNamespace(type="thinking", thinking="ignore me")
    client = FakeClient(response=fake_response(
        texts=('{"entities": ', "[]}"), extra_blocks=(non_text,)))
    runner = make_api_runner("image", model="m", _client_factory=factory_for(client))
    assert runner("P", str(png)) == '{"entities": []}'


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_api_runner_refusal_or_max_tokens_raises_runtime_error(
        monkeypatch, tmp_path, stop_reason):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    png = tmp_path / "t.png"
    png.write_bytes(b"png")
    client = FakeClient(response=fake_response(stop_reason=stop_reason))
    runner = make_api_runner("image", model="m", _client_factory=factory_for(client))
    with pytest.raises(RuntimeError, match=stop_reason):
        runner("P", str(png))


def _http_error(cls, status):
    import httpx
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("api error", response=httpx.Response(status, request=req), body=None)


def test_api_error_message_never_contains_key(monkeypatch, tmp_path):
    import anthropic
    import httpx

    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    png = tmp_path / "t.png"
    png.write_bytes(b"png")

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    cases = [
        (_http_error(anthropic.AuthenticationError, 401),
         "Anthropic API auth failed — check ANTHROPIC_API_KEY"),
        (_http_error(anthropic.RateLimitError, 429), "rate limited after retries"),
        (_http_error(anthropic.APIStatusError, 500), "500"),
        (anthropic.APIConnectionError(request=req), "connection"),
    ]
    for error, expected in cases:
        client = FakeClient(error=error)
        runner = make_api_runner("image", model="m", _client_factory=factory_for(client))
        with pytest.raises(RuntimeError) as exc_info:
            runner("P", str(png))
        message = str(exc_info.value)
        assert expected.lower() in message.lower()
        assert FAKE_KEY not in message
        # the key must not leak through the exception chain either
        chain = exc_info.value.__cause__
        assert chain is None or FAKE_KEY not in str(chain)


def test_make_api_runner_without_key_raises(monkeypatch):
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        make_api_runner("image", model="m", _client_factory=lambda **kw: FakeClient())


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------

def test_api_runner_identity_includes_model_id(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    runner = make_api_runner("image", model="claude-haiku-4-5-20251001",
                             _client_factory=lambda **kw: FakeClient())
    assert runner.identity == "api:claude-haiku-4-5-20251001"
    default = make_api_runner("pdf", _client_factory=lambda **kw: FakeClient())
    assert default.identity == f"api:{DEFAULT_EXTRACT_MODEL}"


def test_cli_runner_identity_is_cli_claude():
    assert make_cli_runner("pdf").identity == "cli:claude"
    assert make_cli_runner("image").identity == "cli:claude"


def test_cli_runner_dispatches_by_kind(monkeypatch):
    calls = []
    monkeypatch.setattr(runners, "run_claude",
                        lambda prompt, path: calls.append(("pdf", prompt, path)) or "r1")
    monkeypatch.setattr(runners, "run_claude_image",
                        lambda prompt, path: calls.append(("image", prompt, path)) or "r2")
    assert make_cli_runner("pdf")("P", "f.pdf") == "r1"
    assert make_cli_runner("image")("P", "t.png") == "r2"
    assert calls == [("pdf", "P", "f.pdf"), ("image", "P", "t.png")]


# --------------------------------------------------------------------------
# Back-compat re-export + lazy anthropic import
# --------------------------------------------------------------------------

def test_run_claude_reexported_from_pdf_extractor():
    from extractors import pdf_extractor

    assert pdf_extractor.run_claude is runners.run_claude
    assert pdf_extractor.run_claude_image is runners.run_claude_image
    assert pdf_extractor.CLI_TIMEOUT_S == runners.CLI_TIMEOUT_S == 300


def test_runners_module_imports_without_anthropic_installed(monkeypatch):
    """CLI-only machines: importing runners must not require the SDK."""
    monkeypatch.setitem(sys.modules, "anthropic", None)  # poison: import raises
    monkeypatch.delitem(sys.modules, "extractors.runners", raising=False)
    mod = importlib.import_module("extractors.runners")
    assert mod.select_runner("image").identity == "cli:claude"  # no key set
    # ... but asking for the API runner fails loud, with an install hint
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    with pytest.raises(ImportError, match="pip3 install anthropic"):
        mod.make_api_runner("image")
