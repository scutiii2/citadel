# Council: shared Laya service and training pipeline

Date: 2026-10-22 (Asia/Manila)
Status: Draft for review. Documentation only; implementation and deployment have not started.
Plan: [Council implementation plan](../plans/2026-10-22-council.md).

## Intent and agreed scope

Create `apps/council/` inside Citadel as the central home for Laya inference,
training, calibration and versioned checkpoints. Connect existing Laya consumers
one at a time so their processes stop loading duplicate copies of the models.
The user chose the name Council and requested a spec and implementation plan
first. The operating defaults and API below are proposed engineering decisions,
not previously agreed user requirements.

One server does not imply one checkpoint. Council initially serves English and
typed-decisions, with one loaded instance of each distinct bundle. A trained
checkpoint can replace an existing profile only after evaluation of its intended
tasks. Training for one task does not establish improvement on another.

## Current code and constraints

- `apps/garrison/src/llm/laya_provider.py`: `LayaQuestions` loads Laya and calls
  native `predict(text, questions, max_len=...)`. Requests carry caller-supplied
  `choice`, `score` and `noul` questions. The public Garrison limit is eight
  questions, 2-10 options and 4,000 text characters.
- `apps/garrison/src/llm/decision.py`: the triage window defaults to 4,096 tokens;
  `CONTEXT_WINDOW=512` remains the provider's fallback. Several consumer comments
  still describe 512. Preserve actual behavior rather than copying those comments.
  Configuration currently allows windows through 32,768 and accepts question
  fields without Council's proposed per-field cap. Inventory actual usage and
  configured windows before migration; default-window parity is insufficient.
- `apps/garrison/src/llm/triage_flow.py`: owns voter order, thresholds, agreement,
  narrowing, uncertainty, traces and optional Jev fallback. By default `noul`
  skips English because of its known yes/no labeling problem.
- `apps/garrison/src/agents/router_engine.py`: creates another pair of Laya
  instances; `router_service.py` and `router_models.py` inspect local model state
  and cached files. Their readiness path must change during migration too.
- Armory's `TicketLaya`, Ember's `TagSuggester` and the triage question form call
  Garrison over existing APIs. They do not currently load their own weights.
  Moving them individually is a validation/configuration rollout; it does not
  require a new direct Council client in every app.
- Garrison's Docker image currently installs CPU-only PyTorch. CPU inference
  remains a supported deployment. No GPU, available VRAM or training speed has
  been established for the user's machine.
- Python apps have independent environments and communicate over HTTP/MCP;
  they do not import each other's source packages.
- The worktree has unrelated Ember and skill edits. Implementation must preserve
  them. This draft does not scaffold an app or change runtime configuration.

## Approaches and recommendation

| Approach | Benefit | Trade-off |
| --- | --- | --- |
| Council predicts; Garrison keeps workflow policy | Shares weights with minimal behavioral change and clear ownership | Garrison still runs the staged decision loop over HTTP |
| Council owns prediction and the entire triage/router policy | One endpoint for complete decisions | Couples a general model service to Garrison's workflow and fallback credentials |
| Keep in-process Laya and share training utilities | Smallest runtime change | Leaves duplicate memory and model lifecycle ownership |

Recommend the first approach. It implements the user's centralized service while
preserving the established triage and Router contracts. The spec and plan are
reviewable drafts of that recommendation; they authorize no runtime migration.

## Service ownership and project layout

Council owns native encoding, checkpoint loading, calibrated model predictions,
resource scheduling, bundle provenance and offline training/evaluation commands.
Garrison owns workflow thresholds, voter combination, narrowing, delegation,
remote fallback and usage attribution to the original operation. Consumer apps
own permissions, arguments, execution and user confirmation.

Use Python >=3.11, FastAPI, Uvicorn, Pydantic 2, HTTPX in clients, Laya and a pinned
compatible PyTorch runtime. Training extras add datasets/Hugging Face Hub,
NumPy, SciPy and scikit-learn. Choose exact Laya, Transformers and PyTorch pins
through a compatibility preflight and commit the resulting lock/constraints;
do not install floating upstream main during service startup.

Required app files: `README.md`, `pyproject.toml`, `run.bat`, `shell.bat`,
`configs/config_council.json.example`, `src/`, `tests/`, plus the conventional
credentials example created during implementation. Real credentials stay local.
Seed missing real config from its example, following Citadel's existing pattern.
Use ignored `data/` for bundles, source caches, dataset manifests, runs and the
compute lock; no extra top-level training/scripts/models folders. Training code
lives under `src/training/`, invoked with `python -m src.training.cli`.

Default Windows environment: `.venv_council`. Default bind: `127.0.0.1:8080`,
overridable by `COUNCIL_HOST`/`COUNCIL_PORT`. Recheck port availability at
implementation; Docker uses `0.0.0.0:8080` on the internal network. This is an
internal HTTP service, without an MCP endpoint or a browser UI in this version.

## Prediction contract, version 1

`GET /health` is unauthenticated and reports process liveness only. All `/v1/*`
operations require `X-Internal-Token` matching the shared `INTERNAL_API_TOKEN`.
Missing server token is a startup configuration error. Never expose the token to
browsers. Authenticate before accepting prediction work.

- `GET /v1/models`: sanitized profile IDs, immutable bundle IDs, supported question
  types/window, device/precision, calibration status and loaded/ready/error state.
  No absolute paths or text from requests.
- `GET /v1/ready`: 200 when configured startup profiles are loaded and validated;
  otherwise 503 with sanitized per-profile readiness. An unhealthy profile does
  not make a different ready profile unusable through `/v1/predict`.
- `POST /v1/predict`: exactly one native prediction against one selected profile.

```json
{
  "request_id": "operation-id-attempt-1",
  "model": "english",
  "text": "The database is refusing connections.",
  "questions": {
    "category": {
      "type": "choice",
      "instructions": "Which category best describes this issue?",
      "criteria": {"database": "Database errors", "network": "Network errors"}
    }
  },
  "max_len": 4096,
  "timeout_ms": 10000
}
```

Request rules: reject unknown fields, non-finite numbers, booleans masquerading
as integers, empty text/IDs, duplicate JSON object keys and unknown profiles.
Accept 1-8 questions; `choice` has 2-32 named options; `score` has 2-32 ordered
level descriptions; `noul` uses optional false/true criteria. The higher Council
option ceiling enables ABCD's 30-action experiment; Garrison retains its existing
2-10-option contract. Preserve input option order. Cap the HTTP body at 256 KiB,
text at 64,000 characters, IDs at 128 characters, and instruction/criterion text
at 4,000 characters each. These are transport limits, not context guarantees.
`max_len` defaults to 4,096 and must be 512-8,192, within the selected bundle's
validated ceiling. Native tokenization must retain every option and all state;
reject overflow before inference instead of silently truncating. Validate the
48-token native option cap where applicable to the pinned runtime.

Return native `answers` and `usage.input_tokens`, with
`usage.truncated=false` and `usage.state_tokens_dropped=0`, plus metadata:
`api_version=1`, `request_id`, `profile_id`, `bundle_id`, `calibration_id` (nullable),
`device`, `precision`, `queue_ms`, `inference_ms`. Choice answers preserve
`choice`, `probabilities`, `answer_confidence`; score/noul preserve their native
values and native confidence. Include `type` per answer. Validate complete
answer coverage, allowed labels, finite probabilities in [0,1], distributions
summing to one within 1e-4, and supported score ranges. Garrison continues to
derive `uncertain` through its existing policy. Initial imported bundles preserve
their native temperature configuration; candidate bundles apply exported fitted
calibration exactly once. Report inherited versus fitted calibration honestly.

Errors use `{"error":{"code":"...","message":"...","request_id":"..."}}`:
401 invalid token; 413 body too large; 422 invalid request/input too long;
404 unknown profile; 429 full queue (Retry-After: 1); 503 unavailable model or
runtime failure; 504 deadline expired. Runtime errors never return a guessed
answer. No automatic HTTP retries or response cache in v1; a repeated request ID
does not imply idempotency or reuse. Never include tokens, raw text or host paths
in HTTP errors.

## One model owner, scheduling and deadlines

Run exactly one Uvicorn worker without reload. Hold an OS-backed exclusive file
lock under `data/` for the service lifetime, shared with Council's training
commands. A second owner using the same configured data root fails startup;
all supported launches mount/use that same root. Do not scale replicas to share
a GPU. Manually bypassing the root/lock is outside this deployment contract.
Every standalone Council command that loads or executes model code, including
evaluation, calibration-logit collection, reload checks and local baseline
capture, takes the same lease. Pure report/logit analysis needs no model lease.
Promotion/rollback take an exclusive lease too and refuse while serving.

The model pool keys loaded engines by immutable bundle ID, device and precision;
aliases for the same key share one engine. Start with one execution worker across
both checkpoints, a FIFO queue of 32 waiting requests and one active prediction.
Defaults are configurable within documented bounds, but execution concurrency
remains one in v1. Different requested windows use per-call encoding settings,
not mutable global model settings. No cross-request batching in this version.

Timeout defaults to 10,000 ms; accept 1-30,000 ms. A request's deadline starts at
admission and includes validation/token budgeting, queueing and prediction. The
client passes its remaining deadline, and bounds the HTTP operation by that same
remaining time. Reject expired/queued-cancelled work before it starts. A native
forward pass cannot necessarily be interrupted: return/abandon the timed-out
reply, discard late results and keep the execution slot occupied until compute
really stops. Disconnects remove queued work; shutdown stops admission, drains
active compute and unloads only afterward. Closing a socket never releases GPU
ownership while its computation is still running.

Startup and prediction perform no artifact downloads. An explicit preparation
CLI imports/downloads pinned sources and records hashes. CPU and CUDA are
explicit deployment choices with separate dependency instructions; a configured
CUDA deployment reports failure rather than silently falling back to CPU.

## Model bundles and promotion

Use `data/bundles/<bundle_id>/` for immutable bundles and a versioned JSON profile
map in `configs/`. Profiles initially include `english` and `typed`; optional
candidate profiles are explicitly configured. A bundle contains model weights,
encoder config, tokenizer, native Laya config, source/checkpoint revisions and
hashes, dependency versions, input-builder version, supported types/window,
precision, calibration metadata and evaluation report references. Include a
label-order manifest for fixed-label tasks; generic callers still supply criteria.
Canonical relative artifact paths are constrained to the bundle directory.

Export to a staging directory, validate hashes and reload parity, then atomically
rename to its content-derived ID. Separate immutable identity from mutable
profile names. Every request resolves one bundle and retains that identity.
Changing a profile requires the offline promotion CLI and a service restart;
there is no hot model replacement or training HTTP endpoint in this version.
Preserve the prior mapping for explicit rollback. Known native label bugs remain
recorded in capabilities and Garrison's voter policy until separately verified.

## Training and data lifecycle

Training is a separate command/process. In v1, stop Council before a training
job; the shared compute lock refuses overlap instead of risking live inference
memory. Other apps then follow their configured unavailable-service behavior.
Training does not auto-promote weights, purchase compute, publish artifacts or
call a remote teacher. GPU capacity and a finite-loss/reload pilot precede a full
job. CPU dry runs and tiny fixtures validate contracts, not achievable full-run
speed. Start the real run from its pinned parent after a disposable pilot.

Use a common JSONL record: `id`, `group_id`, `task_id`, `text`, `questions`,
`targets`, `source` (dataset/revision/original split), and `label_provenance`.
Each target names an existing question and its correct choice, yes/no value or
ordinal level index. Keep complete question groups together when splitting.
The input builder reuses the native choice/type encoding for both training and
serving. Targets and metadata never enter model-visible state. Save original
reference distributions separately when sources provide teacher probabilities;
v1 training uses hard reference labels and reports teacher provenance explicitly.

Two initial importers:

1. **ABCD v1.1**: pin source `6b8700ce67c6b37b062dd7a60abc76d7ef832a97`.
   Build a conditional next-action `choice` task with all 30 ontology actions,
   preceding conversation and a versioned shared procedure reference. Select one
   eligible non-first action per conversation using seed 29 and a stable hash of
   conversation ID/turn; save selected IDs. Exclude the target turn, later turns,
   hidden scenario/intent and current action outcome. Earlier visible results
   remain. This recreates the task family, not the guide's unpublished exact split.
   Rich retrieval inputs and act-versus-speak training are later experiments.
2. **LocalLLaMA/typed-decisions**: choose a source commit during preparation and
   record it with file hashes. Preserve state, questions and source hard labels
   for choice/noul/score. Deduplicate `all` against workflow subsets rather than
   importing both. Declare existing typed-checkpoint exposure to its train split;
   do not claim it as newly unseen training or independent generalization.

Keep each source's official test split untouched. Deterministically group-split
official training data into 70% train / 15% validation / 15% calibration using
seed 29; record actual counts and per-label support. ABCD's official dev is an
additional declared development evaluation and is not pooled into final test.
Detect duplicate normalized payloads and overlapping group IDs across all sets;
quarantine cross-split duplicates and save exclusion reasons. Abort fitting or
promotion for missing task labels/insufficient calibration support, rather than
fabricating metrics. Scarce labels require a reported data/split revision.
No fixed source row counts are an importer correctness requirement after filtering.

Initial learning method: full-model supervised cross-entropy over native logits.
Choice/noul target the appropriate categorical index; score targets a declared
ordinal level (expected-score error is also evaluated). Weight question types
equally within each example, then examples equally within each task; sample tasks
uniformly for a mixed run. This avoids domination by the larger ABCD pack.
Use the guide's three epochs, seed 29, encoder LR 2.5e-5, head LR 1e-4,
effective batch 32, AdamW, weight decay 0.01, gradient clip 1.0 and cosine decay
as a named initial recipe. Record actual per-group scheduler endpoints; floor
is 1e-6. Microbatch/accumulation and FP32/BF16 are hardware-dependent explicit
run settings. Keep the best mean task macro-F1 on validation, earlier on ties.
Optional mixed runs follow single-source baselines; no LoRA/RLCD requirement.

Fit positive temperature values on calibration only, separately by question type
when supported. Store absent/unreliable fits explicitly; remove inherited
overrides that would mask newly fitted values. Choose workflow confidence gates
on calibration; serialize proposed gates in reports for Garrison operators,
without silently changing Garrison configuration. Re-evaluate narrowed and
combined flow outcomes; scalar calibration of a base model is not calibration
of the complete staged policy.

## Evaluation and acceptance

Before connecting callers, compare identical pinned inputs locally and over
Council. Require exact choices and agreement of native values/probabilities
within 1e-5 under the same device/precision/runtime. If it fails, diagnose before
migration. Preserve all allowed labels, score ranges and uncertainty behavior.
Capture embedded baseline results first, unload/stop that owner, then start
Council and replay the saved cases. Do not load both for a side-by-side check.
Record warm p50/p95 latency including queue time, throughput at concurrency
1/4/8, load time and resident memory. Set deployment performance targets after
this baseline; no guide-derived speed or accuracy promise.

Training reports cover untrained English, existing typed checkpoint, candidate,
and TF-IDF/logistic regression per supported categorical task. Record accuracy,
macro-F1, per-label counts/confusions, score MAE, NLL/Brier/reliability bins,
coverage, wrong accepted decisions, failures and timing with denominators.
Public/teacher-label agreement is distinguished from actual Citadel task quality.
Collect future Citadel corrections under an explicit data-retention policy;
request logging in this version stores IDs, task/profile/bundle, outcome codes
and timings, without request text or automatic training-data capture.

A candidate remains experimental until a predeclared validation/calibration
promotion policy specifies applicable tasks, acceptable regressions, accepted
error and review budget. Freeze that policy and checkpoint before final test;
save it in the run manifest. A CLI returns `eligible`, `rejected` or
`insufficient_evidence` with reasons. Promotion requires `eligible`; a model
without evidence for Router, note tagging or grouping cannot replace their
general profile. Test inspection triggers a new untouched holdout for a later
claim; frozen benchmark replays are labeled regression checks. Public data can
prove the pipeline and benchmark performance while production defaults remain
the shipped checkpoints. There is no requirement to produce a better trained
model to declare the infrastructure implemented.

## Migration and rollback

1. Build Council with pinned existing bundles and prove parity independently.
2. Implement/import/train/evaluate an experimental candidate; retain baseline
   profiles. Full training and candidate promotion are explicit operator actions.
3. Add Garrison transport mode `embedded|council`, initially `embedded`, with
   configured `COUNCIL_URL`. Switch Triage first. Keep its MCP request/response
   shape and flow policy; Council supplies one local voter prediction at a time.
   Preflight configured windows and actual request lengths/option fields against
   Council's body/field/token limits and selected bundle capabilities. Block the
   caller's cutover if an existing accepted workload is incompatible. Expand
   validated service limits or explicitly revise that workload through a later
   scoped change; do not silently truncate or silently reduce its contract.
4. Independently switch Router using its own transport setting and Council
   readiness. Preserve request-local policies, caller deadlines and explicit-tier
   behavior; English noul skip, local-only restrictions and cancellation persist.
5. Validate ticket grouping/tag choice, note tags and custom typed questions in
   successive rollout checks through the migrated Triage endpoint. No new browser
   exposure or direct client is required. Any discovered additional direct loader
   gets its own measured migration before the final ownership check.
6. After all deployment callers pass, use Council mode for both Triage and Router,
   remove embedded production loaders and the `embedded` option, then remove
   Laya/PyTorch from Garrison's dependencies and Docker image. Retain offline
   evaluation only in Council; update Garrison scripts to use Council. Operational
   rollback then uses a prior deployment revision, not a duplicate model process.

During rollout, reverting one caller's explicit transport setting restores its
embedded path. Council outages do not silently create embedded engines. Triage
may use its already-authorized remote fallback; local-only requests stay local
and report unavailability. Router abstains and leaves chat on its existing
fallback path. Advisory tag/group consumers retain their no-suggestion behavior.
Before the final cleanup, migrate the regression scripts, readiness and usage
labels too; changing only `predict()` is insufficient.

## Deployment, observability and exclusions

Provide a CPU Docker image and an explicit CUDA build recipe/override after GPU
preflight. Add Council to Compose's core network and publish-live paths. Persist
its data volume; imported serving bundles are provisioned explicitly, outside
image build/startup. Keep Council off public ports. The standard stack can start
with missing bundles and report not-ready; callers handle the outage. Docker
health uses liveness, not readiness that requires downloads. Start ordering is
not a substitute for readiness/error handling. Zima remains CPU unless configured
otherwise. Log bundle/device/precision and service saturation, not source text.

Windows `run.bat` carries launcher label/description and uses one process. The
historical root server launcher is absent from this checkout; provide metadata
and document registration rather than inventing an external launcher edit.

Outside v1: a training UI, public inference, remote teacher generation, automatic
retraining/promotion, shared cross-project Python libraries, distributed workers,
dynamic batching, hot reload, mandatory retrieval, and changing triage voting
mathematics. Include these only through a later scoped design.

## References and provenance

External references were inspected during this chat on 2026-10-22. Moving URLs
are discovery links; implementation records immutable revisions and licenses.

| Reference | Use and boundary |
| --- | --- |
| [The AI Automators fine-tuning guide page](https://www.theaiautomators.com/laya-fine-tuning-guide/) | Original user-provided link; inaccessible through browsing during this chat. The supplied PDF, rather than assumptions about this page, is the source for the recipe. |
| [Supplied PDF: Fine-tuning Laya with your own data](D:/User/Downloads/ai-automators-laya-fine-tuning-guide-v1.pdf) | Edition 1, 6 October 2026; 16 pages. Pages 5-8: splits, native encoding and supervised recipe; 10-12: evaluation, calibration and gates; 16: experiment provenance. Local source is not committed and may be unavailable to another developer. |
| [Laya upstream source and training examples](https://github.com/NandhaKishorM/laya#fine-tuning) | Native typed encoding, loading/export and training starting points. Upstream examples use RLCD; the PDF's recorded experiment uses supervised cross-entropy. Pin the runtime before adapting it. |
| [Pinned English parent](https://huggingface.co/convaiinnovations/laya/tree/55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851) | Guide's parent revision; compare with the locally deployed revision before claiming migration parity. |
| [Typed-decisions checkpoint card](https://huggingface.co/convaiinnovations/laya-typed-decisions) | Existing domain training/exposure and typed-question behavior; not independent evidence of Citadel performance. |
| [Jev Arena](https://github.com/theaiautomators/jev-arena) | Evaluation architecture and pinned-source acquisition; raw third-party datasets/run databases are not bundled in the checkout. |
| [Arena implementation notes](https://github.com/theaiautomators/jev-arena/blob/main/docs/IMPLEMENTATION.md) | Methodology, failure denominators, source exposure and benchmark limitations. |
| [Arena ABCD protocol](https://github.com/theaiautomators/jev-arena/blob/main/docs/ABCD-PROTOCOL.md) | Separate 300-conversation assessment with no fine-tuning. It is not the PDF's 1,000-case fine-tuning run or proof that its exact split IDs are public. |
| [Arena source pins](https://github.com/theaiautomators/jev-arena/blob/main/sources.lock.json) and [third-party notices](https://github.com/theaiautomators/jev-arena/blob/main/THIRD_PARTY.md) | Trace source/runtime provenance and original dataset terms; Arena's MIT license does not replace third-party licenses. |
| [ABCD upstream](https://github.com/asappresearch/abcd) and [data files](https://github.com/asappresearch/abcd/tree/master/data) | Public conversations, guidelines, KB and ontology. Official train/dev/test are 8,034/1,004/1,004 before filtering; record MIT notice and source pin. |
| [LocalLLaMA typed-decisions dataset](https://huggingface.co/datasets/LocalLLaMA/typed-decisions) | Synthetic workflow data with choice/noul/score questions, teacher references, official train/test and Apache-2.0 card. Preserve provenance and avoid duplicated aggregate/subset imports. |

Essential guide findings preserved here so the local PDF is not required to plan:
basic-state Laya 82.2%, rich-state Laya 86.1%, simple classifier 77.3%; the
basic run used 5,900 train / 983 validation / 1,000 calibration / 1,000 test cases.
At a 90% gate, calibration changed automatic cases from 840 to 674 and wrong
accepted cases from 97 to 36. These historical measurements of one support task
are neither Council acceptance targets nor evidence of end-to-end resolution.

Repository references (paths relative to Citadel):

- `AGENTS.md` and `.agents/skills/root-project-scaffold/SKILL.md`: project shape,
  independent environments, launch/configuration conventions.
- `.agents/skills/checking-the-catalog/SKILL.md`: check catalog before new reusable
  Garrison/Armory helpers during implementation; mirror interfaces without imports.
- `apps/garrison/src/llm/{laya_provider,triage_flow,decision,laya_classifier}.py`:
  current typed prediction, policy and compatibility behavior.
- `apps/garrison/src/agents/{router_engine,router_service,router_models}.py`:
  separate model ownership and readiness to migrate.
- `apps/garrison/scripts/{check_triage_cases,triage_three_way}.py` and
  `apps/garrison/docs/laya-triage-evaluation.md`: smoke checks, not an independent
  benchmark or calibrated accuracy claim.
- `apps/armory/src/services/{ticket_laya,ticket_laya_transport}.py` and
  `apps/Ember/ember_api/src/services/{tag_suggestions,triage_questions}.py`:
  indirect callers and their local-only/advisory contracts.
- `docs/superpowers/specs/2026-10-21-internal-router-agent-design.md`: Router
  policy/lifecycle intent; Council supersedes its in-process local-model ownership.
- `apps/treasury/src/{api,auth,config,seed,run}.py`: existing small HTTP service
  conventions, with self-contained implementation in Council.
- `docker-compose.yml`, `docker-compose.zima.yml`, `apps/garrison/Dockerfile`,
  `tools/publish_live.py`, `docs/deployment.md`: CPU deployment and publication paths.
