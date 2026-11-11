# CLAUDE.md — Claude Code Instructions for KaleidoscopeV2

See [`AGENTS.md`](AGENTS.md) for the full agent playbook. Quick summary for Claude Code sessions:

## Stack & Architecture
- **Language**: Python 3.10+ (`kaleidoscope` package, `kaleidoscope.cli:main`).
- **Automation**: Playwright persistent browser context (`msedge`/`chrome`/`chromium`) targeting Google Flow (`.ProseMirror` clipboard paste for reference images + `keyboard.insert_text` + `img[alt^='Option']` polling).
- **CV Engine**: OpenCV + Pillow + NumPy (`kaleidoscope/crop_engine.py`) turning 16:9 turnaround sheets into 5 centered `1024x1024` pure `#FFFFFF` PNGs.

## Essential Commands
```bash
# Offline test suite (must pass after any edit)
python -m unittest discover -s tests -v
python -m kaleidoscope.cli generate --name smoke_test --prompt "test knight" --mock

# Session check (headless) before live generation
python -m kaleidoscope.cli auth --check

# Re-slice existing composite without regenerating
python -m kaleidoscope.cli slice --input sheet.png --output-dir ./outputs/asset_inputs --prefix asset --mode projection
```

## Non-Negotiable Rules
1. Always load config via `kaleidoscope.config.load_settings()` — never hardcode user home paths or project UUIDs.
2. Never read/expose/commit `.env` or `browser_profile/` contents.
3. Verify auth status (`auth --check`) before attempting headless Flow runs; ask the user to run `auth` interactively if unauthenticated.
