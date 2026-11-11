---
name: kaleidoscope-v2
description: >-
  Automates visually consistent 5-in-1 3D asset turnaround generation (Front, Back,
  Side, 3/4, Top/Bottom) and 16:9 concept art via Google Flow headless browser
  automation + Computer Vision square-canvas slicing. Trigger when asked to generate
  consistent multi-view character/weapon/prop references, slice a 5-view sheet into
  1024x1024 pure white views, or automate Google Flow image generation in a workspace.
---

# KaleidoscopeV2 Portable Skill

Use this skill whenever the workspace contains (or references) the **KaleidoscopeV2** repository (`python -m kaleidoscope.cli`).

## Standard Execution Sequence

1. **Check Environment & Auth Headlessly**:
   ```bash
   python -m kaleidoscope.cli auth --check
   ```
   - If not authenticated (exit code `1`), instruct the user to sign in once interactively with:
     ```bash
     python -m kaleidoscope.cli auth
     ```
     and stop until sign-in completes.

2. **Generate Consistent Multi-View Reference Sheets**:
   - Use `--preset character` for characters/creatures/pets.
   - Use `--preset weapon` when side thickness + top-down 90° view are needed for swords/hammers/spears.
   - Use `--preset prop_topbottom` when both top artwork and underside artwork matter (skateboards, shields, boards).
   - Use `--preset concept` for single 16:9 architectural/map concept art (skips 5-view slicing).
   - Always pass `--ref-image <path>` when matching an existing concept image!

   ```bash
   python -m kaleidoscope.cli generate \
     --name <asset_slug> \
     --preset <character|weapon|prop_topbottom|concept> \
     --prompt "<description>" \
     --ref-image <optional_ref.png>
   ```

3. **Batch Multiple Assets Efficiently**:
   Build a JSON task list and invoke `batch` so all assets reuse one browser session:
   ```bash
   python -m kaleidoscope.cli batch --config <tasks.json>
   ```

4. **Re-Slice Only (If Crop Boundaries Need Adjustment)**:
   ```bash
   python -m kaleidoscope.cli slice \
     --input <composite.png> \
     --output-dir <out_dir> \
     --prefix <asset_slug> \
     --preset <character|weapon|prop_topbottom> \
     --mode projection
   ```

5. **Inspect Results & Keep Secrets Private**:
   - Open the generated `01..05` 1024x1024 PNGs visually before feeding into Blender/Rodin/Meshy/Roblox.
   - Never stage, commit, or print `.env`, `browser_profile/`, cookies, or private Google Flow project UUIDs.
