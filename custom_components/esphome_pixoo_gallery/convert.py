"""Turn pictures, GIFs and text into the strips the Pixoo 64 firmware plays.

Pure Pillow code with no Home Assistant imports, so it runs in the executor and in tests.

Two strip layouts, told apart by the firmware from the image size alone:

- Frames: 64x64 frames stacked vertically. Every column past the 64 shown stands for
  10 ms of frame delay.
- Band (text): one row of text with a screen's width of blank on both sides. Its height
  isn't a multiple of 64; every row past the 64 shown stands for 2 px/s of scroll speed.
"""

from __future__ import annotations

import hashlib
import io
import math
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence

SIZE = 64
MAX_FRAMES = 100
DELAY_UNIT_MS = 10
MIN_DELAY_MS = 20
MAX_DELAY_MS = 1000
DEFAULT_FRAME_MS = 100
PREVIEW_SCALE = 4
TEXT_SIZE = 36
TEXT_MAX_CHARS = 120
TEXT_SPEED = 76  # px per second
SPEED_UNIT = 2  # px per second per extra row
PREVIEW_STEP_PX = 4
FONT_PATH = Path(__file__).parent / "fonts" / "DejaVuSans-Bold.ttf"


@dataclass
class Converted:
    """What one conversion produces."""

    strip: bytes  # PNG the display downloads
    preview: bytes  # GIF for the dashboard
    thumb: bytes  # GIF for the history list
    frames: int
    delay_ms: int


def history_key(source: str) -> str:
    """Stable key for a source, used to name its history entry."""
    return hashlib.sha1(source.encode()).hexdigest()[:12]


def text_source(text: str, rgb: tuple[int, int, int]) -> str:
    """Encode a text and its colour as a history source: text:RRGGBB:<urlencoded>."""
    return "text:{:02x}{:02x}{:02x}:".format(*rgb) + urllib.parse.quote(text, safe="")


def parse_text_source(source: str) -> tuple[str, tuple[int, int, int]]:
    _, color, encoded = source.split(":", 2)
    rgb = tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))
    return urllib.parse.unquote(encoded), rgb


def clean_text(text: str) -> str:
    return " ".join(text.split())[:TEXT_MAX_CHARS]


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _gif(frames: list[Image.Image], delay_ms: int) -> bytes:
    out = io.BytesIO()
    frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=delay_ms or 1000,
        loop=0,
    )
    return out.getvalue()


def _fit(frame: Image.Image) -> Image.Image:
    frame = frame.convert("RGBA")
    small = frame.width <= SIZE and frame.height <= SIZE
    frame = ImageOps.contain(frame, (SIZE, SIZE), Image.NEAREST if small else Image.LANCZOS)
    canvas = Image.new("RGB", (SIZE, SIZE))
    canvas.paste(frame, ((SIZE - frame.width) // 2, (SIZE - frame.height) // 2), frame)
    return canvas


def frame_delay(durations: list[int], kept: int) -> int:
    """Delay per kept frame, so the whole animation keeps its length; 0 for a still."""
    if kept <= 1:
        return 0
    per_frame = sum(durations) / kept
    rounded = round(per_frame / DELAY_UNIT_MS) * DELAY_UNIT_MS
    return max(MIN_DELAY_MS, min(MAX_DELAY_MS, rounded))


def convert_image(data: bytes) -> Converted:
    """Scale every frame to 64x64, keep at most 100, and stack them into a strip."""
    image = Image.open(io.BytesIO(data))
    frames, durations = [], []
    for frame in ImageSequence.Iterator(image):
        frames.append(_fit(frame))
        durations.append(frame.info.get("duration") or DEFAULT_FRAME_MS)

    step = math.ceil(len(frames) / MAX_FRAMES)
    kept = frames[::step]
    delay_ms = frame_delay(durations, len(kept))

    strip = Image.new("RGB", (SIZE + delay_ms // DELAY_UNIT_MS, SIZE * len(kept)))
    for i, frame in enumerate(kept):
        strip.paste(frame, (0, SIZE * i))

    preview = [f.resize((SIZE * PREVIEW_SCALE,) * 2, Image.NEAREST) for f in kept]
    return Converted(
        strip=_png(strip),
        preview=_gif(preview, delay_ms),
        thumb=_gif(kept, delay_ms),
        frames=len(kept),
        delay_ms=delay_ms,
    )


def text_band(text: str, rgb: tuple[int, int, int], font_path: Path = FONT_PATH) -> Image.Image:
    """The text on one band, blank for a screen's width on both sides."""
    text = clean_text(text) or " "
    font = ImageFont.truetype(str(font_path), TEXT_SIZE)
    left, _, right, _ = font.getbbox(text)
    # Same baseline for every text, with room for accents and descenders.
    _, top, _, bottom = font.getbbox("ĀĶŠgjy")
    band = Image.new("RGB", (SIZE + (right - left) + SIZE, SIZE))
    draw = ImageDraw.Draw(band)
    draw.fontmode = "1"  # crisp pixels, no anti-aliasing
    draw.text((SIZE - left, (SIZE - (bottom - top)) // 2 - top), text, font=font, fill=rgb)
    return band


def convert_text(
    text: str,
    rgb: tuple[int, int, int],
    speed: int = TEXT_SPEED,
    font_path: Path = FONT_PATH,
) -> Converted:
    """Render a text as one band that the display scrolls right to left."""
    band = text_band(text, rgb, font_path)
    rows = max(1, speed // SPEED_UNIT)
    if (SIZE + rows) % SIZE == 0:
        rows += 1  # a multiple of 64 would read as a frame strip
    strip = Image.new("RGB", (band.width, SIZE + rows))
    strip.paste(band, (0, 0))

    # The dashboard preview skips pixels to stay small.
    frames = [band.crop((x, 0, x + SIZE, SIZE)) for x in range(0, band.width - SIZE + 1, PREVIEW_STEP_PX)]
    preview_ms = round(1000 * PREVIEW_STEP_PX / (rows * SPEED_UNIT))
    preview = _gif(frames, preview_ms)
    return Converted(
        strip=_png(strip),
        preview=preview,
        thumb=preview,
        frames=band.width - SIZE + 1,
        delay_ms=round(1000 / (rows * SPEED_UNIT)),
    )
