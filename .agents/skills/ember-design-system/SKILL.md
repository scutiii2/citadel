---
name: ember-design-system
description: Use when building or reviewing Citadel UI that uses Ember colors, theme tokens, radius, typography, controls, or focus styles.
---

# Ember design system

Use the target app's `style.css` and shared components as the token and implementation source. For Citadel admin layout and interactions, follow the `ember-admin-ui` skill.

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

- **Controls:** primary action = accent-filled pill (`--radius-full`, weight 600, `--accent-contrast` text). Secondary = outlined pill. Shape and weight rules follow below. Inputs = `--radius-md`, `--border`, `--bg` fill, accent border on focus. On/off = `ToggleSwitch` pill (real checkbox, `role="switch"`), never a bare checkbox. A handful of exclusive choices = segmented pill (accent track, white sliding thumb). Both in [components.md](components.md).
- **Button shape** (ruling): shape follows what is inside, not the page.
  - **Pill** (`--radius-full`): every text button that is one line: primary, secondary, danger, chips, dialog Cancel/Save. One button family, so a primary never sits square beside pill chips.
  - **Circle** (`--radius-full`, width = height): an icon-only button that is the single focal action of its area: Send, Record, Add (floating), a media Play, a dialog or toast close. Never a row of them.
  - **Rounded square** (`--radius-md`, width = height): icon-only buttons that repeat or sit in dense UI: toolbars, table rows, drawer and panel headers, the Show/Hide inside a field, the help icon beside a label.
  - **Rounded rectangle** (`--radius-md`): anything that can wrap to two lines, fills the row, or holds an icon plus text in a card or list tile. A pill with two lines looks broken.
  - Never mix a pill and a rounded-rectangle text button in one view. Radius is a token, never a literal.
- **Button weight** (ruling): the outline shows how important the action is. One accent-filled button per area.
  - **Filled** (accent): the one main action of a view, drawer or dialog.
  - **Outlined** (`--border`, transparent fill): other actions that stand alone or sit beside the filled one: Cancel, Test, Export, Add.
  - **Danger** (red outline, red text): a destructive trigger. The confirm button in its dialog is red filled. Never bare when it is the only way to delete.
  - **Bare** (no outline, no fill; only a label or an icon; hover/focus shows a `--surface` tint): use it only for a quiet, repeated or dense action: row and table actions, toolbar and header icons, nav and tabs, "Back", "Show more", links inside text. A bare text button takes the accent colour or an underline so it still reads as clickable, and a bare icon has a tooltip and `aria-label`.
  - Never bare: the main action, the only button in an empty state, anything that spends money, deletes or sends. Hit area stays 44px on touch even when nothing is drawn.
- **Button behaviour** (ruling, from the ui-button-design checklist):
  - **Hit area:** 44 x 44 px on touch even when the drawn button is smaller (`min-height: 44px` under `pointer: coarse` is in `base.css`). Keep the area clear of neighbouring controls.
  - **Name:** the label says the action and its object ("Create folder", not "Submit"). An icon-only button has an accessible name (`aria-label`, or a visually hidden label).
  - **One primary per action group**, and the other actions are outlined or bare.
  - **Loading:** same width and height, one request, `aria-busy`, and the action stays identifiable to a screen reader (see Busy state).
  - **Focus:** a visible `:focus-visible` ring, not clipped by `overflow`. Use a native `<button>` so Enter and Space work. A wrapper may drop the inner input's outline only if `:focus-within` draws one.
  - **Disabled:** show why and what to do next in text beside the button ("Name your workspace first"), not only in a tooltip. A button that is always clickable and explains the problem on press is also fine. No text is needed when the cause is obvious: a button disabled while busy (the spinner shows it), a Save with nothing changed (the dirty-only pattern), a move or remove at the end of a list, or a one-field form whose empty, labelled field is the reason. In a drawer use the footer `note` (`RecordDrawer`); elsewhere use `.disabled-reason`.
- **Carousels** (ruling): native horizontal scroll with `scroll-snap-type: x mandatory`, cards `flex: none` with `scroll-snap-align: center`, and half the free width as padding at both ends so the first and last card can centre. Emphasis is a CSS view timeline (`animation-timeline: view(inline)`, declared after the `animation` shorthand) over `transform: scale(.85 -> 1)` and `opacity` only, so card size never changes. Wrap it in `@supports (animation-timeline: view())`. No JS scroll listener. Every card stays reachable by keyboard with a visible focus ring. None exists yet.
- **Toggle icons** (ruling): a native `<button>` with a stable name ("Favorite", "Expand drawer", "Sidebar") and `aria-pressed` (on/off) or `aria-expanded` (opens something) set from the real state; a tooltip `title` may still change; never swap the name as well, that announces the state twice. The glyph is `aria-hidden`. Media Play/Pause keeps the usual swap of name with no state attribute. Our icons are stroked inline SVG, so the on state is the same path with `fill: currentColor` and a 0.15s transition; do not load Material Symbols or any icon font. Keep the hit area fixed while the glyph changes.
- **Progress** (ruling): a determinate bar is a native `<progress>` or `role="progressbar"` with a name (`aria-label`) and `aria-valuenow/min/max`; the visible percent, the width and the semantics use the same value. Flat is the default. A wavy filled part (SVG mask of one 20px period, `mask-position` looped over exactly 20px, flat remaining track, wave and end dot `aria-hidden`) is allowed for long-running jobs only (download, merge); show a flat fill where masks fail, collapse the gap at 0% and 100%.
- **Sliders** (ruling): a native `<input type="range">` with a name stays the source of truth (its label, or `aria-label`). A custom split-track look overlays it: the input is transparent but focusable and keeps a generous hit area, the decorative layers take no pointer events, one CSS variable `--v` (0 to 100%) places the handle, and the wrapper draws a focus ring on `:focus-within` (`:focus-visible`). Clamp the track pieces; hide the stop dot when the remaining piece is too short. Check arrow keys, Home/End, touch and both ends.
- **Waiting** (ruling): an indeterminate wait (an AI answer, a background task) shows text in a `role="status"` region ("thinking ...", "Preparing response") and may add a decorative 4px gradient bar (`aria-hidden`, tile loop of exactly one tile, feathered ends by `mask-image`, fixed width). It stops when the answer streams, completes, fails or is cancelled, and appearing or disappearing never shifts nearby content. Announce each change once, not each animation cycle.
- **Reduced motion** (ruling, overrides the pasted skills above): none of these patterns gets a `prefers-reduced-motion` branch, ever. Animations always play (workspace `AGENTS.md`, "No reduced motion").
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
