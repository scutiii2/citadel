"""Local OCR with replaceable synchronous engines and bounded async workers."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
import json
import math
import os
from pathlib import Path
import shutil
from typing import Protocol

from PIL import Image, ImageOps, UnidentifiedImageError
import pytesseract

Region = tuple[int, int, int, int]


class OcrError(RuntimeError):
    """An OCR dependency or recognition operation failed."""


class OcrEngine(Protocol):
    """Engines must support concurrent calls with independent crop images."""

    def recognize(self, image: Image.Image) -> tuple[str, float | None]:
        """Return recognized text and mean word confidence on a 0–100 scale."""
        ...


def find_tesseract() -> str:
    """Resolve the explicit executable override first, then PATH."""
    command = os.environ.get("TESSERACT_CMD") or "tesseract"
    executable = shutil.which(command)
    if executable is None:
        raise OcrError(
            "Tesseract executable not found. Install Tesseract OCR separately "
            "(Windows: https://tesseract-ocr.github.io/tessdoc/Installation.html), "
            "then add it to PATH or set TESSERACT_CMD to its full executable path."
        )
    return executable


class TesseractEngine:
    """Use Tesseract TSV word rows for both text and confidence."""

    def __init__(self) -> None:
        # All instances share the process-wide environment-selected executable.
        pytesseract.pytesseract.tesseract_cmd = find_tesseract()

    def recognize(self, image: Image.Image) -> tuple[str, float | None]:
        try:
            data = pytesseract.image_to_data(
                image, output_type=pytesseract.Output.DICT, timeout=60
            )
        except (OSError, RuntimeError) as error:
            raise OcrError(f"Tesseract OCR failed: {error}") from error
        lines: list[str] = []
        words: list[str] = []
        scores: list[float] = []
        previous_line = None
        for index, value in enumerate(data["text"]):
            text = value.strip()
            score = float(data["conf"][index])
            if (data["level"][index] != 5 or not text
                    or not math.isfinite(score) or not 0 <= score <= 100):
                continue
            line = tuple(data[key][index] for key in ("block_num", "par_num", "line_num"))
            if previous_line is not None and line != previous_line:
                lines.append(" ".join(words))
                words = []
            words.append(text)
            scores.append(score)
            previous_line = line
        if words:
            lines.append(" ".join(words))
        return "\n".join(lines), sum(scores) / len(scores) if scores else None


def _load_image(image: str | Path, regions: Sequence[Region] | None):
    """Decode once and validate every box before any OCR begins."""
    path = Path(image)
    if not path.is_file():
        raise ValueError(f"Image file does not exist or is not a regular file: {path}")
    try:
        with Image.open(path) as source:
            width, height = source.size
            selected = list(regions) if regions else [(0, 0, width, height)]
            boxes: list[Region] = []
            for region in selected:
                if (not isinstance(region, (tuple, list)) or len(region) != 4
                        or any(type(value) is not int for value in region)):
                    raise ValueError(f"Invalid region {region!r}: expected four integer pixel coordinates")
                x0, y0, x1, y1 = region
                if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
                    raise ValueError(
                        f"Invalid region {region!r} for image {width}x{height}: "
                        "require 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height"
                    )
                boxes.append((x0, y0, x1, y1))
            return source.copy(), boxes
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError(f"Cannot read image file {path}: {error}") from error


async def _in_thread(function, *args):
    """Drain in-flight work on cancellation before its image can be closed."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task, return_exceptions=True)
        raise


async def extract(
    image: str | Path,
    regions: Sequence[Region] | None = None,
    *,
    engine: OcrEngine | None = None,
    preprocess: bool = False,
    concurrency: int = 4,
) -> list[dict[str, object]]:
    """OCR pixel boxes in input order; omitted or empty boxes mean whole image.

    File decoding, cropping, preprocessing, and OCR run outside the event loop.
    The concurrency limit applies per extraction call, including crop allocation.
    """
    if type(concurrency) is not int or concurrency < 1:
        raise ValueError("concurrency must be a positive integer")
    source, boxes = await _in_thread(_load_image, image, regions)
    try:
        selected_engine = engine if engine is not None else await _in_thread(TesseractEngine)
        results: list[dict[str, object]] = [{} for _ in boxes]
        pending = iter(enumerate(boxes))

        def recognize(region: Region) -> dict[str, object]:
            with source.crop(region) as crop:
                if preprocess:
                    with ImageOps.grayscale(crop) as gray:
                        with ImageOps.autocontrast(gray) as prepared:
                            text, confidence = selected_engine.recognize(prepared)
                else:
                    text, confidence = selected_engine.recognize(crop)
            return {"region": list(region), "text": text, "confidence": confidence}

        async def worker() -> None:
            # Iterator access stays on the event loop, before the next await.
            for index, region in pending:
                results[index] = await _in_thread(recognize, region)

        workers = [asyncio.create_task(worker()) for _ in range(min(concurrency, len(boxes)))]
        try:
            await asyncio.gather(*workers)
        finally:
            # Other workers may still own crops after one worker fails.
            await asyncio.gather(*workers, return_exceptions=True)
        return results
    finally:
        source.close()


def _parse_region(value: str) -> Region:
    try:
        parts = tuple(int(part) for part in value.split(","))
        if len(parts) != 4:
            raise ValueError
        return parts
    except ValueError as error:
        raise argparse.ArgumentTypeError("region must be x0,y0,x1,y1 using integer pixels") from error


def main() -> None:
    """Run the command line boundary; successful stdout contains only JSON."""
    parser = argparse.ArgumentParser(description="Extract text from image pixel regions.")
    parser.add_argument("image", type=Path)
    parser.add_argument("--region", action="append", type=_parse_region, dest="regions")
    parser.add_argument("--preprocess", action="store_true", help="grayscale and autocontrast")
    parser.add_argument("--concurrency", type=int, default=4, help="maximum parallel regions (default: 4)")
    args = parser.parse_args()
    try:
        results = asyncio.run(extract(
            args.image, args.regions, preprocess=args.preprocess, concurrency=args.concurrency
        ))
    except (ValueError, OcrError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(results, ensure_ascii=False, allow_nan=False))
