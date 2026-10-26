# Legion Triage Assistant: two fixes from review (2026-10-19)

> Historical evidence: this records the retired voter-based implementation.
> Legion v2 uses one decision provider and Laya/Jev strategies; the examples and
> thresholds below do not configure the current service.

Review of `apps/legion` triage flow (`src/llm/triage_flow.py`, `src/llm/laya_provider.py`, `src/llm/decision.py`). The 217 triage-related tests pass; both items below are gaps the tests do not cover.

## 1. A step 5 answer is marked `uncertain: false`

**Where**: `apps/legion/src/llm/triage_flow.py`, `final_answer`, line 135 (`"uncertain": not decided`).

**Problem**: `decided` only means the top option clearly leads in the pairwise comparison (`triage_pair_ratio`). No voter met its own threshold when step 5 runs. So English, typed and Jev can all be unsure and the answer still returns `uncertain: false`. `answer_confidence` is then the top option's share of the difference score, not a model confidence. The agent's `focus` text (`agents/triage-assistant.json`) tells callers to treat uncertain answers as provisional, so callers skip `also_check` on exactly these answers.

**Fix**: set `uncertain` to `True` for every step 5 result (the `decided` case keeps `also_check` and its note). Update the `final_answer` docstring and the README "Triage flow" section, which currently implies a decided final answer is settled.

**Tests to add** (`tests/test_triage_flow_provider.py` or `tests/test_decision_strategy.py`): all voters under threshold, top option leads clearly, assert `uncertain is True`, `also_check` set, top-level `uncertain` true.

## 2. `local_only` is enforced by one caller, not by the flow

**Where**: `TriageFlow.answer` (`triage_flow.py` line 202) never reads `request.local_only`. The privacy gate is `_asks_local_only` plus `use_fallback=False` in `LayaQuestions.answer` (`laya_provider.py` line 354).

**Problem**: it works today because both parse the same JSON. Any code that builds `TriageFlow` directly (the scripts in `scripts/` do) sends text to Jev even when the request says `local_only: true`. Ember (tag suggestions, triage questions), armory (`ticket_laya.py`) and mcp_server rely on this flag so note and ticket text stays on the machine.

**Fix**: after `parse_request` in `TriageFlow.answer`, add:

```python
self.use_fallback = self.use_fallback and not request.local_only
```

Keep the `_asks_local_only` pre-check (it picks the 4000-char limit before parsing).

**Tests to add**: build `TriageFlow(..., use_fallback=True)` directly, send `local_only: true`, assert Jev is never asked (monkeypatch `laya_provider._ask_fallback` to fail).

## Smaller items (not urgent)

- `_run_local` (`triage_flow.py` line 178) swallows `RuntimeError` and `ValueError`, so the caller sees only `no model could answer 'x'` and loses "Laya is not installed".
- `_ask_fallback` (`laya_provider.py` line 283) hands off between chain backends at `request.min_confidence` (default 70), while the flow judges Jev at 0.90 or the request override.
- `_restrict` keeps the original `choice`, so `disagreement` can name an eliminated option.
- `parse_threshold` raises `SystemExit` from library code; move it to the script that uses it.
- Doc drift: compact answer size (65 vs 75 tokens) between the `triage_flow.py` docstring and the README; "20/23 and 21/23 on the 47 cases" in the README.

Historical diagnostic references updated for Legion v2: the retired voter-comparison diagnostic is covered by decision-strategy tests and router contract cases.
