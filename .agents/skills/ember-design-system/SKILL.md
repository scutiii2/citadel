---
name: ember-design-system
description: Use when building or reviewing Citadel UI that uses Ember colors, theme tokens, radius, typography, controls, or focus styles.
---

# Ember design system

Use the target app's `style.css` and shared components as the token and implementation source. For Citadel admin layout and interactions, follow the [approved admin design reference](../ember-frontend-design/SKILL.md#admin-design-reference).

**Core idea:** one coherent system, not per-component choices. Pick tokens and patterns first, write styles second. Never hardcode a colour or a pixel radius.

## Start a new UI

1. Copy [tokens.css](tokens.css) into the new project's global stylesheet (or import it). It holds every colour, font, radius and the `--rail-height` token, plus the base reset and app-shell rules.
2. Add theme switching (section "Theme" below).
3. Build from the patterns in [components.md](components.md): copy the CSS, keep the tokens.
4. Check against the rules and checklist below.

In existing Citadel apps, reuse the target app's tokens and components.

## Foundations

**Colour** - every token is `light-dark(light, dark)`, so one declaration themes both. Roles:

| Token | Use |
|---|---|
| `--bg` / `--surface` | page / cards, panels, rail, modals (one step above bg) |
| `--text` / `--muted` | body / secondary text, icons, descriptions |
| `--border` | every 1px outline and divider |
| `--accent` (ember orange `#b23d06` / `#ff7a33`) + `--accent-contrast` | primary action, active state, focus ring, links |
| `--danger`, `--warning`, `--success` | destructive, caution, positive; status red is `--status-failed` |
| `--code-bg` | code, chips, inline tags |

Rules: tinted fills use `color-mix(in srgb, var(--x) N%, var(--bg))`, never a new hex. Colour is never the only cue: pair a status colour with an icon and a label. Chart series colours are categorical slots, validated on both surfaces (see the `dataviz` skill).

**Type** - `--sans` system stack at `15px/1.55`; `--mono` for ids, paths, code. Scale by `em` relative to the parent: body 1em, secondary 0.9em, meta 0.85em, badges 0.75em. Headings are modest: page `h2` 1.2em, section `h3` 1em, weight 600.

**Radius** - pick by element size, never a literal px:

| Token | px | Elements |
|---|---|---|
| `--radius-sm` | 4 | chip, badge, small tag |
| `--radius-md` | 8 | input, row, icon button, tooltip |
| `--radius-lg` | 12 | card, panel, danger zone |
| `--radius-xl` | 16 | modal, sheet |
| `--radius-full` | 9999 | single-line pill button, avatar, toggle, dot only |

A nested corner is `calc(outer - padding)`. An element flush to an edge is square on that side. Only 10-11px chart marks keep a literal `2px`.

**Layout.** Use `PageLayout` for the view's geometry and scrolling. Let the view own its scroll area. Follow the admin design reference for header, collapsible sidebar, panel toolbar, and drawer placement.

**Surfaces** - cards: `1px solid --border`, `--radius-lg`, `--surface`, `12px 14px` padding. Raised tiles use a soft shadow (`0 2px 10px rgba(0,0,0,.14)`, lifting 2px on hover). No heavy shadows elsewhere; modals use a `rgb(0 0 0 / 45%)` backdrop.

**Motion** - 0.15s ease for hover and state, 0.18s for sliding thumbs; animations always play, so never add a reduced-motion setting or `prefers-reduced-motion` media query. Animation follows state; it never delays or replaces the action.

**Focus** - `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px }` on every interactive element. Never `outline: none` without a replacement.

## Interaction rules

- **Controls:** primary action = accent-filled pill (`--radius-full`, weight 600, `--accent-contrast` text). Secondary = outlined pill. Inputs = `--radius-md`, `--border`, `--bg` fill, accent border on focus. On/off = `ToggleSwitch` pill (real checkbox, `role="switch"`), never a bare checkbox. A handful of exclusive choices = segmented pill (accent track, white sliding thumb). Both in [components.md](components.md).
- **Confirmations:** never the browser's `confirm()`. Use an in-app modal; friction scales with severity. Severe actions (delete account, delete something in use, delete all) require typing the name or phrase (`requireText`) before the confirm button enables. Destructive buttons are red-outlined pills and sit in a red-tinted **Danger zone** block, last in the form.
- **Settings:** browser-only preferences apply instantly. Server settings stay in a draft until Save. In admin panels, follow the shared dirty-only Save slot or drawer footer pattern. A setting that differs from its default shows an accent dot and its own reset button.
- **Busy state:** disable the control, set `aria-busy`, show progress on the control itself (spinner ring, drawn globally for `button[aria-busy="true"]` in ember, so no per-component copy); ignore clicks while busy.
- **Icons:** stroked 24x24 SVG path data, `stroke: currentColor; stroke-width: 1.8; fill: none; round caps and joins`. Icon-only controls get a name on hover and keyboard focus (`data-label` tooltip) and an `aria-label`.
- **Bottom sheets:** on shells with mobile bottom navigation, place sheets above `--rail-height`.
- **Persistence:** theme and local preferences in `localStorage`, every read and write in try/catch (storage may be blocked); a failed read means the default.

## Theme

`color-scheme: light dark` on `:root` follows the system. A user override sets `document.documentElement.style.colorScheme` to `light` or `dark`; "system" restores `light dark`. The toggle cycles system, light, dark and persists the choice per browser. Because every token is `light-dark()`, no per-theme stylesheet exists. Apply the saved theme before the app mounts to avoid a flash. See `apps/ember/src/composables/useTheme.ts`.

## Review checklist

- [ ] No hex colour or literal radius outside `tokens.css`
- [ ] Looks right in light, dark, and forced-colour scheme override
- [ ] Desktop, 768 and 375 widths; no horizontal page scroll
- [ ] Every interactive element has a visible focus ring and a name
- [ ] Status shown by icon and text, not colour alone
- [ ] Destructive action: modal, red Danger zone, type-to-confirm if severe
- [ ] No `prefers-reduced-motion` rule or reduced-motion setting
- [ ] Scoped component CSS that a parent page also styles uses a more specific selector (`button.delete-button`, not `.delete-button`): a later same-specificity rule had overridden its padding

## Common mistakes

| Mistake | Fix |
|---|---|
| `border-radius: 10px` | Use the nearest token by element size |
| Separate dark-mode stylesheet or `.dark` class | Use `light-dark()` tokens |
| Native `confirm()` or `alert()` | In-app confirm modal |
| Page-level scroll, sticky headers fighting it | Scroll the view area only |
| New accent shade for hover | `color-mix` from `--accent` or change border to accent |
| Fixed bottom sheet at `bottom: 0` on mobile | `bottom: var(--rail-height)` |
