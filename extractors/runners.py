"""LLM runners for the PDF/image extraction path (EO1 ingestion side).

A runner is a callable `(prompt: str, path: str) -> str` that sends one
extraction prompt plus one input file (a drawing PDF or a PNG tile) to a
generative model and returns the model's text response. Runners are the ONLY
place the extraction pipeline talks to an LLM; everything downstream
(parsing, the EO1 confidence cap, the engine) is deterministic.

Two families:

- CLI runners (`run_claude` / `run_claude_image`, wrapped by
  `make_cli_runner`) shell out to the `claude` CLI in headless mode — no API
  key needed on the machine.
- The API runner (`make_api_runner`) calls the Anthropic Messages API
  directly with the file embedded as a base64 content block. The `anthropic`
  SDK is imported lazily so CLI-only machines never need it installed.

`select_runner(kind)` picks between them ONCE per extraction job (API iff
ANTHROPIC_API_KEY is set; NBC_RUNNER=cli|api overrides). There is no mid-job
fallback: if the chosen path can't run, we fail loud rather than silently
downgrade — silent runner drift would poison provenance.

Every runner carries an `.identity` string ("cli:claude" / "api:<model>")
that the extractors stamp into `project.extractor` so a report always says
which model family produced its facts.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess

CLI_TIMEOUT_S = 300
CLI_IDENTITY = "cli:claude"

# Model used by the API runner. Flip to claude-haiku-4-5-20251001 ONLY after
# a measured A/B (docs/ab-model-results.md, wave 5) supports it.
DEFAULT_EXTRACT_MODEL = "claude-sonnet-4-6"

API_TIMEOUT_S = 120
API_MAX_RETRIES = 2
MAX_TOKENS_TILE = 4096
MAX_TOKENS_PDF = 8192
MAX_PDF_BYTES = 30 * 1024 * 1024  # API document blocks reject ~>32MB; stay clear

_KINDS = ("pdf", "image")


def _check_kind(kind: str) -> None:
    if kind not in _KINDS:
        raise ValueError(f"unknown runner kind {kind!r} (expected 'pdf' or 'image')")


def get_extract_model() -> str:
    """Model id for the API runner; NBC_EXTRACT_MODEL overrides the default."""
    return os.environ.get("NBC_EXTRACT_MODEL") or DEFAULT_EXTRACT_MODEL


# --------------------------------------------------------------------------
# CLI runners (moved verbatim from pdf_extractor.py; re-exported there)
# --------------------------------------------------------------------------

def run_claude(prompt: str, pdf_path: str) -> str:
    """Run the `claude` CLI headless against a PDF; return the assistant text.

    The CLI's --output-format json wraps the response in an envelope whose
    "result" field holds the assistant's text.
    """
    abs_path = os.path.abspath(pdf_path)
    full_prompt = f"{prompt}\n\nThe drawing file to read is at: {abs_path}"
    proc = subprocess.run(
        # --allowedTools "Read" grants the headless instance read-only access so
        # it can open the drawing; without it the nested CLI is denied file access
        # and returns prose instead of JSON.
        ["claude", "-p", full_prompt, "--allowedTools", "Read", "--output-format", "json"],
        capture_output=True,
        text=True,
        timeout=CLI_TIMEOUT_S,
    )
    if proc.returncode != 0:
        stderr_excerpt = (proc.stderr or "").strip()[:500]
        raise RuntimeError(
            f"claude CLI exited with code {proc.returncode}: {stderr_excerpt}"
        )
    envelope = json.loads(proc.stdout)
    return envelope["result"]


def run_claude_image(prompt: str, image_path: str) -> str:
    """Run the `claude` CLI headless against a PNG tile; return assistant text.

    Mirrors `run_claude` but points the nested CLI at an image crop. The
    `--allowedTools Read` grant is required — without it the headless instance
    is denied file access and returns prose instead of JSON.
    """
    abs_path = os.path.abspath(image_path)
    full_prompt = f"{prompt}\n\nThe image to read is at: {abs_path}"
    proc = subprocess.run(
        ["claude", "-p", full_prompt, "--allowedTools", "Read", "--output-format", "json"],
        capture_output=True,
        text=True,
        timeout=CLI_TIMEOUT_S,
    )
    if proc.returncode != 0:
        stderr_excerpt = (proc.stderr or "").strip()[:500]
        raise RuntimeError(
            f"claude CLI exited with code {proc.returncode}: {stderr_excerpt}"
        )
    envelope = json.loads(proc.stdout)
    return envelope["result"]


def make_cli_runner(kind: str):
    """CLI runner for `kind` ("pdf" | "image"), tagged with `.identity`."""
    _check_kind(kind)

    def runner(prompt: str, path: str) -> str:
        # Late-bound module lookup so tests can monkeypatch run_claude*.
        fn = run_claude if kind == "pdf" else run_claude_image
        return fn(prompt, path)

    runner.identity = CLI_IDENTITY
    return runner


# --------------------------------------------------------------------------
# API runner
# --------------------------------------------------------------------------

def _media_block(kind: str, path: str) -> dict:
    """The base64 content block for the input file (image tile or whole PDF)."""
    if kind == "pdf" and os.path.getsize(path) > MAX_PDF_BYTES:
        raise RuntimeError(
            f"PDF {os.path.basename(path)} exceeds the 30MB API document limit "
            f"({os.path.getsize(path)} bytes); use the tiled path or the CLI runner"
        )
    with open(path, "rb") as fh:
        data = base64.standard_b64encode(fh.read()).decode("ascii")
    if kind == "pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": data},
    }


def make_api_runner(kind: str, model: str | None = None, _client_factory=None,
                    usage_cb=None):
    """Direct Anthropic Messages API runner for `kind` ("pdf" | "image").

    The `anthropic` SDK is imported here (not at module import) so CLI-only
    machines are unaffected; a missing package fails at job start with an
    install hint. The client is built ONCE per runner with the key passed
    explicitly — selection (`select_runner` saw a key) and auth can never
    disagree. `_client_factory` is a test seam standing in for
    `anthropic.Anthropic`; production code never passes it.

    `usage_cb`, if given, is called `usage_cb(resp.usage)` after every
    successful `messages.create` (before the refusal/max_tokens check, so a
    usable-but-truncated response still reports its token counts). Additive
    and optional — no caller in the extraction pipeline passes it; it exists
    for diagnostics (`scripts/ab_extract_models.py`) that need per-call token
    counts without duplicating the request/error-mapping logic here. Never
    called on a request that raised (the SDK doesn't return usage for those).
    """
    _check_kind(kind)
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "the API runner needs the anthropic SDK: "
            "pip3 install anthropic --break-system-packages "
            "(or set NBC_RUNNER=cli to use the claude CLI)"
        ) from exc

    model = model or get_extract_model()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set (required for the API runner)")

    factory = _client_factory or anthropic.Anthropic
    client = factory(api_key=api_key, timeout=API_TIMEOUT_S, max_retries=API_MAX_RETRIES)
    max_tokens = MAX_TOKENS_PDF if kind == "pdf" else MAX_TOKENS_TILE

    def runner(prompt: str, path: str) -> str:
        # Media block FIRST, then the prompt text. Unlike the CLI runners, no
        # "file to read is at:" suffix is appended — the payload travels in
        # the request itself. No temperature/thinking params (forward-compat:
        # newer models reject non-default temperature).
        content = [_media_block(kind, path), {"type": "text", "text": prompt}]
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": content}],
            )
        # Most-specific first (Authentication/RateLimit subclass APIStatusError).
        # Messages must NEVER include key material; `from None` also drops the
        # SDK exception (whose repr could carry request details) from the chain.
        except anthropic.AuthenticationError:
            raise RuntimeError(
                "Anthropic API auth failed — check ANTHROPIC_API_KEY"
            ) from None
        except anthropic.RateLimitError:
            raise RuntimeError("Anthropic API rate limited after retries") from None
        except anthropic.APIStatusError as exc:
            raise RuntimeError(
                f"Anthropic API error: status {exc.status_code} ({type(exc).__name__})"
            ) from None
        except anthropic.APIConnectionError as exc:
            raise RuntimeError(
                f"Anthropic API connection error ({type(exc).__name__})"
            ) from None
        if usage_cb is not None:
            usage_cb(getattr(resp, "usage", None))
        if resp.stop_reason in ("refusal", "max_tokens"):
            raise RuntimeError(
                f"Anthropic API response unusable: stop_reason={resp.stop_reason}"
            )
        return "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )

    runner.identity = f"api:{model}"
    return runner


# --------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------

def select_runner(kind: str):
    """Pick the runner for one extraction job (called once, at job start).

    Default: API iff ANTHROPIC_API_KEY is set, else CLI. NBC_RUNNER=cli|api
    overrides. NBC_RUNNER=api without a key fails loud — never a silent
    downgrade to the CLI. No mid-job fallback path exists by design.
    """
    _check_kind(kind)
    choice = os.environ.get("NBC_RUNNER", "").strip().lower()
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if choice == "cli":
        return make_cli_runner(kind)
    if choice == "api":
        if not has_key:
            raise RuntimeError("NBC_RUNNER=api but ANTHROPIC_API_KEY is not set")
        return make_api_runner(kind)
    if choice:
        raise ValueError(
            f"invalid NBC_RUNNER value {choice!r} (expected 'cli' or 'api')"
        )
    return make_api_runner(kind) if has_key else make_cli_runner(kind)
