"""Result models for the generator tools; each ends with a `message` to relay verbatim.
With `email_to`, the value is emailed and its fields are None."""

from __future__ import annotations

from pydantic import BaseModel, Field

_EMAILED = "Set only when the tool was given email_to: the addresses the value was emailed to. The value fields are then empty."


class PasswordResult(BaseModel):
    password: str | None = Field(description="The generated password. Shown once; this server does not store it. Empty when emailed.")
    length: int = Field(description="How many characters the password has.")
    entropy_bits: float = Field(description="Approximate strength in bits (length x log2 of the character pool).")
    emailed_to: str | None = Field(default=None, description=_EMAILED)
    message: str = Field(description="Human-readable summary, safe to relay verbatim.")


class PassphraseResult(BaseModel):
    passphrase: str | None = Field(description="The generated passphrase. Shown once; this server does not store it. Empty when emailed.")
    words: int = Field(description="How many words it holds.")
    entropy_bits: float = Field(description="Strength in bits (words x log2 of the word-list size, plus any digit).")
    emailed_to: str | None = Field(default=None, description=_EMAILED)
    message: str = Field(description="Human-readable summary, safe to relay verbatim.")


class PinResult(BaseModel):
    pin: str | None = Field(description="The generated digits, with leading zeros kept. Shown once; not stored. Empty when emailed.")
    length: int = Field(description="How many digits it has.")
    entropy_bits: float = Field(description="Strength in bits (length x log2 of 10).")
    emailed_to: str | None = Field(default=None, description=_EMAILED)
    message: str = Field(description="Human-readable summary, safe to relay verbatim.")


class TotpSecretResult(BaseModel):
    secret: str | None = Field(description="Base32 TOTP secret for an authenticator app. Shown once; not stored. Empty when emailed.")
    otpauth_uri: str | None = Field(description="otpauth:// URI an authenticator app or QR generator can import. Empty when emailed.")
    emailed_to: str | None = Field(default=None, description=_EMAILED)
    message: str = Field(description="Human-readable summary, safe to relay verbatim.")


class TotpCodeResult(BaseModel):
    code: str | None = Field(description="The current one-time code, with leading zeros kept. Empty when emailed.")
    seconds_remaining: int = Field(description="Seconds until this code stops being valid.")
    period: int = Field(description="Length of one code window in seconds.")
    emailed_to: str | None = Field(default=None, description=_EMAILED)
    message: str = Field(description="Human-readable summary, safe to relay verbatim.")
