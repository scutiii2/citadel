"""Renders the body templates in ``templates/`` for ``send_email()`` (plain ``string.Template`` files).
Values are HTML-escaped by default; a name ending in ``_html`` opts out."""

from __future__ import annotations

from html import escape
from pathlib import Path
from string import Template


TEMPLATE_DIR = Path(__file__).parent / "templates"

_RAW_SUFFIX = "_html"


def available_templates() -> list[str]:
    """Names accepted by ``render_email_template``."""
    return sorted(path.stem for path in TEMPLATE_DIR.glob("*.html"))


def render_email_template(name: str, **values: str) -> str:
    """Fill ``templates/<name>.html`` and return the HTML body.
    Raises ``ValueError`` for an unknown template or one leaving the folder, ``KeyError`` for a missing placeholder."""
    if name not in available_templates():
        raise ValueError(f"Unknown email template {name!r}; expected one of {available_templates()}.")
    source = (TEMPLATE_DIR / f"{name}.html").read_text(encoding="utf-8")
    safe = {
        key: value if key.endswith(_RAW_SUFFIX) else escape(str(value))
        for key, value in values.items()
    }
    return Template(source).substitute(safe).strip()
