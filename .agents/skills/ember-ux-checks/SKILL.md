---
name: ember-ux-checks
description: Use when reviewing or polishing Citadel UI for forms, contrast, link/button/tab semantics, decoration, scrolling, auto-moving content, or hierarchy and proximity. Brain-derived UI/UX checks that supplement the Ember design system.
---

# Citadel UI/UX checks

Distilled from `Brain/Maps/UI UX Frontend Rulesets.md` (consult it for rationale when available). These supplement `ember-design-system` and `ember-frontend-design`; the no-reduced-motion rule and other project rules win on conflict.

- **Forms:** ask only for what the task needs. Use the right `type`, `autocomplete` and `inputmode`; allow paste. Validate on blur or submit, not while the user is still typing a valid value. Put the error beside its field, tie it to the control (`aria-describedby`, `aria-invalid`) and keep entered values.
- **Contrast:** test real foreground/background pairs, including hover, focus and tinted `color-mix` fills: 4.5:1 for text, 3:1 for large text and UI boundaries. Check hierarchy in grayscale before relying on hue.
- **Semantics:** links for destinations, buttons for actions. Tabs that swap panels need tab semantics and arrow-key behaviour, not link markup. A popover or tooltip is not a modal: no focus trap, no scroll lock. A tooltip supplements a label, never replaces it.
- **Decoration:** glow, glass, shine, neon and gradients sit on their own layer with `pointer-events: none`. They must not cover controls, change reading order or clip focus outlines, and need a readable plain fallback. Keep them optional; prefer existing tokens.
- **Scroll:** the view scrolls, not the page. Sticky headers must not cover focused fields or eat a small viewport. Prefer pagination or Load more over infinite scroll when users need a stable position or a reachable footer; keep position, loading and error states. A wide track or table is a labeled local scroller reachable by keyboard.
- **Auto-moving content:** anything that moves by itself for over 5 seconds beside other content (marquee, carousel, ticker) needs a visible pause/stop control; hover-only pause is not enough. Hide decorative duplicates from assistive tech.
- **Design-law prompts:** proximity (does spacing show grouping?), Von Restorff (does the standout element deserve it?), Hick (group or reveal choices progressively without hiding needed ones), Jakob (does it behave like the familiar pattern?). Prompts, not numeric caps.

