"""Composite Versus-style images for World Tournament posts."""

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from versusworld import background
from versusworld.config import ASSETS_DIR, temp_dir
from versusworld.logger import get_logger
from versusworld.window import windowize

logger = get_logger(__name__)

TITLE_FONT = str(ASSETS_DIR / "fonts" / "coolvetica rg.otf")
LOGO_PATH = ASSETS_DIR / "versus_logo.png"
REACTIONS_DIR = ASSETS_DIR / "reactions"
GLOBE_BACKGROUND = ASSETS_DIR / "globe_background.png"
GLOBE_OVERLAY = ASSETS_DIR / "globe_overlay.png"

CANVAS_W, CANVAS_H = 1152, 864


def _compose_globe_layers(globe: Image.Image) -> Image.Image:
    """
    Stack transparent PNGs: globe_background → globe → globe_overlay.
    All layers keep alpha; corners stay clear outside the ocean disc.
    """
    w, h = globe.size
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    if GLOBE_BACKGROUND.exists():
        bg = Image.open(GLOBE_BACKGROUND).convert("RGBA")
        bg = bg.resize((w, h), Image.LANCZOS)
        canvas = Image.alpha_composite(canvas, bg)

    canvas = Image.alpha_composite(canvas, globe.convert("RGBA"))

    if GLOBE_OVERLAY.exists():
        overlay = Image.open(GLOBE_OVERLAY).convert("RGBA")
        overlay = overlay.resize((w, h), Image.LANCZOS)
        canvas = Image.alpha_composite(canvas, overlay)

    return canvas


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(TITLE_FONT, size)
    except OSError:
        return ImageFont.load_default()


def _draw_title_bar(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.ImageFont,
    max_lines: int = 3,
) -> int:
    wrapped = textwrap.wrap(text, width=22)
    for line in wrapped[:max_lines]:
        bbox = font.getbbox(line)
        text_width = bbox[2] - bbox[0] + 14
        draw.rectangle(
            (x, y + 2, x + text_width, y + 48), fill=(0, 0, 0, 255), width=2
        )
        draw.multiline_text((x + 8, y), line, font=font, fill=(255, 255, 255))
        y += 48
    return y


def _reaction_image(name: str) -> Image.Image:
    path = REACTIONS_DIR / f"{name}.png"
    if path.exists():
        return Image.open(path).convert("RGBA")
    # Placeholder circle with letter
    img = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, 152, 152), fill=(255, 200, 50, 255), outline=(0, 0, 0, 255), width=3)
    font = _font(48)
    draw.text((60, 50), name[0], font=font, fill=(0, 0, 0, 255))
    return img


def _logo_image() -> Image.Image:
    if LOGO_PATH.exists():
        return Image.open(LOGO_PATH).convert("RGBA")
    img = Image.new("RGBA", (256, 256), (40, 40, 40, 255))
    draw = ImageDraw.Draw(img)
    font = _font(36)
    draw.multiline_text((40, 100), "Versus\nBot", font=font, fill=(255, 255, 255))
    return img


def render_versus(
    globe_path: str | Path,
    name1: str,
    name2: str,
    reaction1: str,
    reaction2: str,
    out_path: str | Path | None = None,
    use_static: bool = False,
    emoji1: str = "",
    emoji2: str = "",
) -> Path:
    """Classic Versus frame with one large center globe window."""
    logger.info("Rendering world versus composite")
    out_path = Path(out_path or (temp_dir() / "versus.png"))

    img = background.generate(CANVAS_W, CANVAS_H, use_static)
    draw = ImageDraw.Draw(img)
    title_font = _font(36)

    # Center globe window: background → globe → overlay, then window chrome
    globe = Image.open(globe_path).convert("RGBA")
    globe = _compose_globe_layers(globe)
    globe_win = windowize(globe, "World Map", (760, 600), menu_bar=True)
    gx = (CANVAS_W - globe_win.width) // 2
    gy = 120
    img.paste(globe_win, (gx, gy), globe_win)

    label1 = name1
    label2 = name2
    _draw_title_bar(draw, label1, 32, 24, title_font)
    _draw_title_bar(draw, label2, 672, 24, title_font)

    # Reactions (larger, bottom corners)
    r1 = windowize(_reaction_image(reaction1), reaction1, (176, 176), 8, False)
    r2 = windowize(_reaction_image(reaction2), reaction2, (176, 176), 8, False)
    img.paste(r1, (40, 620), r1)
    img.paste(r2, (CANVAS_W - r2.width - 40, 620), r2)

    # Logo — slightly smaller, overlaps globe bottom
    logo = windowize(_logo_image(), "VsBot", (128, 128), menu_bar=False)
    img.paste(logo, ((CANVAS_W - logo.width) // 2, 660), logo)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    logger.info("Versus image saved to %s", out_path)
    return out_path


def render_winner(
    winner_id: str,
    name: str,
    votes: int,
    out_path: str | Path | None = None,
    use_static: bool = False,
    countries: list | None = None,
) -> Path:
    """Winner comment image — full map centered on the winner empire."""
    from versusworld.globe import render_globe

    out_path = Path(out_path or (temp_dir() / "winner.png"))
    globe_raw = temp_dir() / "winner_globe.png"
    render_globe(
        winner_id,
        None,
        globe_raw,
        size_px=(640, 640),
        countries=countries,
        mode="winner",
    )

    # Versus-style frame — tall enough that the globe window isn't clipped
    canvas_w, canvas_h = 576, 720
    img = background.generate(canvas_w, canvas_h, use_static)
    draw = ImageDraw.Draw(img)
    title_font = _font(36)

    header = "Last Round Winner"
    _draw_title_bar(draw, header, 24, 16, title_font, max_lines=1)
    _draw_title_bar(draw, name, 24, 64, title_font, max_lines=2)

    globe = Image.open(globe_raw).convert("RGBA")
    globe = _compose_globe_layers(globe)

    # menu_bar window chrome adds +16w / +78h — keep fully inside canvas
    top = 120
    bottom_reserved = 64  # vote label
    max_content = min(
        canvas_w - 48,
        canvas_h - top - bottom_reserved - 78,
    )
    content = max(320, max_content)
    # padding keeps the circular disc inside the content area (not clipped by chrome)
    globe_win = windowize(globe, "World Map", (content, content), padding=20, menu_bar=True)
    gx = (canvas_w - globe_win.width) // 2
    gy = top
    img.paste(globe_win, (gx, gy), globe_win)

    vote_y = min(gy + globe_win.height + 8, canvas_h - 52)
    _draw_title_bar(draw, f"{votes} votes", 24, vote_y, title_font, max_lines=1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    logger.info("Winner image saved to %s", out_path)
    return out_path
