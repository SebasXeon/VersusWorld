"""Versus-style background generation."""

from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageChops

from versusworld.config import ASSETS_DIR, DATA_DIR

BACKGROUNDS_PATH = ASSETS_DIR / "backgrounds"
GENERATED_BACKGROUNDS_PATH = ASSETS_DIR / "generated_backgrounds"
COLORS_PATH = DATA_DIR / "colors.json"


def _load_colors() -> list[list[int]]:
    if COLORS_PATH.exists():
        with open(COLORS_PATH, encoding="utf-8") as f:
            return json.load(f)["colors"]
    return [[52, 143, 235], [235, 79, 52], [232, 170, 20], [0, 206, 203]]


def generate(width: int, height: int, use_static: bool = False) -> Image.Image:
    if use_static and GENERATED_BACKGROUNDS_PATH.is_dir():
        files = [f for f in GENERATED_BACKGROUNDS_PATH.iterdir() if f.suffix == ".png"]
        if files:
            return Image.open(random.choice(files)).convert("RGBA")

    color = random.choice(_load_colors())
    img = Image.new("RGBA", (width, height), (color[0], color[1], color[2]))

    if BACKGROUNDS_PATH.is_dir():
        files = list(BACKGROUNDS_PATH.iterdir())
        if files:
            overlay = Image.open(random.choice(files)).convert("RGBA")
            overlay = overlay.resize((width, height), Image.LANCZOS)
            img = ImageChops.multiply(img, overlay)
            return img

    # Fallback: soft noise-less solid with subtle gradient-like second pass
    return img
