# configs

`config_app.json` is tracked; there is no `.example` twin. Secrets (the tool service tokens) are not kept here
but in `../.env` (see `../.env.example`). Restart Stronghold after editing.

| Key | Meaning |
|---|---|
| `usage.six_hour_token_limit`, `usage.weekly_token_limit` | Rolling token caps per account. 0 = unlimited. A new question over a cap gets `429`. |
| `usage.max_context_tokens_per_chat`, `usage.auto_summarize_ratio` | Optional. When the last answer used this share (above 0, at most 1) of the smaller of the model's context window and the cap, the chat is summarized before the next question. |
| `pricing.currency` | Must be `USD`. |
| `pricing.models` | Price per model name, `input` and `output` in USD per 1,000,000 tokens. A model that is not listed has no cost estimate. |

Stronghold's data and keys are not here: they are in `.data/stronghold/` in the Citadel folder.
