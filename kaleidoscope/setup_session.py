"""Interactive one-time Google Flow authentication setup & headless session checker."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from kaleidoscope.config import Settings, load_settings


def check_auth_state(page: Any) -> tuple[bool, str]:
    """Inspect DOM and URL to check whether the current Google Flow session is signed in."""
    current_url = (page.url or "").lower()

    if "accounts.google.com" in current_url or "signin" in current_url:
        return False, f"Redirected to Google Sign-In: {page.url}"

    for sel, msg in [
        ("a[href*='accounts.google.com/ServiceLogin']", "Google Sign-In link visible on page"),
        ("text=/Sign in|Log in|Masuk/i", "Sign-In button detected on page"),
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=1500):
                return False, msg
        except Exception:
            pass

    if "/about" in current_url:
        try:
            about_cta = page.locator("text=/Create with Google Flow|Try Google Flow/i").first
            if about_cta.count() > 0 and about_cta.is_visible(timeout=1500):
                # Even on /about, if no Sign-In button appeared, the account may already be active
                return False, "On Google Flow /about landing page; open interactive setup to enter project workspace"
        except Exception:
            pass

    return True, f"Session active at {page.url}"


def run_session_setup(settings: Settings | None = None, check_only: bool = False) -> bool:
    """Launch persistent browser context to authenticate Google Flow or check session health."""
    cfg = settings or load_settings()
    profile_path = Path(cfg.profile_dir)
    profile_path.mkdir(parents=True, exist_ok=True)
    executable_path, channel = cfg.resolve_browser_args()

    launch_args = [
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
    ]

    with sync_playwright() as p:
        launch_kwargs: dict[str, Any] = {
            "user_data_dir": str(profile_path),
            "headless": check_only,
            "args": launch_args,
            "viewport": {"width": 1440, "height": 900},
        }
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        elif channel:
            launch_kwargs["channel"] = channel

        context = p.chromium.launch_persistent_context(**launch_kwargs)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(cfg.flow_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)

            if check_only:
                is_auth, reason = check_auth_state(page)
                print(f"Auth Status: {'AUTHENTICATED' if is_auth else 'NOT AUTHENTICATED'}")
                print(f"Details    : {reason}")
                return is_auth

            print("\n=== Interactive Google Flow Session Setup ===")
            print(f"Profile dir: {profile_path}")
            print(f"Target URL : {cfg.flow_url}")
            print("1. Complete Google login in the visible browser window.")
            print("2. Open/create a Google Flow project and copy its URL into `.env` as `FLOW_PROJECT_URL` if desired.")
            print("3. Return here and press [ENTER] to save cookies/session and close.")
            try:
                input("\n>>> Press [ENTER] once you are signed in and ready... <<<")
            except (KeyboardInterrupt, EOFError):
                print("\nClosing browser...")
            return True
        finally:
            context.close()
