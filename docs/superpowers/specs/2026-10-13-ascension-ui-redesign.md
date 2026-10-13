# Ascension UI redesign

Approved direction: the steel-and-copper pixel-art UI shown in the design references at `D:/User/Documents/Programming/Python/MCPServer/apps/ascension/design_references`, with compact item grids, strong copper selection states, character cards, and contextual inspectors.

- Main menu: Quick Battle is primary; explicit Collection, Shop, How to play; disabled Tavern teaser with lock and Coming soon. No Continue button for existing accounts. New accounts retain starter creation.
- Header: back button immediately before ASCENSION on sub-screens; return navigation never forfeits a battle. Wallet and current destination remain visible.
- Preserve existing EMBLEM and Ascension Type artwork and their detailed/flat variants.
- Every character display uses only `sprite_battle.webp`. No fallback to preview/main sprites and no deletion of those files. Preserve the user's modified character files. Do not generate characters.
- Shared portrait cards use a steel frame, readable name/tier/level and type symbols. Preserve missing-character concealment.
- Collection: filter rail, squad strip and compact collected grid; selected character inspector and full details/progression views. Preserve squad operations, upgrades, ability tree, personalities and presets.
- Shop: Buy/Sell modes, category/rarity/search filters, compact cards and persistent basket; editable quantities, stock and budget limits, total and resulting balance, review before selling. Only spare copies may be sold. Reuse existing APIs, process sequentially, stop on failure, report completed trades and preserve remaining selections. Do not claim atomic execution.
- Encounters/battle/results: contextual plan inspector, fighter stage and action strip, round log and reward summary; preserve server legality, cooldowns, autonomous requirements, catch prompt and all result types.
- Tavern stays disabled; no recruitment API or gacha mechanics.
- Responsive layouts and keyboard access must remain usable. Existing game rules and truthful live values override illustrative mockup text.

Verification: focused behavior regressions, complete frontend unit suite, TypeScript/Vite production build, Playwright flow and screenshots at desktop/mobile when environment permits.
