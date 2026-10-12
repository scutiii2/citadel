# Battle preparation matchup implementation

**Approved design:** Cinematic player-versus-wild artwork, a compact horizontal squad, grouped battle settings and a prominent start action. Proposal: `battle-preparation-proposal.html` in the session's visualizations directory.

**Scope:** Ascension web only. Keep battle payloads, squad order, fainting restrictions, current-state readiness checks, and autonomous requirements. Use real catalog artwork, tiers, types and calculated player stats; do not expose wild personalities. Keep the existing look and encounter preview stages.

- [x] Add regression tests for both matchup fighters, real stats, artwork fallback, preset selection, busy controls and unchanged start payloads; run them red.
- [x] Add a focused BattleMatchup component and replace setup with the approved horizontal squad and grouped controls. Preserve EmPickCard keyboard selection and reduced motion.
- [x] Update setup copy, browser selectors and documentation; verify full Vitest, build, desktop/tablet/phone Playwright and screenshots.
- [x] Review the final diff and record verification. Leave changes in the isolated `codex/battle-preparation-matchup` branch for review.

## Verification

- Before implementation, the new EncounterPanel tests failed for the absent matchup and preset control; BattleMatchup was absent. Existing encounter/starter behavior had a clean baseline.
- Focused matchup, encounter and starter tests: 20 passed.
- Full Vitest: 238 passed across 29 files.
- Production build: TypeScript and Vite passed after removing the unused setup-header formatter import.
- Full Chrome Playwright suite: 10 passed. Checks cover 1280/768/390 widths, side-by-side fighters, artwork, switching squad members, fainted selection, horizontal overflow, reduced motion and autonomous requirements.
- Desktop, tablet and phone screenshots inspected; separate capture of phone controls confirms the start action remains reachable in the content scroll area.
- Independent final review: no actionable material findings. Backend routes and battle payloads are unchanged.
- App source changes are limited to the approved layout and its controls, documentation and regression tests. No merge or deployment performed.
## Rebase integration

- Rebased onto e6ef3db, retaining AscendedPreviewCard in the encounter preview and the approved compact squad/matchup in preparation.
- Browser checks exposed a flip-card CSS collision: callers' root class `face` matched the internal face positioning rule and covered navigation. Scoped the rule to `.flipper > .face`; the existing navigation/preparation checks went from failing to passing.
- Combined verification: 243 Vitest tests, all 10 Chrome Playwright checks, and the production build pass.
