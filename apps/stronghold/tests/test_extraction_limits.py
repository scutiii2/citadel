"""Limits of text extraction: zip bombs, page and row caps, truncation."""

from __future__ import annotations

import io
import zipfile

import pytest

from src.attachments import extraction as text_extraction
from src.attachments.extraction import ExtractionError, extract_text

MB = 1024 * 1024


def zip_with(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class TestAttachmentLimits:
    @pytest.mark.parametrize("name", ["bomb.docx", "bomb.xlsx", "bomb.xlsm"])
    def test_a_zip_that_expands_too_far_is_refused(self, name: str) -> None:
        bomb = zip_with({"word/document.xml": b"\0" * (120 * MB)})
        assert len(bomb) < 1 * MB

        with pytest.raises(ExtractionError, match="far larger than it looks"):
            extract_text(name, bomb)

    def test_the_size_limit_counts_every_entry(self) -> None:
        many = zip_with({f"part{i}.xml": b"\0" * (30 * MB) for i in range(4)})

        with pytest.raises(ExtractionError, match="far larger"):
            extract_text("x.docx", many)

    def test_an_archive_just_under_the_limit_is_opened(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(text_extraction, "MAX_UNZIPPED_BYTES", 5000)
        archive = zip_with({"a.xml": b"\0" * 4999})

        # Not refused as a bomb; the library then says it is no Word file.
        with pytest.raises(ExtractionError, match="Could not read this Word document"):
            extract_text("x.docx", archive)

    def test_an_archive_at_the_limit_plus_one_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(text_extraction, "MAX_UNZIPPED_BYTES", 5000)

        with pytest.raises(ExtractionError, match="far larger"):
            extract_text("x.docx", zip_with({"a.xml": b"\0" * 5001}))

    def test_too_many_entries_are_refused(self) -> None:
        crowded = zip_with({f"f{i}.txt": b"" for i in range(text_extraction.MAX_ZIP_ENTRIES + 1)})

        with pytest.raises(ExtractionError, match="far larger"):
            extract_text("x.xlsx", crowded)

    def test_the_real_limits_are_the_documented_ones(self) -> None:
        assert text_extraction.MAX_UNZIPPED_BYTES == 100 * MB
        assert text_extraction.MAX_ZIP_ENTRIES == 5_000
        assert text_extraction.MAX_PDF_PAGES == 500
        assert text_extraction.MAX_SHEET_ROWS == 200_000

    def test_five_thousand_entries_are_allowed_and_one_more_is_not(self) -> None:
        five_thousand = zip_with({f"f{i}.txt": b"" for i in range(5_000)})
        one_more = zip_with({f"f{i}.txt": b"" for i in range(5_001)})

        with pytest.raises(ExtractionError, match="Could not read"):  # not refused as a bomb
            extract_text("x.xlsx", five_thousand)
        with pytest.raises(ExtractionError, match="far larger"):
            extract_text("x.xlsx", one_more)

    def test_an_archive_of_exactly_the_size_limit_is_opened(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(text_extraction, "MAX_UNZIPPED_BYTES", 5000)

        with pytest.raises(ExtractionError, match="Could not read this Word document"):
            extract_text("x.docx", zip_with({"a.xml": b"\0" * 5000}))

    def test_the_entry_limit_itself_is_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(text_extraction, "MAX_ZIP_ENTRIES", 3)
        three = zip_with({f"f{i}.txt": b"" for i in range(3)})

        with pytest.raises(ExtractionError, match="Could not read"):
            extract_text("x.xlsx", three)

    def test_a_file_that_is_not_a_zip_gets_the_librarys_message(self) -> None:
        with pytest.raises(ExtractionError, match="Could not read this Word document"):
            extract_text("x.docx", b"not a zip at all")

    def test_a_real_word_file_still_reads(self) -> None:
        from docx import Document

        document = Document()
        document.add_paragraph("Hello there")
        buffer = io.BytesIO()
        document.save(buffer)

        assert extract_text("a.docx", buffer.getvalue()).text == "Hello there"

    def test_a_pdf_is_read_page_by_page_and_stops_when_it_has_enough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import pypdf

        read: list[int] = []

        class Page:
            def __init__(self, number: int) -> None:
                self.number = number

            def extract_text(self) -> str:
                read.append(self.number)
                return "x" * 6000

        class Reader:
            def __init__(self, _stream) -> None:
                self.pages = [Page(i) for i in range(50)]

        monkeypatch.setattr(pypdf, "PdfReader", Reader)

        result = extract_text("a.pdf", b"%PDF")

        assert result.truncated and result.char_count == text_extraction.MAX_TEXT_CHARS
        assert read == [0, 1, 2, 3]  # 4 x 6000 characters pass 20,000

    def test_text_that_exactly_fills_the_attachment_ends_the_reading(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import pypdf

        read: list[int] = []

        class Page:
            def __init__(self, number: int) -> None:
                self.number = number

            def extract_text(self) -> str:
                read.append(self.number)
                return "x" * text_extraction.MAX_TEXT_CHARS

        class Reader:
            def __init__(self, _stream) -> None:
                self.pages = [Page(i) for i in range(5)]

        monkeypatch.setattr(pypdf, "PdfReader", Reader)

        extract_text("a.pdf", b"%PDF")

        assert read == [0]

    def test_a_pdf_of_endless_empty_pages_stops_at_exactly_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import pypdf

        read: list[int] = []

        class Page:
            def extract_text(self) -> str:
                read.append(1)
                return ""

        class Reader:
            def __init__(self, _stream) -> None:
                self.pages = [Page() for _ in range(600)]

        monkeypatch.setattr(pypdf, "PdfReader", Reader)

        with pytest.raises(ExtractionError, match="No readable text"):
            extract_text("a.pdf", b"%PDF")

        assert len(read) == 500

    def test_a_sheet_of_empty_rows_stops_at_exactly_two_hundred_thousand(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import openpyxl

        asked: list[int] = []

        class Sheet:
            title = "S"

            def iter_rows(self, values_only: bool):
                for i in range(250_000):
                    asked.append(i)
                    yield (None,)

        class Book:
            sheetnames = ["S"]
            worksheets = [Sheet()]

            def close(self) -> None:
                pass

        monkeypatch.setattr(text_extraction, "_refuse_zip_bomb", lambda _content: None)
        monkeypatch.setattr(openpyxl, "load_workbook", lambda *args, **kwargs: Book())

        with pytest.raises(ExtractionError, match="No readable text"):
            extract_text("a.xlsx", b"x")

        assert len(asked) == 200_001  # 200,000 rows read, then the next one is asked for and the loop stops

    def test_a_pdf_with_endless_empty_pages_stops_at_the_page_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import pypdf

        read: list[int] = []

        class Page:
            def extract_text(self) -> str:
                read.append(1)
                return ""

        class Reader:
            def __init__(self, _stream) -> None:
                self.pages = [Page() for _ in range(text_extraction.MAX_PDF_PAGES + 100)]

        monkeypatch.setattr(pypdf, "PdfReader", Reader)

        with pytest.raises(ExtractionError, match="No readable text"):
            extract_text("a.pdf", b"%PDF")

        assert len(read) == text_extraction.MAX_PDF_PAGES

    def test_a_pdf_with_a_broken_page_keeps_the_rest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import pypdf

        class Broken:
            def extract_text(self) -> str:
                raise ValueError("bad page")

        class Fine:
            def extract_text(self) -> str:
                return "kept"

        class Reader:
            def __init__(self, _stream) -> None:
                self.pages = [Broken(), Fine()]

        monkeypatch.setattr(pypdf, "PdfReader", Reader)

        assert extract_text("a.pdf", b"%PDF").text == "kept"

    def test_a_sheet_is_read_row_by_row_and_stops_when_it_has_enough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import openpyxl

        scanned: list[int] = []

        class Sheet:
            title = "S"

            def iter_rows(self, values_only: bool):
                for i in range(10_000):
                    scanned.append(i)
                    yield ("y" * 5000,)

        class Book:
            sheetnames = ["S"]
            worksheets = [Sheet()]

            def close(self) -> None:
                pass

        monkeypatch.setattr(text_extraction, "_refuse_zip_bomb", lambda _content: None)
        monkeypatch.setattr(openpyxl, "load_workbook", lambda *args, **kwargs: Book())

        result = extract_text("a.xlsx", b"x")

        assert result.truncated
        assert len(scanned) <= 6  # 4 rows reach 20,000 characters; the generator is asked for the next one

    def test_a_sheet_of_empty_rows_stops_at_the_row_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import openpyxl

        asked: list[int] = []

        class Sheet:
            title = "S"

            def iter_rows(self, values_only: bool):
                for i in range(50):
                    asked.append(i)
                    yield (None,)

        class Book:
            sheetnames = ["S"]
            worksheets = [Sheet()]

            def close(self) -> None:
                pass

        monkeypatch.setattr(text_extraction, "_refuse_zip_bomb", lambda _content: None)
        monkeypatch.setattr(text_extraction, "MAX_SHEET_ROWS", 7)
        monkeypatch.setattr(openpyxl, "load_workbook", lambda *args, **kwargs: Book())

        with pytest.raises(ExtractionError, match="No readable text"):
            extract_text("a.xlsx", b"x")

        assert len(asked) == 8  # rows 0 to 6 are read, the generator is asked for row 7 and the loop stops

    def test_a_second_sheet_is_skipped_once_the_first_filled_the_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import openpyxl

        touched: list[str] = []

        class Sheet:
            def __init__(self, title: str, cell: str) -> None:
                self.title = title
                self.cell = cell

            def iter_rows(self, values_only: bool):
                touched.append(self.title)
                yield (self.cell,)

        class Book:
            sheetnames = ["A", "B"]
            worksheets = [Sheet("A", "a" * 25_000), Sheet("B", "b")]

            def close(self) -> None:
                pass

        monkeypatch.setattr(text_extraction, "_refuse_zip_bomb", lambda _content: None)
        monkeypatch.setattr(openpyxl, "load_workbook", lambda *args, **kwargs: Book())

        extract_text("a.xlsx", b"x")

        assert touched == ["A"]

    def test_a_word_file_stops_reading_paragraphs_once_it_has_enough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import docx

        read: list[int] = []

        class Paragraph:
            def __init__(self, i: int) -> None:
                self._i = i

            @property
            def text(self) -> str:
                read.append(self._i)
                return "z" * 9000

        class Document:
            def __init__(self, _stream) -> None:
                self.paragraphs = [Paragraph(i) for i in range(100)]
                self.tables = []

        monkeypatch.setattr(text_extraction, "_refuse_zip_bomb", lambda _content: None)
        monkeypatch.setattr(docx, "Document", Document)

        result = extract_text("a.docx", b"x")

        assert result.truncated
        assert sorted(set(read)) == [0, 1, 2]  # 3 x 9000 pass 20,000 (each is read twice by the check)

    def test_a_word_file_stops_reading_table_rows_once_it_has_enough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import docx

        rows_read: list[int] = []

        class Cell:
            def __init__(self, text: str) -> None:
                self.text = text

        class Row:
            def __init__(self, i: int) -> None:
                self.i = i

            @property
            def cells(self):
                rows_read.append(self.i)
                return [Cell("c" * 8000)]

        class Table:
            rows = [Row(i) for i in range(100)]

        class Document:
            def __init__(self, _stream) -> None:
                self.paragraphs = []
                self.tables = [Table()]

        monkeypatch.setattr(text_extraction, "_refuse_zip_bomb", lambda _content: None)
        monkeypatch.setattr(docx, "Document", Document)

        result = extract_text("a.docx", b"x")

        assert result.truncated
        assert rows_read == [0, 1, 2]


