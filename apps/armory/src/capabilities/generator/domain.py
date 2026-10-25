"""Password, passphrase, PIN and TOTP generation.

Generation is pure standard library (`secrets`, `hmac`, `hashlib`). All
randomness comes from `secrets` (the OS CSPRNG), never `random`. Nothing
generated is stored or logged; callers get it back once, or - when
`email_to` is given - it goes to that inbox through the email delivery
service and is left out of the result, so it never reaches the caller.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import math
import secrets
import string
import struct
import time
from urllib.parse import quote, urlencode

from src.capabilities.generator.contract import (
    PassphraseResult,
    PasswordResult,
    PinResult,
    TotpCodeResult,
    TotpSecretResult,
)
from src.capabilities.generator.utils.wordlist import WORDS
from src.services.email import delivery as email_delivery
from src.services.email.recipients import parse_recipients

SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?"
AMBIGUOUS = set("Il1O0o")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
TOTP_SECRET_BYTES = 20  # 160 bits, the RFC 4226 recommendation


def _entropy_bits(pool_size: int, picks: int) -> float:
    return round(picks * math.log2(pool_size), 1)


def _recipients(email_to: str) -> list[str]:
    """Validated addresses from a comma-separated `email_to`; empty when not emailing.
    Checked before anything is generated, so a bad address wastes nothing."""
    if not email_to.strip():
        return []
    if any(ord(char) < 32 or ord(char) == 127 for char in email_to):
        raise ValueError("email_to must not contain control characters.")
    try:
        return parse_recipients(email_to)
    except ValueError:
        raise ValueError("email_to must hold valid email addresses separated by commas.") from None


def _email_instead(result, recipients: list[str], label: str, lines: list[str], hidden: tuple[str, ...]):
    """Email `lines` to `recipients` and return `result` with the `hidden` fields emptied.
    Delivery errors propagate: the value is never returned when it was not sent."""
    if not recipients:
        return result
    body = f"Your requested {label}:\n\n" + "\n".join(lines) + "\n\nThis message is the only copy: it is not stored anywhere."
    email_delivery.deliver_email(recipients, f"Your {label}", body, capability_alias="generator")
    sent_to = ", ".join(recipients)
    return result.model_copy(update={
        **{field: None for field in hidden},
        "emailed_to": sent_to,
        "message": f"Emailed the {label} to {sent_to}. It is not shown here and not stored.",
    })


def generate_password(
    length: int = 20,
    use_upper: bool = True,
    use_lower: bool = True,
    use_digits: bool = True,
    use_symbols: bool = True,
    exclude_ambiguous: bool = False,
    email_to: str = "",
) -> PasswordResult:
    """Random password with at least one character from each chosen class."""
    recipients = _recipients(email_to)
    classes = [
        chars
        for enabled, chars in (
            (use_upper, string.ascii_uppercase),
            (use_lower, string.ascii_lowercase),
            (use_digits, string.digits),
            (use_symbols, SYMBOLS),
        )
        if enabled
    ]
    if exclude_ambiguous:
        classes = ["".join(c for c in chars if c not in AMBIGUOUS) for chars in classes]
    if not classes:
        raise ValueError("Pick at least one character type: upper, lower, digits or symbols.")
    if not MIN_PASSWORD_LENGTH <= length <= MAX_PASSWORD_LENGTH:
        raise ValueError(f"length must be between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH}.")

    pool = "".join(classes)
    chars = [secrets.choice(chars) for chars in classes]
    chars += [secrets.choice(pool) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    password = "".join(chars)
    bits = _entropy_bits(len(pool), length)
    result = PasswordResult(
        password=password,
        length=length,
        entropy_bits=bits,
        message=f"Generated a {length}-character password (about {bits} bits). It is shown once and not stored.",
    )
    return _email_instead(result, recipients, "password", [password], ("password",))


def generate_passphrase(
    words: int = 6,
    separator: str = "-",
    capitalize: bool = False,
    add_number: bool = False,
    email_to: str = "",
) -> PassphraseResult:
    """Random words from the bundled list, optionally capitalised and with a trailing digit."""
    recipients = _recipients(email_to)
    if not 3 <= words <= 12:
        raise ValueError("words must be between 3 and 12.")
    if len(separator) > 3:
        raise ValueError("separator can be at most 3 characters.")

    picked = [secrets.choice(WORDS) for _ in range(words)]
    if capitalize:
        picked = [word.capitalize() for word in picked]
    passphrase = separator.join(picked)
    bits = _entropy_bits(len(WORDS), words)
    if add_number:
        passphrase += separator + str(secrets.randbelow(10))
        bits = round(bits + math.log2(10), 1)
    result = PassphraseResult(
        passphrase=passphrase,
        words=words,
        entropy_bits=bits,
        message=f"Generated a {words}-word passphrase (about {bits} bits). It is shown once and not stored.",
    )
    return _email_instead(result, recipients, "passphrase", [passphrase], ("passphrase",))


def generate_pin(length: int = 6, email_to: str = "") -> PinResult:
    """Random digits, leading zeros kept. Also usable as a one-time code."""
    recipients = _recipients(email_to)
    if not 4 <= length <= 12:
        raise ValueError("length must be between 4 and 12.")
    pin = "".join(secrets.choice(string.digits) for _ in range(length))
    result = PinResult(
        pin=pin,
        length=length,
        entropy_bits=_entropy_bits(10, length),
        message=f"Generated a {length}-digit code. It is shown once and not stored.",
    )
    return _email_instead(result, recipients, "one-time code", [pin], ("pin",))


def _decode_secret(secret: str) -> bytes:
    cleaned = "".join(secret.split()).upper().rstrip("=")
    if not cleaned:
        raise ValueError("secret is empty.")
    try:
        return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))
    except (binascii.Error, ValueError) as error:
        raise ValueError("secret is not valid base32 (letters A-Z and digits 2-7).") from error


def _hotp(key: bytes, counter: int, digits: int) -> str:
    """RFC 4226 HOTP with HMAC-SHA1 and dynamic truncation."""
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def generate_totp_secret(issuer: str = "", account: str = "", email_to: str = "") -> TotpSecretResult:
    """New random base32 secret plus the otpauth:// URI that imports it."""
    recipients = _recipients(email_to)
    secret = base64.b32encode(secrets.token_bytes(TOTP_SECRET_BYTES)).decode("ascii").rstrip("=")
    label = quote(f"{issuer}:{account}" if issuer and account else issuer or account or "account", safe="")
    params = {"secret": secret}
    if issuer:
        params["issuer"] = issuer
    uri = f"otpauth://totp/{label}?{urlencode(params, quote_via=quote)}"
    result = TotpSecretResult(
        secret=secret,
        otpauth_uri=uri,
        message="Generated a TOTP secret (SHA1, 6 digits, 30 s). Add it to an authenticator app now; it is shown once and not stored.",
    )
    lines = [f"Secret: {secret}", f"Import link: {uri}"]
    return _email_instead(result, recipients, "TOTP secret", lines, ("secret", "otpauth_uri"))


def get_totp_code(secret: str, digits: int = 6, period: int = 30, at: float | None = None, email_to: str = "") -> TotpCodeResult:
    """Current RFC 6238 code for `secret`. `at` (unix seconds) is for tests."""
    recipients = _recipients(email_to)
    if digits not in (6, 7, 8):
        raise ValueError("digits must be 6, 7 or 8.")
    if not 15 <= period <= 120:
        raise ValueError("period must be between 15 and 120 seconds.")
    now = time.time() if at is None else at
    code = _hotp(_decode_secret(secret), int(now // period), digits)
    remaining = period - int(now % period)
    result = TotpCodeResult(
        code=code,
        seconds_remaining=remaining,
        period=period,
        message=f"Current code {code}, valid for {remaining} more seconds.",
    )
    return _email_instead(result, recipients, "TOTP code", [f"Code: {code} (valid for {remaining} more seconds)"], ("code",))
