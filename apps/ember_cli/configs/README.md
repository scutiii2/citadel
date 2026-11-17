# configs

`config_cli.json` is tracked; there is no `.example` twin. The password is never stored: it is typed at login.

| Key | Meaning |
|---|---|
| `ember_api_url` | Portcullis address, `http://` or `https://`. A trailing slash is removed. |
| `username` | Account to log in as. Empty asks for it. |

A missing file means the defaults.
