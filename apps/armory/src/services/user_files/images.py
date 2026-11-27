"""Image checks and the downscaled copy a model is shown. Blocking."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from src.services.file_errors import ErrorCode, FileError

register_heif_opener()
# Our own pixel limit (with a clear message) replaces Pillow's DecompressionBombError.
Image.MAX_IMAGE_PIXELS = None

IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/webp", "image/tiff", "image/gif", "image/heic"})

# What a model gets: more pixels than this are scaled down by the provider anyway.
VIEW_MAX_EDGE = 1568
# Above this a PNG goes out as JPEG; providers refuse images of a few megabytes.
VIEW_MAX_PNG_BYTES = 3 * 1024 * 1024


def flatten(image: Image.Image) -> Image.Image:
    has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
    if has_alpha:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image if image.mode in ("RGB", "L") else image.convert("RGB")


def check_image(path: Path, max_pixels: int) -> None:
    """Refuse a damaged or oversized image. Blocking."""
    try:
        with Image.open(path) as image:
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as error:
        raise FileError(ErrorCode.CORRUPT_FILE, "This image is damaged and can't be read.") from error
    if width * height > max_pixels:
        raise FileError(
            ErrorCode.LIMIT_EXCEEDED,
            f"This image is {width * height / 1e6:.1f} megapixels; the limit is {max_pixels / 1e6:g}. Resize it, then upload it again.",
        )


def view_image(path: Path) -> tuple[bytes, str]:
    """An upright, flattened, downscaled copy of a stored image, as (bytes, media type). Blocking."""
    try:
        with Image.open(path) as image:
            image.seek(0)
            picture = flatten(ImageOps.exif_transpose(image))
            picture.thumbnail((VIEW_MAX_EDGE, VIEW_MAX_EDGE))
            buffer = io.BytesIO()
            picture.save(buffer, format="PNG")
            if buffer.tell() <= VIEW_MAX_PNG_BYTES:
                return buffer.getvalue(), "image/png"
            buffer = io.BytesIO()
            picture.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue(), "image/jpeg"
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise FileError(ErrorCode.CORRUPT_FILE, "This image is damaged and can't be read.") from error
