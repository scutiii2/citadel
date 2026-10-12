# Ascension: autonomous policy redesign

Date: 2026-10-12. Status: proposed, built after `2026-10-12-ascension-ability-trees-design.md`.

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
- Utility of an action `a` inside its category: `style_affinity(personality, a)` weighted highest, a small potency term
  (`log` of the percentage ratio to the category best), and a repeat penalty `repeat_factor ^ repeats` that is stronger
  than today's. A softmax temperature in the catalog keeps the pick random.
- **Style.** Each ability node has an optional `style` tag from a small set (for example `burst`, `steady`). Each
  personality lists the styles it likes in `ascension_catalog.json`. No tag means neutral. The tag set and the mapping
  are my proposal (?); they need a design pass with the tree content.
- The audit records both stages: category probabilities, then per-category action utilities and probabilities.

## Config

`policy` in `configs/ascension_catalog.json` gains `style_weight`, `potency_weight`, `temperature` and a
`personality_styles` map. The old coefficients stay as the category situation values.

## Tests

- a 3-ATTACK loadout keeps the category probabilities the situation and personality ask for (property test: moving
  actions between categories without changing categories present leaves the category probabilities unchanged);
- a category with one action behaves as today;
- repeats lower an action inside its category and still leave other categories alone;
- style affinity shifts the pick toward the liked style, and temperature 0 picks the best, high temperature approaches uniform;
- the audit shape;
- the Laya-fed evaluation (`situation_eval`) still runs.

## Open questions

- The style tags and the personality mapping (above).
- Whether the wild side shares the same utility or keeps a plain pick. Drafted: the same policy for both sides.
- Fit rules (skip a stacked buff, go for the kill) were dropped for now because variety was chosen; they can return as a
  later utility term.
