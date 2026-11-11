"""KaleidoscopeV2: Headless Google Flow & 5-in-1 Turnaround Synthesis Engine."""

from kaleidoscope.config import Settings, load_settings
from kaleidoscope.crop_engine import PRESET_VIEW_NAMES, slice_turnaround
from kaleidoscope.flow_bot import FlowHeadlessBot
from kaleidoscope.prompts import PRESET_NAMES, build_prompt

__all__ = [
    "FlowHeadlessBot",
    "PRESET_NAMES",
    "PRESET_VIEW_NAMES",
    "Settings",
    "build_prompt",
    "load_settings",
    "slice_turnaround",
]

__version__ = "2.0.0"
