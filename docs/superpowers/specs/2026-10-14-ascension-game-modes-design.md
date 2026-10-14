# Ascension game modes

Date: 2026-10-14
Status: written spec awaiting owner review

## Intent and approved direction

Add three activities inside the existing Battle tab: Wild Hunts for collecting
Ascended, Ascension Trials for developing type-specific fighters, and Expeditions
for earning XP and rewards while offline.

The owner approved the three-mode proposal and requested that implementation reuse
the **current header and preview cards unchanged**. Generated mockups show layout
ideas only. Reuse `EmShell`, the current navigation in `App.vue`, and
`AscendedPreviewCard`, including its existing art selection, typography, frame
assets, metadata, proportions, and size rules. Do not restyle these components or
replace their sprites. Display overall rating outside cards.

Follow `apps/ascension/AGENTS.md` and `apps/ascension/DESIGN.md`. New content uses
the existing sanctuary background, theme tokens, controls, and responsive layout.
No changes to Ember navigation, permissions, or game launch are required.

## Existing behavior to preserve

- Battles use one fighter selected from the owner's squad.
- Manual/Autonomous is the battle control mode, independent of the new activity.
- Existing random checkpoints, revisions, ownership checks, and idempotent writes
  continue to govern battles and rewards.
- Hunt capture retains the current HP/EMBLEM/tier-based chance calculation.
- Fainting, tier ladders, level caps, loadouts, presets, capture copies, personality
  awards, and shop behavior retain their current rules except expedition locks.
- The existing repository is SQLite schema version 7. Extend its incremental
  migrations rather than rebuilding player data.

## Overall rating and initial balance

Introduce a server-calculated overall rating:

`overall = catalog HP + catalog Power + catalog Speed`

Use the positive integer stats calculated by `Catalog.stat_value` at the owned
Ascended's current level and effective tier. This is a transparent baseline-stat
rating; do not add temporary buffs, personality preferences, ability percentages,
or passive estimates. Those mechanics affect combat but have no single reliable
stat-equivalent value. Stars currently do not modify these stats directly.

The server exposes rating for owned Ascended, encounter previews, and activity
preparation. The client displays the server result. Freeze the selected fighter's
rating and reward multiplier when the battle starts.

The chat's difficulty bands were illustrative. Use these initial bands after
checking the current catalog:

| Hunt | Recommended overall | Enemy overall range |
| --- | --- | --- |
| Outskirts | 100–299 | 100–299 |
| Frontier | 300–599 | 300–599 |
| Forbidden Grounds | 600–1599 | 600–1599 |

The wider upper band admits the current Forbidden Ascended: Cindrax has at least
1080 overall at its Forbidden tier. The existing Common starters fit Outskirts.
All bands and rates below are catalog configuration, not frontend constants.

## Wild Hunts

1. Choose one of three difficulties and inspect its recommended range.
2. Select a rested squad member to preview its rating and any reward penalty.
3. Find an encounter; show the existing opponent preview and Fight/Decline flow.
4. Prepare and play through the existing battle controls and results.

For each difficulty, enumerate valid catalog Ascended/tier/level combinations
whose overall is within its enemy band. Respect each Ascended's tier ladder and
level cap; the Forbidden Ascended remains Forbidden. Keep encounter tier weights
from the catalog, renormalized over tiers with valid candidates. Choose uniformly
among eligible Ascended within the chosen tier and uniformly among that
Ascended's eligible levels. An invalid or empty configured difficulty fails
catalog validation, rather than looping indefinitely or producing an out-of-band
enemy. Preserve current personality rolls and the per-owner encounter cooldown.
Enemy strength does not scale with the player's highest owned level.

For fighter rating `R` and recommended upper limit `U`:

`penalty = min(0.75, max(0, (R - U) / U))`

`reward_multiplier = 1 - penalty`

Apply this multiplier independently to base fighter XP, Insignia, and essence,
flooring each result once to a whole number. Small essence rewards may become
zero. Calculate the squad XP pool from the reduced fighter XP. Below the lower
limit, show a warning but allow entry with no penalty or bonus.

Capture odds, collected Ascended, spare copies, and personality awards receive no
rating penalty. “Capture chance unaffected” means no added rating modifier;
ordinary HP, tier, and EMBLEM mechanics still apply.

Use the existing reward calculation based on enemy level and tier as the base;
harder enemy ranges naturally yield greater XP and currency. Before starting,
show the rounded percentage reduction and explain that XP, Insignia, and essence
are affected. Round display percentages to the nearest integer, retaining the
full multiplier for rewards. Show actual awarded values in results.

## Ascension Trials

Six permanently visible options: Pure, Abyss, Divine, Crimson, Enchant, Synthetic.
Each requires a rested squad fighter whose catalog type list includes the
selected type. Multi-type Ascended qualify for every matching trial. The backend
checks the selected type at battle start; filtering the picker is insufficient.

Each trial initially has four stages with fixed catalog-configured opponents:

| Stage | Opponent | Tier | Level |
| --- | --- | --- | --- |
| 1 | Guardian | Common | 3 |
| 2 | Bruiser | Rare | 8 |
| 3 | Twoychi | Unique | 15 |
| 4 | Twoychi | Legendary | 25 |

The same initial opponent ladder is used for all six trials. The restriction
applies to the player's fighter; enemy type need not match. This keeps all six
activities valid without adding or reclassifying characters. Configuration
validation checks opponent ids, legal tiers, and level caps.

Stage 1 starts unlocked. Winning a stage unlocks the next stage for that owner and
type. Cleared stages remain replayable. No capture is available: exclude CATCH
from manual legal actions, autonomous decisions, EMBLEM prompts, and server action
acceptance. Trial autonomous preparation requires an equipped personality preset,
but no EMBLEM limit. Manual/Autonomous remains selectable.

Victory gives existing base XP, Insignia, and essence rewards. The first victory
for each owner/type/stage doubles fighter XP, Insignia, and essence; replays use
the base rewards. Apply the normal bench pool to the awarded fighter XP, split
only among other squad members matching the trial type. Ineligible members get
no trial XP and do not enter the divisor. Loss, escape, and forfeit give no
rewards or unlocks. Standard fainting rules apply.

Clear-state writes and reward grants share the terminal battle transaction. The
first-clear bonus is granted once even under retries or simultaneous requests.

Current catalog types: all eight Ascended include Enchant; Twoychi also includes
Divine. Pure, Abyss, Crimson, and Synthetic must show “No eligible Ascended” and
disable preparation. Do not alter the catalog types to fill empty trials. Explain
when a player owns a matching Ascended but needs to equip or rest it first.

## Expeditions

One unclaimed expedition slot per owner. Choose a rested owned Ascended (squad
membership is optional) and a duration of 2, 4, or 8 hours. Initial fixed hourly
rewards are 100 XP and 25 Insignia, identical across durations and independent of
rating/tier. Show the total before departure. No essence, copies, capture,
personalities, or squad XP are awarded.

Departing creates a durable expedition with owner, Ascended id, server departure
and completion timestamps, duration, frozen XP/currency rewards, and claim state.
Creation and removal from the squad commit together. Preserve the relative order
of remaining squad members. An empty squad is allowed by the current service; if
the last member departs, show the empty state and a Collection action to equip
another fighter. Do not substitute a fighter automatically.

Departure is rejected while the owner has an active battle, preserving its squad
XP participants. Fainted Ascended and owners with an unclaimed expedition cannot
depart. A pending encounter may remain pending; its fighter is chosen at start.

Until the rewards are claimed, the dispatched Ascended cannot:

- Start a battle or join/rejoin the squad, including through auto-enrollment.
- Start another expedition.
- Gain a star or raise its tier.
- Learn tree nodes, edit its loadout, save personality presets, or change its
  default preset.

Viewing the Ascended and obtaining spare copies remains possible. Capturing or
buying another copy must not replace its stored expedition state or re-enroll it
into the squad. Expedition locking is per owned Ascended record, which currently
represents one species with spare copies, not individually selectable duplicates.

The visible states are “On expedition” before completion, “Ready to claim” after
completion, and claimed after a successful claim. Server timestamps determine
eligibility; the frontend timer is display only. No worker or background loop is
needed. Progress survives reloads, logout, and server restarts.

At completion, Claim & Return adds the frozen Insignia and uses the existing
level-up helper for XP, respecting level caps. XP/currency writes and claim state
commit atomically. A repeated request cannot grant rewards twice. A claim with a
different idempotency key after claiming returns the recorded receipt without a
second grant. No early recall, automatic renewal, or rewards beyond the selected
duration. Returning does not automatically restore squad membership.

Claiming is allowed during a battle with another fighter: the expedition fighter
is outside the squad and cannot affect the active battle snapshot or bench XP.
Full progress reset deletes expeditions and trial progress with the other
owner-scoped data; its existing explicit confirmation still applies.

## UI and integration

The existing Battle tab becomes the mode hub when no battle is active. Its three
destinations use existing buttons and supporting surfaces, with an expedition
status row when occupied. Mode selection belongs inside screen content; retain
the current header/navigation. Active and resumed battles still open directly
into the existing arena.

- Hunts show three difficulty options, a rating/penalty summary outside the
  existing fighter cards, and the existing encounter/preparation flow.
- Trials show six type choices using existing type symbols, unlocked/cleared
  stages, and the unchanged preview cards filtered to eligible squad members.
- Expeditions show the existing preview card, duration controls, reward estimate,
  departure notice, and then timer/progress/Claim & Return states.
- Collection and details show an expedition status outside the preview card and
  disable prohibited actions with a visible reason. Preserve the details tabs
  and current header treatment.
- Back to modes is available before a battle; during combat retain the current
  finish/forfeit flow. Terminal results return to the originating activity.
- Preserve keyboard controls, focus handling, portrait usability, and established
  preview-card minimum sizes. Use the existing sanctuary asset.

## Backend boundaries and compatibility

Introduce activity context separately from `BattleRecord.mode`, which remains
`manual` or `autonomous`. Persist activity (`hunt`/`trial`/legacy), difficulty or
trial type/stage, and the start-time rating/reward snapshot. Encounters carry
their originating context; clients cannot override it at battle start.

Reuse the battle coordinator/engine, catalog stats, progression helpers,
repository transactions, and idempotent writer. Add focused activity rules,
trial progress, and expedition services rather than duplicate combat engines.
New endpoints expose activity definitions/preparation, trial start/progress, and
expedition read/start/claim. Mutation bodies accept only player choices, never
owner ids, rewards, timing, or capture odds. The exact routes belong in the
implementation plan.

Add incremental storage for activity context, per-owner trial clears, and
expeditions with a database uniqueness constraint on one unclaimed expedition
per owner. Include new tables in fresh databases and owner reset. Existing
encounters and battles retain legacy rewards and capture behavior through
default context; do not reinterpret a battle already in progress on upgrade.
Existing clients omitting a hunt selection may retain legacy encounter behavior
for compatibility, while the updated UI always selects an activity explicitly.

Centralize expedition availability checks and use them for every prohibited
mutation. Guards run inside the same transaction as the mutation to prevent
departure/upgrade, departure/squad, and start/claim races. Existing battle/squad
guards remain in place. API/profile responses expose authoritative availability,
rating, expedition state, and activity origin for the UI.

## Acceptance and validation

1. All three modes are accessible inside Battle without changing the current
   header or preview-card component styles, markup, or asset selection.
2. Hunt enemies stay within the selected range. Penalties are zero at the upper
   limit, increase above it, and stop at 75%. Reward flooring and squad XP match
   the displayed rules; capture probability is unchanged for identical target
   state and EMBLEM input.
3. Trials enforce type and stage eligibility server-side. CATCH fails in manual
   and autonomous play. First-clear bonuses/unlocks are granted exactly once;
   only matching bench members get XP. Empty type options explain eligibility.
4. Departure, squad removal, availability guards, duration validation, and
   returning without auto-equipping work for squad and non-squad Ascended.
5. Expedition claims reject early requests, survive restarts, and cannot pay
   twice with repeated or different keys. XP respects caps. No rewards accrue
   beyond completion and no bench XP is awarded.
6. Migration tests cover fresh and existing databases, including an active
   legacy battle. Reset removes new state. Ownership isolation and concurrent
   mutations are tested.
7. Run relevant Python service/API/storage tests, frontend component/store tests,
   type checking and production build, plus browser checks of the new mode flow,
   expedition locks, and unchanged header/cards at desktop and portrait sizes.

## Delivery order

Build shared activity/rating persistence and Wild Hunts first, then Trials, then
Expeditions and cross-service locks. Finish with integrated browser verification.
All three activities are part of the requested outcome; intermediate milestones
are not task completion. New Ascended, competitive modes, additional expedition
slots, early recall, and changes to header/card design are outside this scope.
