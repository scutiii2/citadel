"""MCP tool wrappers for the generator capability; thin, no config.
Values are returned once (or emailed with `email_to`), never stored or logged."""

from __future__ import annotations

from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field

from src.capabilities.generator import domain
from src.capabilities.generator.contract import (
    PassphraseResult,
    PasswordResult,
    PinResult,
    TotpCodeResult,
    TotpSecretResult,
)
from src.commands import command
from src.offload import offload
from src.server import mcp


# Not read-only: with `email_to` a tool sends an email, so ember's "Auto" approval mode must ask first.
_SENDS_EMAIL = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)

EmailTo = Annotated[
    str,
    Field(
        description=(
            "Optional. Email address(es), comma-separated, to send the generated value to directly. "
            "The value is then NOT returned and must not be repeated: only confirm it was sent. "
            "Use it whenever the person asks for the value to be sent, emailed or delivered somewhere. "
            "Leave empty to get the value back in this chat."
        ),
    ),
]


@command(name="password", description="Generate a random password")
@mcp.tool(meta={"keywords": ["generator", "password", "random", "secure", "generate"], "display_label": "Generating password"}, annotations=_SENDS_EMAIL)
@offload
def tool_gen_generatePassword(
    length: Annotated[int, Field(description="Password length in characters.", ge=8, le=128, json_schema_extra={"input": "range"})] = 20,
    use_upper: Annotated[bool, Field(description="Include A-Z.")] = True,
    use_lower: Annotated[bool, Field(description="Include a-z.")] = True,
    use_digits: Annotated[bool, Field(description="Include 0-9.")] = True,
    use_symbols: Annotated[bool, Field(description="Include symbols such as ! @ # $ %.")] = True,
    exclude_ambiguous: Annotated[bool, Field(description="Leave out look-alike characters (I l 1 O 0 o).")] = False,
    email_to: EmailTo = "",
) -> PasswordResult:
    """Generate a cryptographically random password with at least one character
    of every chosen type. Deterministic rules, random output; the value is
    returned once and not stored. Tell the person to copy it now, unless
    `email_to` was set: then it is emailed, not returned, and not to be repeated."""
    return domain.desk.generate_password(length, use_upper, use_lower, use_digits, use_symbols, exclude_ambiguous, email_to)


@command(name="passphrase", description="Generate a random passphrase")
@mcp.tool(meta={"keywords": ["generator", "passphrase", "words", "diceware", "random", "generate"], "display_label": "Generating passphrase"}, annotations=_SENDS_EMAIL)
@offload
def tool_gen_generatePassphrase(
    words: Annotated[int, Field(description="How many words.", ge=3, le=12, json_schema_extra={"input": "range"})] = 6,
    separator: Annotated[str, Field(description="Text between words (up to 3 characters).", max_length=3)] = "-",
    capitalize: Annotated[bool, Field(description="Capitalise each word.")] = False,
    add_number: Annotated[bool, Field(description="Append one random digit.")] = False,
    email_to: EmailTo = "",
) -> PassphraseResult:
    """Generate a passphrase of random words from a bundled word list. Easier
    to type and remember than a random password; 6 words is about 78 bits.
    The value is returned once and not stored. If `email_to` was set it is
    emailed instead and not returned."""
    return domain.desk.generate_passphrase(words, separator, capitalize, add_number, email_to)


@command(name="pin", description="Generate a random PIN or one-time code")
@mcp.tool(meta={"keywords": ["generator", "pin", "otp", "one-time", "code", "digits", "random", "generate"], "display_label": "Generating code"}, annotations=_SENDS_EMAIL)
@offload
def tool_gen_generatePin(
    length: Annotated[int, Field(description="How many digits.", ge=4, le=12, json_schema_extra={"input": "range"})] = 6,
    email_to: EmailTo = "",
) -> PinResult:
    """Generate a random numeric PIN. Use it as a one-time code too: it is
    plain random digits with no time window or secret, so the caller must
    store and check it. If `email_to` was set it is emailed instead and not
    returned, so it cannot be checked later by the caller.
    For authenticator-app codes use `tool_gen_getTotpCode`."""
    return domain.desk.generate_pin(length, email_to)


@command(name="totp_secret", description="Generate a TOTP secret for an authenticator app")
@mcp.tool(meta={"keywords": ["generator", "totp", "otp", "secret", "authenticator", "2fa", "mfa", "generate"], "display_label": "Generating TOTP secret"}, annotations=_SENDS_EMAIL)
@offload
def tool_gen_generateTotpSecret(
    issuer: Annotated[str, Field(description="Service name shown in the authenticator app, e.g. Ember. Optional.")] = "",
    account: Annotated[str, Field(description="Account name shown in the authenticator app, e.g. an email. Optional.")] = "",
    email_to: EmailTo = "",
) -> TotpSecretResult:
    """Generate a new base32 TOTP secret and its otpauth:// URI. The person adds
    the secret to an authenticator app; `tool_gen_getTotpCode` then shows the
    same codes. The value is returned once and not stored. If `email_to` was
    set it is emailed instead and not returned."""
    return domain.desk.generate_totp_secret(issuer, account, email_to=email_to)


@command(name="totp", description="Show the current TOTP code for a secret")
@mcp.tool(meta={"keywords": ["generator", "totp", "otp", "code", "authenticator", "2fa", "mfa", "current"], "display_label": "Computing TOTP code"}, annotations=_SENDS_EMAIL)
@offload
def tool_gen_getTotpCode(
    secret: Annotated[
        str,
        Field(description="Base32 TOTP secret (spaces allowed).", json_schema_extra={"input": "password"}),
    ],
    digits: Annotated[int, Field(description="Code length.", ge=6, le=8)] = 6,
    period: Annotated[int, Field(description="Seconds each code stays valid.", ge=15, le=120)] = 30,
    email_to: EmailTo = "",
) -> TotpCodeResult:
    """Compute the current RFC 6238 one-time code for a base32 secret, plus
    the seconds left before it changes. Only the person who holds the secret
    should ask for this; the secret is not stored. If `email_to` was set the
    code is emailed instead and not returned."""
    return domain.desk.get_totp_code(secret, digits, period, email_to=email_to)
