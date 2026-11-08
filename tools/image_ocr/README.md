# Image region OCR

Local CLI and importable async module. Requires Python 3.11+ and `uv`.
Run commands from `tools/image_ocr` inside Citadel:

```powershell
uv sync
uv run image-ocr sample.png --region 10,10,200,60
uv run image-ocr sample.png --region 10,10,200,60 --region 0,70,200,120 --preprocess
uv run image-ocr sample.png
uv run pytest -q -rs
```

From the Citadel root, use `uv run --project tools/image_ocr image-ocr sample.png`.

No regions means the whole image. Repeat `--region` for multiple boxes.
Coordinates are integer pixels, with exclusive right/bottom edges; boxes must
fit inside the image. Output preserves region order:

```json
[{"region": [10, 10, 200, 60], "text": "HELLO", "confidence": 95.5}]
```

Confidence is the arithmetic mean of Tesseract's valid nonempty word scores
(0–100), or `null` when no words are detected. Text preserves detected line
breaks. Invalid files, boxes, and OCR failures produce a clear stderr message
and nonzero exit status. `--preprocess` applies only grayscale and autocontrast.

## Tesseract installation

Tesseract is a separate binary; this tool never installs it. Follow the
[official installation guide](https://tesseract-ocr.github.io/tessdoc/Installation.html)
(including its Windows installer links), install English language data, then
add the executable directory to PATH or set this process environment variable:

```powershell
$env:TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
uv run image-ocr sample.png --region 10,10,200,60
```

`TESSERACT_CMD` takes precedence over PATH. A missing executable produces an
install hint. Tests skip only the real OCR round trip when it is absent.

## Async API

```python
import asyncio
from image_ocr import extract


async def main():
    results, other_results = await asyncio.gather(
        extract("sample.png", [(10, 10, 200, 60)], preprocess=True, concurrency=2),
        extract("other.png"),
    )
    print(results, other_results)


if __name__ == "__main__":
    asyncio.run(main())
```

File decoding, crops, preprocessing, and OCR use `asyncio.to_thread`.
Each extraction decodes once, uses at most `concurrency` workers (default 4),
allocates crops only when workers need them, and waits for workers before
closing images. Each Tesseract call has a 60-second timeout. Limits apply per
`extract` call; callers scheduling many images should also bound image calls.

To swap engines later, pass `engine=` with an object implementing
`OcrEngine.recognize(PIL.Image.Image) -> tuple[str, float | None]`. Engines must
support concurrent calls on separate crops. Only Tesseract is supplied.
Its executable configuration is process-wide; set `TESSERACT_CMD` before use.
