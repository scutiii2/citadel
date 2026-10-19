# capabilities/generator/

Generate random passwords, passphrases, PINs and one-time codes, create TOTP secrets, and show the current TOTP code for a secret - five tools.

## Tools

| Tool | Purpose | Connection |
| --- | --- | --- |
| `tool_gen_generatePassword` | Random password with chosen character types. | Local |
| `tool_gen_generatePassphrase` | Random-word passphrase. | Local |
| `tool_gen_generatePin` | Random numeric PIN or one-time code. | Local |
| `tool_gen_generateTotpSecret` | New TOTP secret and otpauth:// URI. | Local |
| `tool_gen_getTotpCode` | Current TOTP code for a secret. | Local |

## Slash commands

| Tool | Slash command | Parameters |
| --- | --- | --- |
| `tool_gen_generatePassword` | `/gen password` | <ul><li>`length` - optional, default `20`. Password length (8 to 128).</li><li>`use_upper` - optional, default `true`. Include A-Z.</li><li>`use_lower` - optional, default `true`. Include a-z.</li><li>`use_digits` - optional, default `true`. Include 0-9.</li><li>`use_symbols` - optional, default `true`. Include symbols.</li><li>`exclude_ambiguous` - optional, default `false`. Leave out look-alike characters (I l 1 O 0 o).</li><li>`email_to` - optional. Email address(es), comma-separated, to send the value to instead of showing it.</li></ul> |
| `tool_gen_generatePassphrase` | `/gen passphrase` | <ul><li>`words` - optional, default `6`. How many words (3 to 12).</li><li>`separator` - optional, default `-`. Text between words (up to 3 characters).</li><li>`capitalize` - optional, default `false`. Capitalise each word.</li><li>`add_number` - optional, default `false`. Append one random digit.</li><li>`email_to` - optional. Email address(es), comma-separated, to send the value to instead of showing it.</li></ul> |
| `tool_gen_generatePin` | `/gen pin` | <ul><li>`length` - optional, default `6`. How many digits (4 to 12).</li><li>`email_to` - optional. Email address(es), comma-separated, to send the value to instead of showing it.</li></ul> |
| `tool_gen_generateTotpSecret` | `/gen totp_secret` | <ul><li>`issuer` - optional. Service name shown in the authenticator app.</li><li>`account` - optional. Account name shown in the authenticator app.</li><li>`email_to` - optional. Email address(es), comma-separated, to send the value to instead of showing it.</li></ul> |
| `tool_gen_getTotpCode` | `/gen totp` | <ul><li>`secret` - required. Base32 TOTP secret.</li><li>`digits` - optional, default `6`. Code length (6 to 8).</li><li>`period` - optional, default `30`. Seconds each code stays valid (15 to 120).</li><li>`email_to` - optional. Email address(es), comma-separated, to send the value to instead of showing it.</li></ul> |

## Typical workflow

| Sequence | Tool | Explanation |
| --- | --- | --- |
| 1 | `tool_gen_generateTotpSecret` | Create a secret and add it to an authenticator app. |
| 2 | `tool_gen_getTotpCode` | Show the current code for that secret. |

## Emailing a value

Every tool takes an optional `email_to` (comma-separated addresses). The tool generates the value, sends it through `services/email_delivery.deliver_email` (alias `generator`, so the Email capability must be online and configured) and returns the result with the value fields empty, `emailed_to` set and a message that only confirms the send. The value never reaches the model or the chat transcript. Addresses are checked before anything is generated; if delivery fails the tool raises and no value is returned. Because a tool can now send mail, none of the five declares `readOnlyHint`: ember's Auto approval mode asks before running them.

## Page

ember_web has a dedicated Generator page at `/generator` (`GeneratorView.vue`, needs `tools.execute`): one tabbed card (Password, Passphrase and PIN regenerate live as you change a control; TOTP secret and TOTP code run on request) with a strength bar from `entropy_bits`. The capability has no `gui/page.json`.

## Configuration

No config or secrets, and nothing is stored: no files, no database, no audit trail.

- All randomness comes from Python's `secrets` module (the OS CSPRNG).
- Passwords carry at least one character of every chosen type. `entropy_bits` is the pool-size estimate.
- Passphrases draw from `utils/wordlist.py`: the EFF long word list (7,776 words, about 12.9 bits each), so 6 words is about 78 bits. Four entries contain a hyphen (`drop-down`, `felt-tip`, `t-shirt`, `yo-yo`); use a separator other than `-` if a passphrase must be split back into words.
- The word list is © 2016 Electronic Frontier Foundation, licensed [CC BY 3.0 US](https://creativecommons.org/licenses/by/3.0/us/), from <https://www.eff.org/files/2016/07/18/eff_large_wordlist.txt>. The words are unchanged; only the dice numbers were dropped.
- `tool_gen_generatePin` returns `entropy_bits` with the digits. It is also the random one-time code: plain digits with no time window. The caller must keep and check it.
- TOTP follows RFC 6238 (HMAC-SHA1, 30 s, 6 digits by default), so codes match Google Authenticator and similar apps.

**Privacy.** Without `email_to`, a generated value, and a TOTP secret passed to `tool_gen_getTotpCode`, travels through the chat and the agent transcript like any other tool result or argument. The tool does not log or store it, but chat history and agent logs may. Treat a value generated here as visible to whoever can read that chat; do not use it for something that must stay secret from them.

Toggle: `"gen"` in `configs/config_capabilities.json`.
