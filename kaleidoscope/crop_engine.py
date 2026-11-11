"""Hybrid Computer Vision 5-in-1 Turnaround Slicing & Centering Engine.

Converts a wide panoramic (e.g., 16:9) 5-view turnaround sheet into 5 cleanly
separated, tightly bounded, aspect-ratio-preserved 1:1 square orthographic
PNGs centered on pure solid white (#FFFFFF) canvases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Sequence

import cv2
import numpy as np
from PIL import Image

SliceMode = Literal["auto", "contour", "projection"]

PRESET_VIEW_NAMES: dict[str, tuple[str, ...]] = {
    "character": (
        "01_front_view",
        "02_three_quarter_front",
        "03_side_profile",
        "04_three_quarter_back",
        "05_back_view",
    ),
    "weapon": (
        "01_front_view",
        "02_back_view",
        "03_right_view",
        "04_top_view",
        "05_perspective",
    ),
    "prop_topbottom": (
        "01_top_view",
        "02_three_quarter_top",
        "03_side_profile",
        "04_three_quarter_bottom",
        "05_bottom_view",
    ),
}

DEFAULT_VIEW_NAMES = PRESET_VIEW_NAMES["character"]


def estimate_background_color_rgb(image_rgb: np.ndarray) -> np.ndarray:
    """Estimate studio background RGB color by sampling all four corners."""
    h, w, _ = image_rgb.shape
    c_size = max(5, min(h, w) // 50)
    corners = [
        image_rgb[0:c_size, 0:c_size],
        image_rgb[0:c_size, w - c_size : w],
        image_rgb[h - c_size : h, 0:c_size],
        image_rgb[h - c_size : h, w - c_size : w],
    ]
    medians = [np.median(c, axis=(0, 1)) for c in corners]
    return np.mean(medians, axis=0).astype(np.float32)


def build_foreground_mask(image_rgb: np.ndarray) -> np.ndarray:
    """Build a binary subject mask (255 = foreground, 0 = white studio / light shadow)."""
    bg_rgb = estimate_background_color_rgb(image_rgb)
    diff = np.linalg.norm(image_rgb.astype(np.float32) - bg_rgb, axis=2)

    # HSV helps suppress neutral soft floor shadows near studio white backgrounds
    hsv = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2HSV)
    near_white_bg = float(np.min(bg_rgb)) > 230.0

    threshold = max(18.0, float(np.percentile(diff, 10)) + 12.0)
    fg = diff > threshold

    if near_white_bg:
        is_pure_white = (image_rgb[:, :, 0] > 240) & (image_rgb[:, :, 1] > 240) & (image_rgb[:, :, 2] > 240)
        is_soft_shadow = (
            (image_rgb[:, :, 0] > 215)
            & (image_rgb[:, :, 1] > 215)
            & (image_rgb[:, :, 2] > 215)
            & (hsv[:, :, 1] < 20)
        )
        fg = fg & (~is_pure_white) & (~is_soft_shadow)

    mask = fg.astype(np.uint8) * 255
    # Close vertical gaps inside limbs/accessories and clear isolated pixel dust
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return mask


def _merge_overlapping_x_boxes(boxes: list[tuple[int, int, int, int]], overlap_gap: int = 8) -> list[tuple[int, int, int, int]]:
    """Merge vertically stacked / overlapping components belonging to the same view column."""
    if not boxes:
        return []
    ordered = sorted(boxes, key=lambda b: b[0])
    merged: list[tuple[int, int, int, int]] = [ordered[0]]

    for x, y, bw, bh in ordered[1:]:
        px, py, pbw, pbh = merged[-1]
        prev_x2 = px + pbw
        cur_x2 = x + bw
        # Merge if X intervals overlap or are within tight horizontal gap (floating halo/weapon tip)
        if x <= prev_x2 + overlap_gap:
            nx = min(px, x)
            ny = min(py, y)
            nx2 = max(prev_x2, cur_x2)
            ny2 = max(py + pbh, y + bh)
            merged[-1] = (nx, ny, nx2 - nx, ny2 - ny)
        else:
            merged.append((x, y, bw, bh))
    return merged


def detect_contour_boxes(fg_mask: np.ndarray, expected_views: int = 5) -> list[tuple[int, int, int, int]] | None:
    """Detect N horizontally ordered subject bounding boxes via OpenCV contours."""
    h, w = fg_mask.shape
    min_area = max(300, int(w * h * 0.0015))
    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    raw_boxes: list[tuple[int, int, int, int]] = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw * bh >= min_area:
            raw_boxes.append((x, y, bw, bh))

    merged = _merge_overlapping_x_boxes(raw_boxes, overlap_gap=max(6, w // 250))
    if len(merged) == expected_views:
        return merged
    return None


def find_projection_slices(fg_mask: np.ndarray, expected_views: int = 5) -> list[tuple[int, int]]:
    """Segment image horizontally by locating local minima in smoothed vertical projection."""
    _, width = fg_mask.shape
    proj = np.sum(fg_mask > 0, axis=0).astype(np.float32)

    sigma = max(2.0, width / 120.0)
    radius = int(sigma * 3)
    x_grid = np.arange(-radius, radius + 1)
    kernel = np.exp(-(x_grid**2) / (2.0 * sigma**2))
    kernel /= np.sum(kernel)
    smoothed = np.convolve(proj, kernel, mode="same")

    ideal_w = width / expected_views
    splits = [0]
    for i in range(1, expected_views):
        nominal = int(i * ideal_w)
        search_rad = int(ideal_w * 0.30)
        lo = max(0, nominal - search_rad)
        hi = min(width - 1, nominal + search_rad)
        window = smoothed[lo:hi]
        best = lo + int(np.argmin(window)) if len(window) > 0 else nominal
        splits.append(best)
    splits.append(width)

    return [(splits[i], splits[i + 1]) for i in range(expected_views)]


def center_crop_on_canvas(
    crop_img: Image.Image,
    target_size: int = 1024,
    pad_ratio: float = 0.08,
    bg_rgb: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Scale a cropped view preserving aspect ratio and center on a solid square canvas."""
    cw, ch = crop_img.size
    if cw <= 0 or ch <= 0:
        return Image.new("RGB", (target_size, target_size), bg_rgb)

    usable = max(16, int(round(target_size * (1.0 - 2.0 * pad_ratio))))
    scale = min(usable / cw, usable / ch)
    new_w = max(1, int(round(cw * scale)))
    new_h = max(1, int(round(ch * scale)))

    resized = crop_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_size, target_size), bg_rgb)
    canvas.paste(resized, ((target_size - new_w) // 2, (target_size - new_h) // 2))
    return canvas


def slice_turnaround(
    image_path: str | Path,
    output_dir: str | Path,
    prefix: str | None = None,
    preset: str = "character",
    view_names: Sequence[str] | None = None,
    target_size: int = 1024,
    pad_ratio: float = 0.08,
    mode: SliceMode = "auto",
) -> list[Path]:
    """Slice a multi-view panoramic turnaround sheet into centered 1:1 square PNGs.

    Args:
        image_path: Path to composite input turnaround image (typically 16:9).
        output_dir: Destination folder for output 1:1 square PNG views.
        prefix: Optional asset prefix appended to filenames (e.g. ``01_front_view_hero.png``).
        preset: View label preset (``character``, ``weapon``, or ``prop_topbottom``).
        view_names: Custom sequence of base filenames (overrides ``preset``).
        target_size: Output square dimension in pixels (default 1024).
        pad_ratio: White border margin ratio (default 0.08 = 8% per side).
        mode: Segmentation strategy (``auto``, ``contour``, or ``projection``).

    Returns:
        List of output PNG file paths in left-to-right view order.
    """
    src = Path(image_path)
    if not src.exists():
        raise FileNotFoundError(f"Composite turnaround image not found: {src}")

    im = Image.open(src).convert("RGB")
    arr = np.asarray(im)
    h, w, _ = arr.shape

    labels = list(view_names) if view_names else list(PRESET_VIEW_NAMES.get(preset, DEFAULT_VIEW_NAMES))
    expected_views = len(labels)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fg_mask = build_foreground_mask(arr)

    boxes: list[tuple[int, int, int, int]] | None = None
    if mode in ("auto", "contour"):
        boxes = detect_contour_boxes(fg_mask, expected_views=expected_views)

    crops: list[Image.Image] = []
    if boxes is not None and mode != "projection":
        pad_px_x = max(8, w // 110)
        pad_px_y = max(8, h // 65)
        for bx, by, bw, bh in boxes:
            x1 = max(0, bx - pad_px_x)
            y1 = max(0, by - pad_px_y)
            x2 = min(w, bx + bw + pad_px_x)
            y2 = min(h, by + bh + pad_px_y)
            crops.append(im.crop((x1, y1, x2, y2)))
    else:
        if mode == "contour":
            raise RuntimeError(f"Contour mode expected {expected_views} distinct subjects, could not cleanly isolate.")
        x_intervals = find_projection_slices(fg_mask, expected_views=expected_views)
        for sx, ex in x_intervals:
            sub_mask = fg_mask[:, sx:ex]
            ys, xs = np.where(sub_mask > 0)
            if len(ys) > 50:
                x1 = max(0, sx + int(np.min(xs)) - 8)
                y1 = max(0, int(np.min(ys)) - 8)
                x2 = min(w, sx + int(np.max(xs)) + 9)
                y2 = min(h, int(np.max(ys)) + 9)
                crops.append(im.crop((x1, y1, x2, y2)))
            else:
                crops.append(im.crop((sx, 0, ex, h)))

    saved_paths: list[Path] = []
    for idx, crop_img in enumerate(crops):
        base_label = labels[idx].removesuffix(".png")
        filename = f"{base_label}_{prefix}.png" if prefix else f"{base_label}.png"
        dest = out_dir / filename
        canvas = center_crop_on_canvas(crop_img, target_size=target_size, pad_ratio=pad_ratio)
        canvas.save(dest, format="PNG", optimize=True)
        saved_paths.append(dest)

    return saved_paths
