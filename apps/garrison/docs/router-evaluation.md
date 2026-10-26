# Router evaluation and rollout

> Historical evidence: this records the retired voter-based implementation.
> Legion v2 uses one decision provider and Laya/Jev strategies; the examples and
> thresholds below do not configure the current service.

Implementation was developed and validated on `codex/internal-router-agent`.
Local integration into `main` was subsequently authorized by the user. No running
deployment was changed, no local model weights were downloaded and no live
classifier call was made during implementation.

## Offline evidence

`python -m scripts.check_router_cases --offline` runs eight synthetic contract
fixtures: general, server, research, complex, follow-up, mixed work, attachment
references and overlong input. Fixtures inject known predictions into real Router
and triage plumbing, test abstention and report zero remote calls. Passing these
fixtures establishes contract behavior, not model accuracy.

Additional regression suites cover shared triage behavior, permission/approval
handling, role validation, no-download cache guards, independent decision
outcomes, tier compatibility, timeout/cancellation, per-voter attribution,
sanitized metadata, browser editing and offline/disabled Web listings. The plan's
verification record lists final commands/results.

## Live evaluation before deployment

Use a prepared environment with both local checkpoints cached and the existing
Jev credential supplied through the deployment environment. Router itself refuses
downloads. Run `python -m scripts.check_router_cases --live` explicitly; this
sends the synthetic case subjects to Jev and incurs provider usage. It never
dispatches specialist work or modifies external systems.

The JSON report compares direct Jev and staged Router choices, sizes, abstentions,
elapsed time and remote calls. Review errors and timing on representative real
rosters and tasks before enabling in a deployed instance. A configured model or
confidence score is not evidence of a successful live call or improved accuracy.
Recorded live comparison is pending because this implementation did not access
deployment secrets or activate external model calls.

## Operational limits

Missing/offline/disabled Router leaves Ember and configured default models in
control. Missing local checkpoints make those voters unavailable; configured
remote fallback may still decide. An end-to-end timeout abstains from the whole
Router response; late workers cannot trigger a handoff. Actual late completions
remain visible in Router's local usage log, while the completed API response can
include only work known before its deadline.

Disabling Router does not reactivate deprecated direct-Jev automatic routing.
Admin Save/Reset applies through the existing supervised agent restart.
