# Ascension: autonomous policy redesign

Date: 2026-10-12. Status: built, follows `2026-10-12-ascension-ability-trees-design.md`.

## Why

With loadouts, an Ascended can carry 3 ATTACK abilities and no DEFENSE. `ActionPolicy.probabilities` gives every legal
action its own weight (`situation_value(category) x personality x potency x repeat penalty`), and potency is only relative
to the category mean. So the probability of a category grows with the number of actions in it:
- today ATTACK already has 2 actions (basic attack and ability) against 1 DEFENSE and 1 SUPPORT;
- a 3-ATTACK loadout would give ATTACK 4 of 5 shares whatever the situation or personality says.

The policy also ignores what an ability does (an active buff or defense, a likely kill, the SUPPORT stat).

## Decisions

- Keep the inputs: Laya or heuristic situation (`danger`, `aggression`, `advantage`), the mood draw, personality weights,
  the seeded draw, the audit. Only the probability step changes.
- Two stages:
  1. **Category.** `situation_value x (1 + gain x personality weight)` for each category that has a legal action,
     normalized over those categories. The number of actions in a category no longer matters. FEAR (flee) and
     INTERCEPT (catch) stay categories as today.
  2. **Action inside the category.** A softmax over a utility. The player chose personality-driven variety, so potency
     matters little and personality style and repeat avoidance matter most.
- Utility of an action inside its category combines a small potency term (`log` of its percentage relative to
  the category mean), any `pick_by_percentage` override, and a repeat penalty. Softmax temperature keeps the pick random.
- Decided: no style tags; `pick_by_percentage`, `repeat` and the potency term give the variety.
- The audit records category probabilities, final action probabilities and fired rules.

## Match reading and mood (added 2026-10-12)

Personalities now read the match, and keep a hidden mood. Both are derived from public state and `state.history`
(attack events carry `damage` and `target_hp`), so nothing new is saved and a restarted battle decides the same way.

**Match state**, recomputed at each decision for one side:
`own_hp`, `enemy_hp` (fractions), `lead = own_hp - enemy_hp` (-1 to 1), `trend` (change of `lead` over the last 2 rounds),
`round`, `own_streak` (category and length), `enemy_last` (the enemy's last category), `hit_taken` (own HP lost last round
as a fraction of max HP), `enemy_low` (`enemy_hp < 0.3`).

**Mood meters**, each 0 to 1, replayed from the history round by round:
- `rage`: rises with `hit_taken`, halves each quiet round.
- `confidence`: starts at 0.5, rises when `lead` grew in a round, falls when it shrank.
- `nerves`: rises while `lead < 0` or own HP is low, falls while `lead > 0`.

Which instance leads the round (the current mood draw) is unchanged. Mood meters are the new, separate state.

**Rules.** A personality is a list of rules in `ascension_catalog.json`, so balance stays in data:

```json
{"id": "ANXIOUS", "rules": [
  {"when": {"nerves_over": 0.5}, "chaos": 0.6},
  {"when": {"lead_over": 0.0}, "multiply": {"DEFENSE": 1.2}}]}
```

A rule has a condition (`lead_over`/`lead_under`, `own_hp_under`, `enemy_low`, `rage_over`, `confidence_over`,
`nerves_over`, `hit_taken_over`, `streak_over`, `round_under`, `round_over`, `enemy_last_is`, or none), and an effect:
- `multiply`: category multipliers on stage 1. A factor f at tier t becomes `1 + (f - 1) * t / 3`. Tier scales strength.
- `chaos` (0 to 1): stage 1 blends the probabilities toward uniform over the legal categories and shifts mass to the
  least likely ones. The seeded draw keeps it reproducible.
- `counter`: moves mass to the category that beats `enemy_last` (see Cunning).
- `copy_enemy`: moves mass to `enemy_last` (Mimic).
- `break_streak`: after a hidden streak length, forces the least likely category once, then resets (Weird). After tuning it skips FEAR and INTERCEPT unless nothing else is left, so a turn is never a retreat.
- `stay`: boosts the category chosen last (Stubborn).
- `repeat`: replaces the repeat factor (Stubborn removes the penalty).
- `pick_by_percentage`: `high` or `low` in stage 2 (Gambler).

Several personalities add their multipliers per category as today, then chaos and break effects apply last. Anything not
listed is not allowed in a rule; catalog validation rejects unknown conditions and effects.

**First personalities.** The 8 existing ones stay unchanged. 14 new:

| Id | Behaviour |
|---|---|
| WEIRD | Follows its preference, then after a hidden streak of 2 to 4 rounds jumps to its least likely category, then resets. |
| ANXIOUS | Normal while winning. When `nerves` is high (losing, low HP), chaos 0.6: flat odds, mass on FLEE, SUPPORT and CATCH. |
| RECKLESS | ATTACK x1.6 as own HP falls below 0.5, and danger is ignored. |
| VENGEFUL | After `hit_taken > 0.15`, ATTACK x1.8 for 2 rounds (the `rage` meter). |
| BERSERKER | ATTACK scales with `rage`. FLEE is removed above `rage` 0.6. At very low HP it also turns reckless. |
| COCKY | ATTACK x1.4 and DEFENSE x0.6 when `confidence` is high. When it starts losing it adds chaos 0.3. |
| COMEBACK | ATTACK and SUPPORT x1.4 when `lead < 0`. Plays plain while ahead. |
| CUNNING | `counter`: DEFENSE after the enemy's ATTACK, ATTACK after the enemy's SUPPORT or DEFENSE. |
| MIMIC | `copy_enemy`. |
| PATIENT | SUPPORT and DEFENSE x1.5 before round 4, ATTACK x1.5 afterwards or when `enemy_low`. |
| OPPORTUNIST | ATTACK and CATCH x1.8 when `enemy_low`, DEFENSE x1.2 otherwise. |
| STUBBORN | `repeat`: no repeat penalty, stays on the previous category. |
| GAMBLER | `pick_by_percentage`: `high` when `lead < 0`, `low` when `lead > 0.3`. |
| STOIC | No rules. The control group. |

The numbers are first guesses (?). The existing situation read from Laya or the heuristic stays; rules add to it.

**Audit.** It now records the match state, the mood meters, and each rule that fired.

**Tests for this section.** One test per condition and effect; one per new personality showing the intended shift
against the same state without it; mood replay is deterministic and identical after reloading the battle; unknown
conditions are rejected by catalog validation; Weird's streak resets; Anxious has no chaos while winning.

## Config

`policy` in `configs/ascension_catalog.json` gains the mood constants (decay, thresholds), the `rules` of every personality, and `potency_weight`, `pick_weight`, `temperature` and `counter_boost`. The old coefficients stay as the category situation values.

## Tests

- a 3-ATTACK loadout keeps the category probabilities the situation and personality ask for (property test: moving
  actions between categories without changing categories present leaves the category probabilities unchanged);
- a category with one action behaves as today;
- repeats lower an action inside its category and still leave other categories alone;
- `pick_by_percentage` shifts the pick toward high or low percentages; temperature is positive and high temperature approaches uniform;
- the audit shape;
- the Laya-fed evaluation (`situation_eval`) still runs.

## Open questions

- Whether the wild side shares the same utility or keeps a plain pick. Drafted: the same policy for both sides.
- Fit rules (skip a stacked buff, go for the kill) were dropped for now because variety was chosen; they can return as a
  later utility term.
- Mood meter formulas (rates, decay) are first guesses (?).
