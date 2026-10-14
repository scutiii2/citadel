# Ascension UI design guide

This is the visual reference for Ascension screens, approved on 2026-10-14. Use it for new screens, UI changes, and visual reviews. It describes the sanctuary design implemented in the collection, shop, battle screens, and Ascended details.

For visual decisions, this guide supersedes older forge-style mockups and style-sheet examples. Game rules, costs, limits, and available actions come from the catalog and server responses. Explicit user requests take precedence over this guide.

## Visual direction

Ascension should feel like a quiet, ancient sanctuary: deep navy stone arches, subtle cyan reflections, sparse distant torchlight, ivory headings, and restrained peach accents. Character artwork and ornate trading cards carry the strongest detail and color.

- Use one continuous scene behind a screen, with dark overlays where content needs contrast.
- Group content through spacing, headings, and thin dividers. Use translucent navy surfaces for supporting controls and sidebars.
- Avoid nested outlined rectangles, heavy inset frames, thick blue borders, and a separate opaque box around every row.
- Keep the ornate tier-colored card frames. These are intentional artwork and should remain distinct from the restrained surrounding interface.
- Reserve prominent peach fills for the main action or selected segmented control. Active navigation uses a peach underline.
- Keep backgrounds quieter than text, controls, and character art. Avoid bright foreground torches, dense decorative clutter, or gold glows around ordinary controls.

## Palette and typography

Reuse the tokens in [theme.css](web/src/components/theme.css), scoped to `.em-root`. Ascension has its own theme within Ember.

| Purpose | Token | Current value |
| --- | --- | --- |
| Base | `--em-bg` | `#101720` |
| Supporting surfaces | `--em-header`, `--em-panel`, `--em-raised` | `#141e28`, `#1b2733`, `#253443` |
| Main text | `--em-text` | `#f5f0e6` |
| Secondary text | `--em-muted` | `#b8c6d2` |
| Accent | `--em-accent` | `#f3b47a` |
| Text on accent | `--em-on-accent` | `#20180f` |
| Control borders | `--em-border` | `#36546a` |
| Quiet dividers | `--em-divider` | `#29425599` |
| Success / danger / warning | `--em-success`, `--em-danger`, `--em-warning` | `#9ad5ac`, `#ff9b9b`, `#f0cc85` |

- Use `--em-font-heading` (Georgia with serif fallbacks) for page titles, character names, and section headings.
- Use `--em-font-body` (Inter with system fallbacks) for controls, descriptions, and numbers. Use tabular numbers for balances and progress values.
- Keep Silkscreen for existing pixel-art card labels and appropriate compact game labels; large screen headings use the serif treatment.
- Names have no decorative underline or spelling-style red underline.
- Reuse the spacing scale: 4, 8, 12, 16, 24, 32, and 48 pixels. Leave more space between sections than between related rows.
- Use radius tokens. Ordinary Ascension controls use `--em-radius`; reuse the established shared radius tokens where appropriate, such as dialogs. Do not invent literal corner radii per component.
- Use the established tier colors for Common, Rare, Unique, Royal, Legendary, and Forbidden. Always include text or another identifying cue alongside color.

## Shared navigation

Desktop navigation order is **Battle**, **Collection**, **Tavern**. Tavern remains visibly disabled with a lock and an accessible “Locked / Coming soon” description until its feature is implemented. It is not Archive.

The right side shows the **currency icon and numeric balance immediately to the left of a separate Shop button**, followed by Help and Settings. Do not display the word “Insignia” beside the header balance; retain an accessible name that explains the amount.

In portrait layouts, use icon-only navigation buttons with accessible names. Keep the selected-state indicator, Tavern lock, and balance-to-Shop ordering. Desktop labels should not force a portrait header to overflow.

References: [App.vue](web/src/App.vue), [EmShell.vue](web/src/components/EmShell.vue), [EmTabs.vue](web/src/components/ui/EmTabs.vue).

## Collection

- Start with “Your Ascended,” a short introduction, and compact essence counters.
- Use a softly shaded filter rail on desktop. Portrait layouts expose configuration through a disclosure control.
- Present the squad first, then collected groups, then uncollected cards. Separate sections with headings and subtle dividers.
- Keep squad slots, tier frames, card stats, selection, and drag-and-drop behavior recognizable.
- Portrait squad strips can scroll horizontally; the overall page should not overflow horizontally.

Reference: [CollectionPanel.vue](web/src/components/CollectionPanel.vue), [collectionScreen.css](web/src/components/collectionScreen.css).

## Ascended details

The modal header shows the **Ascended name**, with **Ready for battle** directly beneath it. Show the actual fainted/rest countdown there when applicable. Do not show an “ASCENDED” eyebrow or spare-copy count in this header.

Keep the tabs in this order: **Overview → Progression → Ability tree → Personalities**.

### Overview

- Make the character's `sprite_main_card.webp` the main visual.
- Keep stats and squad membership controls in the left rail.
- Place six shaped ability positions near the lower left: two passive circles and four active octagons. Availability follows the actual loadout slots; unsupported positions remain unavailable.
- Show five personality preset choices near the lower right, beside the three personality names from the selected preset.
- Selecting a preset here saves that Ascended's battle-start default. Battle preparation can override it without changing the saved default.
- Do not restore the “Progression & abilities” expandable button.

### Progression

- Put copies, current-tier essence, star progress, upgrade costs, and ascension controls in this tab.
- Show the current tier, earned and unearned star milestones, and the next tier when one exists. Long star ladders use a compact progress bar.
- Show each upgrade cost alongside the player's available amount. Use the server's eligibility flags and busy state to enable actions.
- On desktop, put level/XP progress and supporting character art in the right column. Keep innate passive and foundation ability descriptions available as supporting information.
- Stack the content in portrait layouts. All actions and costs must remain reachable through scrolling.
- Handle maximum stars, no next tier, and maximum level explicitly. Do not invent a target tier, upgrade cost, or stat bonus.
- Keep upgrade success messages and errors inside the modal.

### Ability tree and Personalities

- Ability tree: preserve the branching graph, shaped nodes, equipment slots, selected-node details, requirements, and zoom controls. State and selection must stay clear over the dim background.
- Personalities: use a five-preset selector, three equipped slots with descriptions, and a searchable/filterable library. Preserve save/discard behavior and protection against switching away from unsaved edits.

References: [ascendedDetails.css](web/src/components/ascendedDetails.css), [AscendedProgression.vue](web/src/components/AscendedProgression.vue), [TreeTab.vue](web/src/components/TreeTab.vue), [PresetEditor.vue](web/src/components/PresetEditor.vue).

## Shop

- Put **Offers**, **Sell Copies**, and **search on the same row**, including narrow layouts. The refresh timer may occupy a second row when space is limited.
- In Offers → All Items, separate **Ascended offers** and **EMBLEMs** into clearly headed groups. Search applies to both; omit groups with no matching items.
- Keep category selection available. Show the rarity filter only in Sell Copies.
- Use open item layouts with sprites, names, tier cues, stock/copy information, prices, and compact add/quantity controls. Avoid enclosing every item in a strongly outlined tile.
- Desktop uses a supporting basket rail with a reachable total and checkout action. Portrait uses a sticky basket bar that opens a native modal.
- Checkout feedback must be visible inside the open basket modal. Preserve quantities on dismissal, sale confirmation, stock checks, partial results, and retry behavior.
- The second mode sells spare copies. Do not rename it “Currency” or imply a currency-purchase feature unless that feature is explicitly added.

References: [ShopPanel.vue](web/src/components/ShopPanel.vue), [shopPanel.css](web/src/components/shopPanel.css).

## Encounters, battles, and results

- Encounter preview: emphasize the opponent, tier, level, and Fight / Decline choice over the shared sanctuary. Opponent personalities remain hidden until capture.
- Preparation: show both fighters and their health side by side, then squad selection. Put the battle plan beside the arena on desktop and below it in portrait layouts.
- Keep Manual / Autonomous, the chosen personality preset, saved-default annotation, personality preview, and EMBLEM limit readable. Begin battle is the primary action.
- Active battle: keep character sprites, health, actions, effects, and round information legible. Category colors may identify actions without turning the entire screen into bright colored panels.
- Results: use a serif outcome heading, featured character, open reward rows, and compact squad XP bars. Capture also shows copies and revealed personalities, with the awarded personality distinguished.
- Keep Back to encounters easy to find. Loss, escape, no-reward, and fainted states need the same care as victory and capture.

References: [EncounterPanel.vue](web/src/components/EncounterPanel.vue), [BattleArena.vue](web/src/components/BattleArena.vue), [BattleResult.vue](web/src/components/BattleResult.vue).

## Artwork and asset ownership

The shared sanctuary scene is [sanctuary.webp](web/src/assets/scenes/sanctuary.webp); its generation prompt is [sanctuary.prompt.md](web/src/assets/scenes/sanctuary.prompt.md). Existing detail-tree/personality treatments also use [ascended-sanctum.png](web/src/assets/scenes/ascended-sanctum.png). Reuse these assets before generating another background for a matching screen.

Keep per-Ascended assets under `ascended/<id>/`, served as `/ascended/<id>/<filename>`. Follow [ART_GUIDE.md](ascended/ART_GUIDE.md) and [AGENTS.md](AGENTS.md) for artwork roles and placement. Overview uses main-card art; battle uses battle art or its supported animation. Some existing preview/shop renderers currently use battle art through the sprite helper: preserve their established behavior during styling work unless changing artwork selection is part of the request.

Shared tier card fronts/backs live in `web/src/assets/ascended_card/`; brand assets live in `web/src/assets/brand/`. Reuse original artwork and preserve its proportions and transparency. Mockup illustrations are visual references, not replacements for the shipped sprites.

Ascended tier icons live in `design_references/tiers/tier_<tier>.webp` and are bundled through `EmTierIcon`. Use them beside tier names through `EmTierBadge`, or as larger tier markers in battle and progression with a visible tier label nearby. Capture EMBLEMs and essence retain their own artwork. Numbered personality tiers are a separate scale and do not use Ascended tier icons.

## Review before finishing

1. Compare the screen with the sanctuary direction above: restrained surfaces, clear hierarchy, readable text, and artwork as the focus.
2. Check desktop, tablet portrait, and narrow portrait layouts. Recent browser checks use widths of 1440, 768, and 375 pixels. Check horizontal overflow and access to controls below the fold.
3. Keep accessible names, visible keyboard focus, semantic controls, native modal focus handling, and readable disabled/selected states. Use the existing 44-pixel action target where practical.
4. Verify real catalog/server data, including empty collections, long labels, missing artwork, insufficient resources, capped progression, and busy/error states relevant to the change.
5. Run affected component tests, browser checks for changed layouts, and the production build. A visual rework must preserve the existing gameplay operations.
6. When a new design decision is approved, update the relevant section of this guide so it remains the shared reference.
