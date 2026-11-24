import io

import pixoo_convert as convert
import pytest
from PIL import Image


def gif(frames: int, duration: int, size=(32, 32)) -> bytes:
    images = [Image.new("RGB", size, (i * 10 % 256, 0, 0)) for i in range(frames)]
    out = io.BytesIO()
    images[0].save(out, format="GIF", save_all=True, append_images=images[1:], duration=duration, loop=0)
    return out.getvalue()


def png(size=(200, 100)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (0, 255, 0)).save(out, format="PNG")
    return out.getvalue()


def strip_size(result: convert.Converted) -> tuple[int, int]:
    return Image.open(io.BytesIO(result.strip)).size


def test_still_has_no_delay_columns():
    result = convert.convert_image(png())
    assert result.frames == 1
    assert result.delay_ms == 0
    assert strip_size(result) == (64, 64)


def test_gif_delay_rides_in_the_width():
    result = convert.convert_image(gif(5, 70))
    assert result.frames == 5
    assert result.delay_ms == 70
    assert strip_size(result) == (64 + 7, 64 * 5)


def test_long_gif_is_thinned_and_keeps_its_length():
    result = convert.convert_image(gif(250, 20))
    # Every third frame of 250 is kept, each shown three times as long.
    assert result.frames == 84
    assert result.delay_ms == 60
    width, height = strip_size(result)
    assert height == 64 * 84
    assert width == 64 + 6


@pytest.mark.parametrize(("durations", "kept", "expected"), [([100], 1, 0), ([5] * 4, 4, 20), ([3000] * 2, 2, 1000)])
def test_frame_delay_limits(durations, kept, expected):
    assert convert.frame_delay(durations, kept) == expected


def test_text_band_height_carries_the_speed():
    result = convert.convert_text("Sveiki, pasaule!", (255, 71, 219))
    width, height = strip_size(result)
    assert height % 64 != 0
    assert (height - 64) * convert.SPEED_UNIT == convert.TEXT_SPEED
    assert width > 2 * 64
    assert result.frames == width - 64 + 1


def test_text_band_never_reads_as_frames():
    result = convert.convert_text("x", (255, 255, 255), speed=128)
    assert strip_size(result)[1] % 64 != 0


def test_latvian_letters_render():
    band = convert.text_band("ĀČĒĢĪĶĻŅŠŪŽ", (255, 255, 255))
    assert band.getbbox() is not None


def test_text_is_cleaned_and_capped():
    assert convert.clean_text("  a \n b  ") == "a b"
    assert len(convert.clean_text("x" * 500)) == convert.TEXT_MAX_CHARS


def test_text_source_round_trip():
    source = convert.text_source("Labrīt <3", (255, 71, 219))
    assert source == "text:ff47db:Labr%C4%ABt%20%3C3"
    assert convert.parse_text_source(source) == ("Labrīt <3", (255, 71, 219))


def test_history_key_is_stable():
    assert convert.history_key("text:ffaa00:Hello") == "0583cb727322"
