"""Email notifications via smtplib (stdlib only); settings come from the ``"email"`` section of the JSON config (see ``services/app_config.py``).
Transports: ``"ssl"`` (465), ``"starttls"`` (587), ``"none"`` (trusted LAN relays only, sent in the clear). A failed send raises; callers decide whether to abort."""

from __future__ import annotations

import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from html import unescape

from src.services.app_config import EmailConfig
from src.services.email.recipients import parse_recipients


# Anything inside these is code, not prose, and would otherwise land in the
# plain-text part as a wall of CSS.
_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)

# Links are kept as "text (url)": these messages exist to carry a link, and anchor text alone
# would tell the reader to click something that isn't there.
_ANCHOR = re.compile(r'<a\b[^>]*?href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)

# Tags that end a visual line. Without this the whole document collapses
# onto one line, since HTML's own newlines are just source formatting.
_BLOCK_BREAK = re.compile(r"<br\s*/?>|</(?:p|div|h[1-6]|li|tr|table|blockquote)\s*>", re.IGNORECASE)

_ANY_TAG = re.compile(r"<[^>]+>")

# Stands in for a line break between tag stripping and whitespace flattening; a real "\n" can't,
# since the HTML source's newlines are indentation and become indistinguishable once tags are gone.
_LINE_BREAK = "\x00"

# Appended to every message this module sends, so a recipient never mistakes
# a notification for a mailbox somebody reads.
AUTO_GENERATED_NOTICE = "This is an auto-generated message. Do not reply."

SUBJECT_PREFIX = "EMBER"

_MESSAGE_ID = re.compile(r"<[^<>\s@]+@[^<>\s@]+>")


def validate_message_id(value: str) -> str:
    """Require a single bracketed Message-ID, without embedded headers."""
    _validate_header(value)
    if not _MESSAGE_ID.fullmatch(value):
        raise ValueError("Provide a bracketed Message-ID such as <id@example.com>.")
    return value


def _validate_header(value: str) -> None:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Email headers must not contain control characters.")


def _validate_address(value: str) -> None:
    _validate_header(value)
    try:
        parsed = parse_recipients(value)
    except ValueError:
        raise ValueError("Provide a valid email address.") from None
    if parsed != [value]:
        raise ValueError("Provide one email address per recipient entry.")


def format_subject(subject: str) -> str:
    """``[EMBER] <subject>``: the agent name, then the context of the message."""
    return f"[{SUBJECT_PREFIX}] {subject}"


def _html_to_text(body_html: str) -> str:
    """Best-effort plain-text rendering of an HTML body, via regex rather than a parser (bodies are small in-project templates).
    Known limits: no layout (tables and lists flatten) and only double-quoted ``href`` is recovered; pass ``body_text`` when wording matters."""
    # Dropped so the sentinel below can't be forged by the body itself.
    text = body_html.replace(_LINE_BREAK, "")
    text = _SCRIPT_OR_STYLE.sub("", text)
    text = _ANCHOR.sub(r"\2 (\1)", text)
    text = _BLOCK_BREAK.sub(_LINE_BREAK, text)
    text = _ANY_TAG.sub("", text)
    text = unescape(text)
    # One line per block with inner whitespace collapsed, so a wrapped paragraph doesn't arrive ragged.
    lines = [" ".join(line.split()) for line in text.split(_LINE_BREAK)]
    return "\n".join(line for line in lines if line)


def send_email(
    config: EmailConfig,
    capability_alias: str,
    subject: str,
    body_html: str | None,
    *,
    to: list[str] | None = None,
    body_text: str | None = None,
    in_reply_to: str | None = None,
    references: list[str] | None = None,
    prefix_subject: bool = True,
) -> str:
    """SMTP transport; application callers use ``email_delivery.deliver_email``. Returns the Message-ID after SMTP accepts every recipient.
    Sends ``[EMBER] <subject>`` (``prefix_subject=False`` keeps the caller's) with an auto-generated notice; ``to`` defaults to ``config.to``; ``body_text`` is derived from the HTML when omitted, since HTML-only is a spam signal."""
    recipients = to if to is not None else config.to
    if not recipients:
        raise ValueError("No recipients: pass to=[...] or set a non-empty 'to' list in config.json")

    _validate_header(subject)
    _validate_header(capability_alias)
    _validate_address(config.from_address)
    for recipient in recipients:
        _validate_address(recipient)
    ancestry = list(dict.fromkeys(validate_message_id(value) for value in references or []))
    if in_reply_to is not None:
        validate_message_id(in_reply_to)
        if in_reply_to not in ancestry:
            ancestry.append(in_reply_to)
    if body_html is None and body_text is None:
        raise ValueError("Provide a plain text or HTML email body.")

    if config.security not in ("ssl", "starttls", "none"):
        # Checked before opening a socket: never offer a password on a config that can't say how to protect the connection.
        raise ValueError(
            f"Unknown email security mode {config.security!r}; expected one of ssl, starttls, none."
        )

    text_part = body_text if body_text is not None else _html_to_text(body_html or "")
    plain = MIMEText(f"{text_part}\n\n{AUTO_GENERATED_NOTICE}", "plain")
    message = MIMEMultipart("alternative") if body_html is not None else plain
    message["Subject"] = format_subject(subject) if prefix_subject else subject
    message["From"] = config.from_address
    message["To"] = ", ".join(recipients)
    # Some receivers penalize a message without Date or Message-ID, and threading needs the latter; smtplib adds neither.
    message["Date"] = formatdate(localtime=True)
    # make_msgid() defaults to the machine hostname (e.g. "desktop.lan"), which leaks internal naming
    # and mismatches the From domain, a spam heuristic.
    message["Message-ID"] = make_msgid(domain=config.from_address.rpartition("@")[2] or None)
    if in_reply_to is not None:
        message["In-Reply-To"] = in_reply_to
    if ancestry:
        message["References"] = " ".join(ancestry)

    # Order is the protocol: RFC 2046 prefers the last multipart/alternative part, so plain text goes first.
    if body_html is not None:
        message.attach(plain)
        message.attach(MIMEText(f'{body_html}\n<p style="color:#888;font-size:12px;font-style:italic;">{AUTO_GENERATED_NOTICE}</p>', "html"))
    raw_message = message.as_string()

    # smtplib exposes implicit TLS as a separate class: the socket is wrapped before the greeting,
    # so starttls() has no plain session to run on.
    if config.security == "ssl":
        client = smtplib.SMTP_SSL(config.smtp_server, config.smtp_port, timeout=15)
    else:
        client = smtplib.SMTP(config.smtp_server, config.smtp_port, timeout=15)

    with client as server:
        if config.security == "starttls":
            server.starttls()
        if config.password:
            # An empty password means the relay doesn't want AUTH; offering it anyway fails the send
            # on servers without the AUTH extension.
            server.login(config.from_address, config.password)
        refused = server.sendmail(config.from_address, recipients, raw_message)
        if refused:
            raise RuntimeError("Email delivery was incomplete: one or more recipients were refused.")
    return str(message["Message-ID"])
