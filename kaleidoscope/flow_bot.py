"""Battle-tested headless Google Flow browser automation client.

Combines Playwright persistent profiles, ProseMirror Trusted-Types-safe text
insertion, synthetic ClipboardEvent image pasting, automatic consent/'Try again'
handling, and full-resolution image downloading for batch or single runs.
"""

from __future__ import annotations

import base64
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, Response, sync_playwright

from kaleidoscope.config import Settings, load_settings
from kaleidoscope.crop_engine import slice_turnaround
from kaleidoscope.prompts import PresetName, build_prompt
from kaleidoscope.setup_session import check_auth_state


class FlowHeadlessBot:
    """Automates Google Flow generation in persistent headless/headed browser mode."""

    def __init__(self, settings: Settings | None = None, headless: bool | None = None) -> None:
        self.settings = settings or load_settings()
        self.headless = self.settings.headless if headless is None else headless
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._intercepted_images: list[str] = []

    def start(self) -> FlowHeadlessBot:
        """Launch Playwright persistent browser context."""
        profile_dir = Path(self.settings.profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)
        executable_path, channel = self.settings.resolve_browser_args()

        self._playwright = sync_playwright().start()
        launch_kwargs: dict[str, Any] = {
            "user_data_dir": str(profile_dir),
            "headless": self.headless,
            "args": [
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ],
            "viewport": {"width": 1920, "height": 1080},
        }
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        elif channel:
            launch_kwargs["channel"] = channel

        self._context = self._playwright.chromium.launch_persistent_context(**launch_kwargs)
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.set_default_timeout(self.settings.timeout_sec * 1000)

        def _on_response(resp: Response) -> None:
            url = resp.url
            ct = resp.headers.get("content-type", "")
            if "image/" in ct and ("flow.google.com/asb/" in url or "googleusercontent" in url):
                if url not in self._intercepted_images:
                    self._intercepted_images.append(url)

        self._page.on("response", _on_response)
        return self

    def close(self) -> None:
        """Close browser context and Playwright cleanly."""
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def __enter__(self) -> FlowHeadlessBot:
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Bot not started. Use `with FlowHeadlessBot(...) as bot:`.")
        return self._page

    def navigate(self, url: str | None = None) -> None:
        """Navigate to the configured Google Flow URL and bypass landing CTAs if present."""
        target = url or self.settings.flow_url
        page = self.page
        print(f"Navigating to {target}...")
        page.goto(target, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)

        try:
            create_btn = page.locator("text=/Create with Google Flow|Try Google Flow/i").first
            if create_btn.count() > 0 and create_btn.is_visible(timeout=1500):
                create_btn.click()
                page.wait_for_timeout(3000)
        except Exception:
            pass

    def verify_authenticated(self) -> None:
        """Raise clear actionable error if Google Flow login session is not active."""
        is_auth, reason = check_auth_state(self.page)
        if not is_auth:
            raise RuntimeError(
                f"Google Flow session is not authenticated ({reason}). "
                "Run `python -m kaleidoscope.cli auth` once interactively to sign in."
            )

    def start_new_session(self) -> None:
        """Start a fresh chat thread if available and clear the ProseMirror prompt editor."""
        page = self.page
        try:
            new_btn = page.locator("button[aria-label*='New session'], button:has-text('New session')").first
            if new_btn.count() > 0 and new_btn.is_visible(timeout=1500):
                new_btn.click()
                page.wait_for_timeout(2000)
        except Exception:
            pass

        editor = page.locator(".ProseMirror, [contenteditable='true'], textarea").first
        editor.wait_for(state="visible", timeout=30000)
        editor.click(force=True)
        page.wait_for_timeout(300)

        select_all = "Meta+A" if sys.platform == "darwin" else "Control+A"
        page.keyboard.press(select_all)
        page.keyboard.press("Backspace")
        page.wait_for_timeout(300)

    def set_aspect_ratio(self, ratio: str = "16:9") -> bool:
        """Try configuring generation aspect ratio (e.g., 16:9) in Flow controls."""
        page = self.page
        for sel in [
            f"button:has-text('{ratio}')",
            f"[aria-label*='{ratio}' i]",
            f"[data-ratio='{ratio}']",
            f"div[role='radio']:has-text('{ratio}')",
        ]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=1200):
                    loc.click()
                    page.wait_for_timeout(400)
                    return True
            except Exception:
                continue

        # Check Settings / tune popover if present
        for trigger_sel in ["button[aria-label='Settings']", "button[aria-label*='Settings' i]"]:
            try:
                trig = page.locator(trigger_sel).first
                if trig.count() > 0 and trig.is_visible(timeout=1200):
                    trig.click()
                    page.wait_for_timeout(800)
                    opt = page.locator(f"text=/{ratio}/i").first
                    if opt.count() > 0 and opt.is_visible(timeout=1200):
                        opt.click()
                        page.keyboard.press("Escape")
                        return True
                    page.keyboard.press("Escape")
            except Exception:
                continue
        return False

    def attach_reference_image(self, ref_image_path: str | Path) -> bool:
        """Attach a reference image via ClipboardEvent paste or fallback upload menu."""
        page = self.page
        img_path = Path(ref_image_path).resolve()
        if not img_path.exists():
            raise FileNotFoundError(f"Reference image not found: {img_path}")

        b64_data = base64.b64encode(img_path.read_bytes()).decode("ascii")
        ext = img_path.suffix.lower().lstrip(".")
        mime = "image/jpeg" if ext in {"jpg", "jpeg"} else f"image/{ext or 'png'}"
        fname = f"ref_input.{ 'jpg' if mime == 'image/jpeg' else ext or 'png' }"

        js_paste = """async ({ b64, mime, fname }) => {
            const raw = atob(b64);
            const arr = new Uint8Array(raw.length);
            for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
            const blob = new Blob([arr], { type: mime });
            const file = new File([blob], fname, { type: mime });
            const pm = document.querySelector('.ProseMirror, [contenteditable="true"]') || document.body;
            pm.focus();
            const dt = new DataTransfer();
            dt.items.add(file);
            pm.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt }));
            return true;
        }"""

        attached = False
        try:
            page.evaluate(js_paste, {"b64": b64_data, "mime": mime, "fname": fname})
            page.wait_for_timeout(2500)
            attached = True
        except Exception:
            attached = False

        # Handle optional image upload terms/consent modal ("I agree" / "Agree")
        try:
            agree = page.locator("button:has-text('I agree'), button:has-text('Agree')").first
            if agree.count() > 0 and agree.is_visible(timeout=1500):
                agree.click()
                page.wait_for_timeout(2000)
        except Exception:
            pass

        if attached:
            return True

        # Fallback: standard file chooser button flow
        try:
            add_btn = page.locator("button[aria-label='Add ingredients to the prompt box']").first
            if add_btn.count() > 0 and add_btn.is_visible(timeout=1500):
                add_btn.click()
                page.wait_for_timeout(800)
                upload_item = page.locator("text=/Upload media/i").first
                if upload_item.is_visible(timeout=1500):
                    with page.expect_file_chooser(timeout=5000) as fc_info:
                        upload_item.click()
                    fc_info.value.set_files(str(img_path))
                    page.wait_for_timeout(2500)
                    page.keyboard.press("Escape")
                    return True
        except Exception:
            pass

        return False

    def submit_prompt(self, prompt: str) -> None:
        """Insert prompt into ProseMirror/input editor (Trusted Types safe) and submit."""
        page = self.page
        editor = page.locator(".ProseMirror, [contenteditable='true'], textarea").first
        editor.click(force=True)
        page.wait_for_timeout(300)

        # keyboard.insert_text avoids TrustedHTML / ProseMirror controlled input bugs
        page.keyboard.insert_text(prompt)
        page.wait_for_timeout(800)

        for sel in [
            "button[aria-label='Start generation']",
            "button[aria-label*='Generate' i]",
            "button:has-text('Generate')",
            "button:has-text('Create')",
            "button[type='submit']",
        ]:
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible(timeout=1500):
                    btn.click(force=True)
                    return
            except Exception:
                continue

        page.keyboard.press("Enter")

    def wait_for_generation(
        self,
        dest_path: str | Path,
        opts_before: int,
        timeout_sec: int | None = None,
    ) -> Path:
        """Wait for a new Option tile to render, recover transient retries, and save PNG."""
        page = self.page
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        max_wait = timeout_sec or self.settings.timeout_sec
        deadline = time.time() + max_wait

        new_src: str | None = None
        while time.time() < deadline:
            page.wait_for_timeout(4000)

            try:
                retry_btn = page.locator("button:has-text('Try again')").first
                if retry_btn.count() > 0 and retry_btn.is_visible(timeout=800):
                    print("Transient 'Try again' button detected; retrying...")
                    retry_btn.click()
                    page.wait_for_timeout(2000)
                    continue
            except Exception:
                pass

            opts = page.locator("img[alt^='Option'], img[alt*='Tile displaying']").all()
            if len(opts) > opts_before:
                src = opts[-1].get_attribute("src")
                if src and ("flow.google.com/asb/" in src or "googleusercontent" in src or src.startswith("http")):
                    new_src = src
                    break

        if new_src:
            resp = page.request.get(new_src)
            if resp.status == 200:
                dest.write_bytes(resp.body())
                return dest

        # Fallback: Download button or last rendered image screenshot
        try:
            dl_btn = page.locator("button[aria-label*='Download' i], a[download]").first
            if dl_btn.count() > 0 and dl_btn.is_visible(timeout=1500):
                with page.expect_download(timeout=10000) as dl_info:
                    dl_btn.click()
                dl_info.value.save_as(str(dest))
                return dest
        except Exception:
            pass

        opts = page.locator("img[alt^='Option'], img[alt*='Tile displaying']").all()
        if len(opts) > opts_before:
            opts[-1].screenshot(path=str(dest))
            return dest

        raise TimeoutError(f"Timed out after {max_wait}s waiting for Google Flow image output.")

    def generate_asset(
        self,
        name: str,
        prompt: str,
        preset: PresetName = "character",
        ref_image: str | Path | None = None,
        aspect_ratio: str = "16:9",
        slice_mode: str = "auto",
        output_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        """Execute a complete Flow generation (and 5-view slicing unless preset=='concept')."""
        base_out = Path(output_dir) if output_dir else self.settings.output_dir
        target_dir = base_out / f"{name}_inputs"
        target_dir.mkdir(parents=True, exist_ok=True)
        composite_path = target_dir / f"{name}_composite.png"

        full_prompt = build_prompt(prompt, preset=preset, has_reference_image=bool(ref_image))
        self.start_new_session()
        opts_before = len(self.page.locator("img[alt^='Option'], img[alt*='Tile displaying']").all())

        if aspect_ratio:
            self.set_aspect_ratio(aspect_ratio)
        if ref_image:
            self.attach_reference_image(ref_image)

        self.submit_prompt(full_prompt)
        self.wait_for_generation(composite_path, opts_before=opts_before)

        views: list[Path] = []
        if preset != "concept":
            views = slice_turnaround(
                image_path=composite_path,
                output_dir=target_dir,
                prefix=name,
                preset=preset,
                target_size=self.settings.view_size,
                pad_ratio=self.settings.pad_ratio,
                mode=slice_mode,  # type: ignore[arg-type]
            )

        return {"name": name, "preset": preset, "composite": composite_path, "views": views}

    def inspect_dom(self) -> dict[str, Any]:
        """Inspect live Flow DOM elements for debugging selector changes."""
        page = self.page
        return {
            "url": page.url,
            "title": page.title(),
            "editables": page.locator(".ProseMirror, [contenteditable='true'], textarea").count(),
            "option_imgs": page.locator("img[alt^='Option'], img[alt*='Tile displaying']").count(),
            "buttons": [
                {
                    "text": (b.inner_text() or "").strip().replace("\n", " "),
                    "aria": b.get_attribute("aria-label") or "",
                }
                for b in page.locator("button").all()[:25]
                if b.is_visible()
            ],
        }
