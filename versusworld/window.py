"""Win95-style window chrome (from VersusBot reference)."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from versusworld.config import ASSETS_DIR

TITLE_FONT = str(ASSETS_DIR / "fonts" / "editundo.ttf")
MENU_FONT = str(ASSETS_DIR / "fonts" / "coolvetica rg.otf")

BACKGROUND_COLOR = (204, 204, 204)
BORDER_COLOR = (0, 0, 0)
BUTTON_COLOR = (158, 158, 158)
HIGHLIGHT_COLOR = (248, 248, 248)


def has_transparency(img: Image.Image) -> bool:
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        for pixel in img.getdata():
            if pixel[3] < 255:
                return True
    return False


def tile(width: int, height: int) -> Image.Image:
    background = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(background)
    tile_size = 64
    for y in range(0, height, tile_size):
        for x in range(0, width, tile_size):
            color = (
                (169, 169, 169)
                if (x // tile_size + y // tile_size) % 2 == 0
                else (255, 255, 255)
            )
            draw.rectangle([x, y, x + tile_size, y + tile_size], fill=color)
    return background


def _load_font(path: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def windowize(
    img: Image.Image,
    title: str,
    size: tuple[int, int],
    padding: int = 0,
    menu_bar: bool = True,
) -> Image.Image:
    width, height = size
    window_width = width + 16
    window_height = height + 78 if menu_bar else height + 47
    img_window = Image.new("RGBA", (window_width, window_height), BACKGROUND_COLOR)
    draw_window = ImageDraw.Draw(img_window)

    if has_transparency(img):
        tile_background = tile(width, height)
        img_window.paste(tile_background, (8, 70 if menu_bar else 39), tile_background)
    else:
        draw_window.rectangle(
            (6, 70 if menu_bar else 39, window_width - 7, window_height - 7),
            fill=HIGHLIGHT_COLOR,
            width=2,
        )

    draw_window.rectangle(
        (0, 0, window_width - 1, window_height - 1), outline=BORDER_COLOR, width=2
    )
    draw_window.rectangle(
        (6, 6, window_width - 7, window_height - 7), outline=BORDER_COLOR, width=2
    )
    draw_window.line((2, 2, window_width - 4, 2), fill=HIGHLIGHT_COLOR, width=2)
    draw_window.line((2, 2, 2, window_height - 4), fill=HIGHLIGHT_COLOR, width=2)
    draw_window.line(
        (6, window_height - 6, window_width - 6, window_height - 6),
        fill=HIGHLIGHT_COLOR,
        width=2,
    )
    draw_window.line(
        (window_width - 6, 6, window_width - 6, window_height - 6),
        fill=HIGHLIGHT_COLOR,
        width=2,
    )
    draw_window.rectangle((6, 6, window_width - 7, 32 + 6), outline=BORDER_COLOR, width=2)
    draw_window.line((8, 8, window_width - 9, 8), fill=HIGHLIGHT_COLOR, width=2)
    draw_window.line((8, 8, 8, 36), fill=HIGHLIGHT_COLOR, width=2)
    draw_window.rectangle((6, 6, 32 + 6, 32 + 6), outline=BORDER_COLOR, width=1)
    draw_window.rectangle((12, 18, 34, 26), fill=BORDER_COLOR, width=1)
    draw_window.rectangle((12, 18, 32, 24), fill=BUTTON_COLOR, width=1)
    draw_window.rectangle(
        (window_width - 32 - 7, 6, window_width - 7, 32 + 6), outline=BORDER_COLOR, width=1
    )
    draw_window.rectangle(
        (window_width - 32, 14, window_width - 13, 32), fill=BORDER_COLOR, width=1
    )
    draw_window.rectangle(
        (window_width - 32, 14, window_width - 15, 30), fill=BUTTON_COLOR, width=1
    )

    title_font = _load_font(TITLE_FONT, 20)
    draw_window.multiline_text((46, 14), title, font=title_font, fill=(0, 0, 0, 255))

    if menu_bar:
        draw_window.rectangle(
            (6, 37, window_width - 7, 37 + 32), outline=BORDER_COLOR, width=2
        )
        draw_window.line((8, 39, window_width - 9, 39), fill=HIGHLIGHT_COLOR, width=2)
        draw_window.line((8, 39, 8, 66), fill=HIGHLIGHT_COLOR, width=2)
        menu_font = _load_font(MENU_FONT, 16)
        draw_window.multiline_text(
            (16, 42),
            "File      Edit      Options      Help",
            font=menu_font,
            fill=(0, 0, 0, 255),
        )

    img = img.convert("RGBA")
    img.thumbnail((width, height), Image.LANCZOS)
    final_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    final_img.paste(img, ((width - img.size[0]) // 2, (height - img.size[1]) // 2), img)
    img = final_img

    if padding > 0:
        padded = Image.new("RGBA", (width + padding * 2, height + padding * 2), (0, 0, 0, 0))
        padded.paste(img, (padding, padding), img)
        padded.thumbnail((width, height), Image.LANCZOS)
        img = padded

    img_window.paste(img, (8, 70 if menu_bar else 39), img)
    return img_window
