"""Environment-backed configuration loader for KaleidoscopeV2.

Safely reads `.env` and OS environment variables without hardcoding any user
machine paths, cookies, API keys, or private Google Flow project UUIDs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional fallback before pip install
    load_dotenv = None


def _load_dotenv_fallback(env_path: Path) -> None:
    """Parse key=value pairs from .env if python-dotenv is not installed."""
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Resolved runtime configuration for browser automation and CV slicing."""

    flow_url: str
    profile_dir: Path
    output_dir: Path
    browser_channel: str
    browser_path: Path | None
    headless: bool
    timeout_sec: int
    view_size: int
    pad_ratio: float

    def resolve_browser_args(self) -> tuple[str | None, str | None]:
        """Return (executable_path, channel) tuple compatible with Playwright."""
        if self.browser_path and self.browser_path.exists():
            return str(self.browser_path), None

        channel = self.browser_channel.strip().lower()
        if channel in {"msedge", "chrome"}:
            return None, channel
        # Fallback for bundled Playwright chromium or custom channel string
        if channel == "chromium" or not channel:
            return None, None
        return None, channel


def load_settings(env_file: str | Path | None = None, base_dir: str | Path | None = None) -> Settings:
    """Load Settings from `.env` (if present) and environment variables."""
    root = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
    env_path = Path(env_file) if env_file else (root / ".env")

    if env_path.is_file():
        if load_dotenv is not None:
            load_dotenv(dotenv_path=env_path, override=False)
        else:
            _load_dotenv_fallback(env_path)

    def resolve_rel(env_key: str, default_rel: str) -> Path:
        raw = os.environ.get(env_key, "").strip() or default_rel
        p = Path(raw).expanduser()
        return p if p.is_absolute() else (root / p).resolve()

    raw_browser_path = os.environ.get("KALEIDOSCOPE_BROWSER_PATH", "").strip()
    browser_path = Path(raw_browser_path).expanduser() if raw_browser_path else None

    flow_url = os.environ.get("FLOW_PROJECT_URL", "").strip() or "https://flow.google.com/"
    browser_channel = os.environ.get("KALEIDOSCOPE_BROWSER_CHANNEL", "msedge").strip() or "msedge"

    return Settings(
        flow_url=flow_url,
        profile_dir=resolve_rel("KALEIDOSCOPE_PROFILE_DIR", "./browser_profile"),
        output_dir=resolve_rel("KALEIDOSCOPE_OUTPUT_DIR", "./outputs"),
        browser_channel=browser_channel,
        browser_path=browser_path,
        headless=_parse_bool(os.environ.get("KALEIDOSCOPE_HEADLESS"), default=True),
        timeout_sec=int(os.environ.get("KALEIDOSCOPE_TIMEOUT_SEC", "120") or 120),
        view_size=int(os.environ.get("KALEIDOSCOPE_VIEW_SIZE", "1024") or 1024),
        pad_ratio=float(os.environ.get("KALEIDOSCOPE_PAD_RATIO", "0.08") or 0.08),
    )
