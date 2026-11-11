# AGENTS.md — AI Assistant Operating Manual for KaleidoscopeV2

Read this entire file before executing any command inside `KaleidoscopeV2`. This document tells autonomous coding agents how to operate the Google Flow headless turnaround generator safely and deterministically in **any workspace**.

---

## 1. Purpose & Pipeline Mental Model

`KaleidoscopeV2` automates **Google Flow** in headless Chromium/Edge/Chrome via Playwright (`kaleidoscope/flow_bot.py`) and slices wide `16:9` multi-view sheets into **5 centered `1024x1024` pure-white (`#FFFFFF`) orthographic PNGs** (`kaleidoscope/crop_engine.py`).

Every asset generated (except `--preset concept`) produces:
- `<KALEIDOSCOPE_OUTPUT_DIR>/<name>_inputs/<name>_composite.png` (raw 16:9 multi-view sheet)
- `<KALEIDOSCOPE_OUTPUT_DIR>/<name>_inputs/01_*_<name>.png` through `05_*_<name>.png` (5 standardized 1024x1024 `#FFFFFF` views ready for 3D modeling, Rodin, Meshy, Tripo, or Roblox asset pipelines)

---

## 2. Mandatory Pre-Flight Workflow for AI Agents

Always execute steps in this exact order:

### Step 1: Verify Environment & Python Dependencies
1. Confirm `.env` exists (if missing, create from `.env.example` — NEVER copy real project URLs or credentials into `.gitignore`d bypasses or tracked files):
   ```bash
   python -c "import playwright, cv2, PIL, numpy; print('deps ok')"
   ```
2. Run offline verification if making code edits:
   ```bash
   python -m unittest discover -s tests -v
   ```

### Step 2: Check Google Flow Authentication Headlessly First
Never launch live generation blindly! Always verify the persistent browser profile first:
```bash
python -m kaleidoscope.cli auth --check
```
- **If exit code is `0` (`AUTHENTICATED`)**: Proceed to Step 3 cleanly in headless mode.
- **If exit code is `1` (`NOT AUTHENTICATED`)**: **STOP** and ask the user to run the one-time interactive sign-in command locally in their terminal:
  ```bash
  python -m kaleidoscope.cli auth
  ```
  Wait for the user to confirm sign-in before resuming headless generation. **Never attempt to automate Google sign-in passwords or bypass login challenges.**

### Step 3: Pick the Right Preset & Command
Choose preset carefully based on asset geometry:
- **`character`** (avatars, creatures, armor, pets): Generates `01_front_view`, `02_three_quarter_front`, `03_side_profile`, `04_three_quarter_back`, `05_back_view`.
- **`weapon`** (swords, hammers, spears, guns): Replaces one angled view with a crisp **90-degree Top-Down Cross-Section (`04_top_view`)** critical for asymmetric blade/head thickness in 3D modeling.
- **`prop_topbottom`** (skateboards, shields, hoverboards, vehicles): Generates `01_top_view`, `02_three_quarter_top`, `03_side_profile`, `04_three_quarter_bottom`, `05_bottom_view` so both upper grip/top deck and underside artwork remain legible.
- **`concept`** (environments, architecture vistas, interior/map callouts): Saves only `<name>_composite.png` at 16:9 without 5-panel slicing.

Single run CLI:
```bash
python -m kaleidoscope.cli generate \
  --name <asset_slug> \
  --preset <character|weapon|prop_topbottom|concept> \
  --prompt "<detailed geometry, surface, & color description>" \
  --ref-image <optional/path/to/reference.png>
```

Multi-asset run CLI (reuses ONE headless browser session — much faster than N sequential commands):
```bash
python -m kaleidoscope.cli batch --config <tasks.json>
```
Where `<tasks.json>` is a list of `{"name": ..., "preset": ..., "prompt": ..., "ref_image": ...}`.

### Step 4: Inspect Outputs Visually Before Handing Off to 3D Modeling
After generation completes:
1. View BOTH `<name>_composite.png` and all 5 sliced `01..05_*.png` files with your image reader tool.
2. Check for:
   - Missing limb/tip clipped at panel edges -> If clipped, re-slice with `--mode projection` or higher `--padding 0.12` using `kaleidoscope slice --input <composite> --output-dir <dir>`.
   - Extra shadow haze or merged views -> Try `--mode contour` vs `--mode projection`.
   - Anatomy drift or extra tails/limbs -> Strengthen negative/anatomical phrasing in custom `--prompt` and attach `--ref-image`.

---

## 3. Troubleshooting Reference for Agents

| Symptom | Root Cause | Exact Recovery Action |
| :--- | :--- | :--- |
| `Session is not authenticated` | Expired cookies or blank `browser_profile/` | Ask user to run `python -m kaleidoscope.cli auth` |
| Wrong 5-panel split / clipped weapon tip | Contour connected shadows or fragments | Re-run offline with `kaleidoscope slice --input ... --mode projection` |
| Prompt not typed or button unclickable | Google Flow UI DOM updated | Run `python -m kaleidoscope.cli inspect --headed` and update selectors in `kaleidoscope/flow_bot.py` |
| Timed out waiting for image (`120s`) | Transient server latency or queue stall | Increase `KALEIDOSCOPE_TIMEOUT_SEC=180` in `.env` and re-run |
| Reference upload consent blocked | First-time Google Flow media consent modal | `flow_bot.py` auto-clicks `I agree`; if changed, run `kaleidoscope generate --headed` to observe |

---

## 4. Strict Security & Git Hygiene Rules (Mandatory)

1. **NEVER** commit, print, or upload `.env`, `browser_profile/`, cookie files, or private `FLOW_PROJECT_URL` UUIDs to Git or artifacts.
2. **NEVER** hardcode absolute user home directories (e.g. `C:\Users\<name>\...`) inside tracked source files — always read from `kaleidoscope.config.load_settings()`.
3. Keep `outputs/`, `references/`, and `.scratch/` out of version control unless an explicit repo example asset is intended.
