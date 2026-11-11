"""Prompt engineering templates & presets for multi-view consistent generation."""

from __future__ import annotations

from typing import Literal

PresetName = Literal["character", "weapon", "prop_topbottom", "concept"]

PRESET_NAMES: tuple[PresetName, ...] = ("character", "weapon", "prop_topbottom", "concept")

PROMPT_TEMPLATES: dict[PresetName, str] = {
    "character": (
        "A professional 3D character turnaround model sheet of {subject}{ref_clause}, "
        "displaying 5 distinct full-body orthographic views arranged side-by-side in a single "
        "horizontal row on a seamless pure solid white studio background (#FFFFFF). "
        "The 5 views from left to right must be: "
        "1. Front view (neutral symmetric A-pose), "
        "2. Front 3/4 view, "
        "3. Right side profile view, "
        "4. Back 3/4 view, "
        "5. Back view. "
        "Maintain exact anatomy, silhouette, proportions, colors, and surface details across all 5 views. "
        "16:9 aspect ratio, sharp studio lighting, high detail 3D modeling reference, zero text, zero watermark."
    ),
    "weapon": (
        "A professional 3D video game weapon prop turnaround model sheet of {subject}{ref_clause}, "
        "displaying 5 distinct full-length views arranged side-by-side in a single horizontal row "
        "on a seamless pure solid white studio background (#FFFFFF). "
        "The 5 views from left to right must include: "
        "1. Front view (upright), "
        "2. Back view (upright), "
        "3. Side profile view showing thickness and attachments, "
        "4. Top-down 90-degree bird's-eye view looking straight down onto the top cross-section, "
        "5. Dynamic 3/4 perspective view showing full volumetric silhouette. "
        "Consistent scale and materials across all 5 views, 16:9 aspect ratio, clean solid white "
        "background (#FFFFFF), sharp studio lighting, high resolution 3D render, zero text, zero watermark."
    ),
    "prop_topbottom": (
        "A professional 3D game prop turnaround model sheet of {subject}{ref_clause}, "
        "displaying 5 distinct views arranged side-by-side in a single horizontal row "
        "on a seamless pure solid white studio background (#FFFFFF). "
        "The 5 views from left to right must include: "
        "1. Top View (flat vertical orthographic view of the upper surface), "
        "2. 3/4 Top Angled View, "
        "3. Side Profile View (showing thickness and silhouette), "
        "4. 3/4 Bottom Angled View, "
        "5. Bottom View (flat vertical orthographic view of the underside artwork and hardware). "
        "Consistent scale and surface detail across all 5 views, 16:9 aspect ratio, seamless pure solid "
        "white studio background (#FFFFFF), sharp studio lighting, high resolution 3D render, zero text, zero watermark."
    ),
    "concept": (
        "A highly detailed game environment and architectural concept art render of {subject}{ref_clause}. "
        "Clear silhouette readability, modular geometry cues suitable for 3D modeling reference, "
        "16:9 widescreen aspect ratio, rich balanced lighting, crisp materials, zero text, zero watermark."
    ),
}


def build_prompt(
    subject_description: str,
    preset: PresetName = "character",
    has_reference_image: bool = False,
) -> str:
    """Wrap a user subject prompt in an engineered turnaround or concept template.

    If the caller already wrote a full 5-view turnaround sheet specification, it is
    returned as-is so custom prompts are never double-wrapped.
    """
    cleaned = subject_description.strip().rstrip(".")
    lower = cleaned.lower()

    if preset != "concept" and ("turnaround" in lower and ("5 view" in lower or "5-view" in lower or "5 distinct" in lower)):
        return subject_description.strip()

    template = PROMPT_TEMPLATES.get(preset, PROMPT_TEMPLATES["character"])
    ref_clause = " matching the exact design, materials, and colors from the attached reference image" if has_reference_image else ""
    return template.format(subject=cleaned, ref_clause=ref_clause)
