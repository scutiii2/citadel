# Sanctuary screens implementation plan

> **For agentic workers:** Use superpowers:executing-plans for inline execution. The user approved the revised mockups and explicitly requested implementation.

**Goal:** Apply the approved navy sanctuary design to collection, shop, encounter preparation, active battle and results.

**Architecture:** Preserve Vue/Pinia stores and trading/combat APIs. Use a shared scene and theme tokens, component-owned layout styles, and the existing artwork. Keep the Ascended details design intact.

**Tech stack:** Vue 3, TypeScript, Vite, Vitest, Playwright.

**Spec:** Approved collection mockup and revised shop/battle/results mockups in this chat. Cool navy sanctuary, serif ivory headings, peach underlines, open groupings, minimal panel strokes.

## Global constraints

- Third navigation destination is disabled Tavern, labelled as locked/coming soon.
- Visible currency icon and numeric amount immediately precede the separate Shop button. No visible currency-name text in the header.
- Portrait navigation uses icons without visible labels; accessible names remain.
- Preserve buy/sell, confirmation, retries, stock checks, battle modes, preset selection and capture behavior. Mockup Currency tab maps to existing Sell behavior rather than inventing a currency-purchase feature.
- Preserve artwork and the three-tab Ascended details modal.
- Work in the existing isolated worktree; no merge or push requested this turn.

## Tasks

- [x] 1. Shared sanctuary asset, theme and shell. Update shell tests for numeric balance and separate shop action; run failing tests, implement and verify. Add responsive nav labels and original serif typography.
- [x] 2. Collection layout. Add page title and resource header, soft filter rail and open card sections; preserve filtering, drag/drop and detail modal. Verify collection tests and responsive rendering.
- [x] 3. Shop layout. Keep buy/sell semantics; introduce compact filters and a portrait basket disclosure bar without duplicating checkout controls. Test disclosure and basket state preservation; verify trading suites.
- [x] 4. Encounter, battle and result layouts. Add readable preparation title and saved-default annotation. Restyle arena and outcome/reward rows without changing mechanics; verify battle tests.
- [x] 5. Browser validation at desktop and portrait sizes, production build and affected tests. Review whole diff and report evidence.

## Review focus

- Narrow portrait headers must keep wallet and Shop adjacent, labels hidden, buttons usable.
- Shop basket remains reachable with zero items and errors; opening/closing must not reset state or interfere with sale confirmation.
- All battle states, including losses/no rewards, remain readable and navigable.
- Long names/filter lists and large currency balances must not cause horizontal page overflow.
- Existing modal styling, animation and keyboard access must remain usable.

## Progress

Initial inspection: worktree clean at e999f92; existing main checkout contains separate work and is not being modified. Shared interfaces are existing theme tokens and shell slots; no API changes planned.

Completed inline. Shared sanctuary asset generated with the built-in tool and converted to WebP (270 KB); exact prompt recorded alongside it. Existing Ascension icon reused from the main checkout without modifying the source. The prior preview-card paths referenced folders absent from this checkout: corrected them to the shipped ascended_card assets and updated the existing failing asset tests.

Validation: 292/292 Vitest tests pass; 19/19 Edge Playwright tests pass across the existing flow, details, header and new sanctuary suites. Desktop, tablet portrait and phone widths checked, including real artwork, basket dismissal/state preservation, active battle, capture/victory/loss and all detail tabs. Production build passes. Browser screenshots saved to the chat visualization directory.

Final review: fresh read-only reviewer found portrait checkout feedback hidden behind the basket modal. Success and failure regression tests reproduced it; feedback now appears within the open basket and returns to the page when dismissed. Both regression tests and full suite pass. No other significant finding. Existing main checkout remains untouched; changes are uncommitted in the isolated feature worktree.
