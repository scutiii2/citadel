"""Exercise public boundaries, image pixels, worker limits, and real OCR."""

import asyncio
import json
import threading
import time

import pytest
from PIL import Image, ImageDraw, ImageFont

from image_ocr import OcrError, TesseractEngine, extract, find_tesseract, main


def test_boundary_validation(tmp_path):
    path = tmp_path / "image.png"
    Image.new("RGB", (20, 10), "white").save(path)
    for box in [(-1, 0, 5, 5), (0, 0, 21, 5), (0, 0, 5, 11),
                (5, 0, 5, 5), (0, 5, 5, 4), (0, 0, 1.5, 5), (0, 0, 5)]:
        with pytest.raises(ValueError, match="region"):
            asyncio.run(extract(path, [box]))
    with pytest.raises(ValueError, match="file"):
        asyncio.run(extract(tmp_path / "missing.png"))
    with pytest.raises(ValueError, match="concurrency"):
        asyncio.run(extract(path, concurrency=0))


def test_exact_crops_and_bounded_threads(tmp_path):
    path = tmp_path / "colors.png"
    image = Image.new("RGB", (20, 10), "red")
    image.paste("blue", (10, 0, 20, 10))
    image.save(path)
    main_thread = threading.get_ident()

    class PixelEngine:
        def __init__(self):
            self.active = 0
            self.peak = 0
            self.lock = threading.Lock()

        def recognize(self, crop):
            assert threading.get_ident() != main_thread
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                time.sleep(0.02)
                assert crop.size == (10, 10)
                assert len(crop.getcolors()) == 1
                return str(crop.getpixel((0, 0))), 90.0
            finally:
                with self.lock:
                    self.active -= 1

    engine = PixelEngine()
    boxes = [(0, 0, 10, 10), (10, 0, 20, 10)] * 4
    result = asyncio.run(extract(path, boxes, engine=engine, concurrency=2))
    assert engine.peak == 2
    assert [row["region"] for row in result] == [list(box) for box in boxes]
    assert [row["text"] for row in result] == ["(255, 0, 0)", "(0, 0, 255)"] * 4


def test_word_confidence_and_preprocessing(tmp_path, monkeypatch, capsys):
    import pytesseract

    path = tmp_path / "gray.png"
    Image.new("RGB", (20, 10), (80, 80, 80)).save(path)
    monkeypatch.setattr("image_ocr.find_tesseract", lambda: "tesseract")
    data = {"level": [4, 5, 5, 5, 5], "text": ["", "Hello", "world", "", "bad"],
            "conf": [-1, 80.5, 99.5, 50, -1],
            "block_num": [1] * 5, "par_num": [1] * 5, "line_num": [1] * 5}

    def recognize(crop, **kwargs):
        assert crop.mode == "L"
        return data

    monkeypatch.setattr(pytesseract, "image_to_data", recognize)
    result = asyncio.run(extract(path, preprocess=True))
    assert result == [{"region": [0, 0, 20, 10], "text": "Hello world", "confidence": 90.0}]
    monkeypatch.setattr("sys.argv", ["image-ocr", str(path), "--region", "0,0,10,10", "--preprocess"])
    main()
    assert json.loads(capsys.readouterr().out) == [
        {"region": [0, 0, 10, 10], "text": "Hello world", "confidence": 90.0}
    ]
    data["text"] = [""] * 5
    assert asyncio.run(extract(path, preprocess=True))[0]["confidence"] is None


def test_ocr_round_trip(tmp_path):
    try:
        find_tesseract()
    except OcrError as error:
        pytest.skip(str(error))
    path = tmp_path / "sample.png"
    image = Image.new("RGB", (600, 120), "white")
    ImageDraw.Draw(image).text((20, 20), "HELLO 123", fill="black",
                               font=ImageFont.load_default(size=48))
    image.save(path)
    result = asyncio.run(extract(path, engine=TesseractEngine()))
    assert result[0]["text"].strip() == "HELLO 123"
    assert 0 <= result[0]["confidence"] <= 100
