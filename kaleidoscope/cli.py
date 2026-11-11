"""Unified CLI for KaleidoscopeV2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from kaleidoscope.config import load_settings
from kaleidoscope.crop_engine import slice_turnaround
from kaleidoscope.flow_bot import FlowHeadlessBot
from kaleidoscope.prompts import PRESET_NAMES, build_prompt
from kaleidoscope.setup_session import run_session_setup


def _create_mock_turnaround(dest_path: Path, width: int = 1920, height: int = 1080) -> Path:
    """Create a synthetic 5-view 16:9 turnaround sheet for offline smoke testing."""
    import cv2
    import numpy as np

    img = np.full((height, width, 3), 255, dtype=np.uint8)
    col_w = width // 5
    colors = [(40, 40, 180), (180, 50, 40), (30, 150, 40), (160, 40, 160), (40, 150, 180)]
    for i, col in enumerate(colors):
        cx = i * col_w + col_w // 2
        hy = int(height * 0.28)
        cv2.circle(img, (cx, hy), 45, col, -1)
        cv2.rectangle(img, (cx - 45, hy + 55), (cx + 45, hy + 295), col, -1)
        cv2.rectangle(img, (cx - 45, hy + 295), (cx - 13, hy + 545), col, -1)
        cv2.rectangle(img, (cx + 13, hy + 295), (cx + 45, hy + 545), col, -1)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest_path), img)
    return dest_path


def _cmd_auth(args: argparse.Namespace) -> int:
    settings = load_settings(env_file=args.env_file)
    ok = run_session_setup(settings=settings, check_only=args.check)
    return 0 if ok else 1


def _cmd_slice(args: argparse.Namespace) -> int:
    settings = load_settings(env_file=args.env_file)
    views = slice_turnaround(
        image_path=args.input,
        output_dir=args.output_dir,
        prefix=args.prefix,
        preset=args.preset,
        target_size=args.size or settings.view_size,
        pad_ratio=args.padding if args.padding is not None else settings.pad_ratio,
        mode=args.mode,
    )
    print(f"Sliced {len(views)} views to {Path(args.output_dir).resolve()}:")
    for v in views:
        print(f"  -> {v.name}")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    settings = load_settings(env_file=args.env_file)
    if args.mock:
        out_dir = Path(args.output_dir) if args.output_dir else settings.output_dir
        target_dir = out_dir / f"{args.name}_inputs"
        comp = _create_mock_turnaround(target_dir / f"{args.name}_composite.png")
        prompt_preview = build_prompt(args.prompt, preset=args.preset, has_reference_image=bool(args.ref_image))
        print(f"[MOCK] Generated synthetic composite: {comp}")
        print(f"[MOCK] Prompt preview: {prompt_preview}")
        if args.preset != "concept":
            views = slice_turnaround(
                image_path=comp,
                output_dir=target_dir,
                prefix=args.name,
                preset=args.preset,
                target_size=settings.view_size,
                pad_ratio=settings.pad_ratio,
                mode=args.slice_mode,
            )
            print(f"[MOCK] Sliced {len(views)} views:")
            for v in views:
                print(f"  -> {v}")
        return 0

    with FlowHeadlessBot(settings=settings, headless=False if args.headed else None) as bot:
        bot.navigate()
        bot.verify_authenticated()
        res = bot.generate_asset(
            name=args.name,
            prompt=args.prompt,
            preset=args.preset,
            ref_image=args.ref_image,
            aspect_ratio=args.ratio,
            slice_mode=args.slice_mode,
            output_dir=args.output_dir,
        )
        print(f"Composite saved: {res['composite']}")
        for v in res["views"]:
            print(f"  -> {v}")
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    settings = load_settings(env_file=args.env_file)
    tasks: list[dict[str, Any]] = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Batch config JSON must be a non-empty list of task objects.")

    with FlowHeadlessBot(settings=settings, headless=False if args.headed else None) as bot:
        bot.navigate()
        bot.verify_authenticated()
        for idx, task in enumerate(tasks, start=1):
            print(f"\n[{idx}/{len(tasks)}] Running asset: {task['name']}")
            res = bot.generate_asset(
                name=task["name"],
                prompt=task["prompt"],
                preset=task.get("preset", "character"),
                ref_image=task.get("ref_image"),
                aspect_ratio=task.get("ratio", "16:9"),
                slice_mode=task.get("slice_mode", "auto"),
                output_dir=args.output_dir,
            )
            print(f"  Saved composite: {res['composite']} ({len(res['views'])} sliced views)")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    settings = load_settings(env_file=args.env_file)
    with FlowHeadlessBot(settings=settings, headless=False if args.headed else None) as bot:
        bot.navigate()
        data = bot.inspect_dom()
        print(json.dumps(data, indent=2))
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="kaleidoscope",
        description="KaleidoscopeV2: Headless Google Flow & 5-in-1 Turnaround Synthesis CLI",
    )
    parser.add_argument("--env-file", default=None, help="Optional path to custom .env file")
    sub = parser.add_subparsers(dest="command", required=True)

    p_auth = sub.add_parser("auth", help="Initialize or verify persistent Google Flow login")
    p_auth.add_argument("--check", action="store_true", help="Headless check of active auth session")
    p_auth.set_defaults(func=_cmd_auth)

    p_slice = sub.add_parser("slice", help="Slice an existing 16:9 turnaround sheet into 5 1:1 views")
    p_slice.add_argument("--input", required=True, help="Input turnaround image path")
    p_slice.add_argument("--output-dir", required=True, help="Output folder for 1:1 PNG views")
    p_slice.add_argument("--prefix", default=None, help="Optional asset filename suffix")
    p_slice.add_argument("--preset", choices=["character", "weapon", "prop_topbottom"], default="character")
    p_slice.add_argument("--mode", choices=["auto", "contour", "projection"], default="auto")
    p_slice.add_argument("--size", type=int, default=None, help="Square canvas dimension (default 1024)")
    p_slice.add_argument("--padding", type=float, default=None, help="Padding ratio (default 0.08)")
    p_slice.set_defaults(func=_cmd_slice)

    p_gen = sub.add_parser("generate", help="Generate via Google Flow and auto-slice 5 views")
    p_gen.add_argument("--name", required=True, help="Asset slug (creates outputs/<name>_inputs/)")
    p_gen.add_argument("--prompt", required=True, help="Asset description or full turnaround prompt")
    p_gen.add_argument("--preset", choices=list(PRESET_NAMES), default="character")
    p_gen.add_argument("--ref-image", default=None, help="Optional reference image to lock identity")
    p_gen.add_argument("--ratio", default="16:9", help="Aspect ratio (default 16:9)")
    p_gen.add_argument("--slice-mode", choices=["auto", "contour", "projection"], default="auto")
    p_gen.add_argument("--output-dir", default=None, help="Override base output directory")
    p_gen.add_argument("--mock", action="store_true", help="Offline smoke test using synthetic composite")
    p_gen.add_argument("--headed", action="store_true", help="Run visible browser instead of headless")
    p_gen.set_defaults(func=_cmd_generate)

    p_batch = sub.add_parser("batch", help="Generate multiple assets in one headless Flow session")
    p_batch.add_argument("--config", required=True, help="Path to JSON list of task definitions")
    p_batch.add_argument("--output-dir", default=None, help="Override base output directory")
    p_batch.add_argument("--headed", action="store_true", help="Run visible browser instead of headless")
    p_batch.set_defaults(func=_cmd_batch)

    p_insp = sub.add_parser("inspect", help="Dump live Google Flow DOM selectors for debugging")
    p_insp.add_argument("--headed", action="store_true", help="Run visible browser")
    p_insp.set_defaults(func=_cmd_inspect)

    args = parser.parse_args(argv)
    try:
        code = args.func(args)
        sys.exit(code)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
