# Citadel

Project note: `Brain/Projects/Citadel.md` in the Obsidian vault (`../../Brain/` from this folder; component notes sit beside it, e.g. `ember_api.md`).

## Agent instructions
This file is the one instruction file for every coding agent. Codex reads it directly; `CLAUDE.md` only imports it (`@AGENTS.md`) for Claude Code. Edit this file, never `CLAUDE.md`.

## Skills
Skills live only in `.agents/skills/` (Codex reads it). `.claude/skills` is a git symlink to `../.agents/skills`, so Claude Code reads the same files; there is nothing to sync. Edit through either path. On Windows a fresh clone needs Developer Mode and `git config core.symlinks true`, or `.claude/skills` becomes a plain text file.

## Frontend UI instructions
For UI work in `apps/Ember/ember_web` or `ember_admin`, read `.agents/skills/ember-frontend-design/SKILL.md` and the existing `ember-design-system` skill. For mobile or responsive layouts, touch controls, virtual-keyboard issues, sheets or narrow-screen reviews, also read `.agents/skills/ember-frontend-design/mobile-ui.md`. The mobile guide supplements the shared design; keep desktop behavior and the existing tokens and components coherent with it.

## No reduced motion
Never add a reduced-motion setting, a `prefers-reduced-motion` media query or a reduced-motion test, in any app or doc. Animations always play. Remove one if found in code you touch. Repeats across every skill and plan: do not write it back in.
