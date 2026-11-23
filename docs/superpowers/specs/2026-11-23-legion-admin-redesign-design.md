# Legion Admin redesign specification

Apply the approved [Legion Admin mockup](../../../apps/legion_admin/mockups/legion-redesign.html) to the production Vue app. Use the [Citadel frontend skill](../../../.agents/skills/ember-frontend-design/SKILL.md) and its mobile guide for implementation. The mockup defines the shell and interactions. Production routes, permissions, live data, configuration fields, and apply timing define what each screen does.

## Shell and navigation

- Use a full-width header with the sidebar toggle, Legion Admin identity, thin divider, and current page title on the left. Place Notifications, Help, and Profile on the right. Profile contains the signed-in account, theme switching, and Log out. Preserve the existing `useTheme` preference and auth store behavior. The dark mockup remains the visual reference.
- Keep Agents, Connections, and Tuning in the sidebar, filtered by their existing permissions. Keep Portcullis, Armory, Stronghold, and Treasury shortcuts at the bottom. Expanded desktop navigation shows labels, collapsed desktop navigation keeps named icons, and the header toggle reveals navigation above content on mobile.
- Keep `PageLayout` for layout, scrolling, and action slots. Show one page title in the header. Keep task-specific section headings and actionable timing notes in the body.
- Notifications show known offline agents from the existing optional live-status request. Selecting the notice opens Agents with the Offline filter. When status is unavailable, say so. Show the offline-agent action only to accounts with `agents.manage`. Help explains real configuration effects, including MCP restart timing. Keep existing sign-in, access-denied, verification, deep-link and session-expiry behavior.

## Panels and drawers

- Give roster, connection, and settings panels labeled local search. Keep filtered-out drafts, scroll context, and active drawer state. Show helpful no-results text and a way to clear search. Keep last-row hover, selection, and focus paint inside rounded panel borders in Light and Dark.
- Any row with one details action opens from every column. Use one native keyboard opener and a row-wide focus indicator. Independent actions stay operable. Long URLs and names wrap or scroll inside the panel.
- Open record details in a full-height, right-edge drawer above a dimmed backdrop. Put Edit, Expand, and Close in the drawer header. Expand to 90% of viewport width and shrink back through the same control. Preserve scroll, selected record, and draft when resizing. Restore focus to the invoking row on close, falling back to panel search if that row disappeared.
- Edit inside the drawer and keep Save and Cancel in a footer outside its scroll area. Validate before save confirmation. Cancel and dismissal during editing ask before discarding. Dismissing confirmation retains the draft. During a request, keep controls pending and prevent double submission. A failed save keeps the draft and shows a recoverable error. Keep existing stronger confirmations for destructive operations.

## Agents

Show the live roster with search and Configured, Running, Offline, and Disabled filters. Counts reflect the loaded roster before search. A failed or unauthorized live-status request leaves enabled records with unknown status, while known configured-disabled records remain Disabled. Keep existing create, edit, shared prompts, prompt preview, reset-to-default, and protected entry-agent deletion behavior. Retain full model, routing, tier, capability, port, and validation controls and show useful existing details in the drawer. Move existing page actions into the roster header or its toolbar.

## Connections

Put Model gateways and MCP servers on `/connections` in separately searchable panels with matching name, description, and address columns. Preserve `/servers` links by redirecting to `/connections#mcp-servers`. The destination keeps the `agents.manage` guard. Independent loading and retry states allow a partial service failure without losing the other section.

- **Model gateways.** Use the existing ConversationGateway and DecisionGateway endpoints and the existing credential flow. Edit description and HTTP(S) URL in the same drawer. Keep partial updates, token clearing, token presence indicators, URL validation, and runtime cache timing. Add optional `description` to the existing GET/PUT responses and PUT payloads. Read missing descriptions as empty, trim writes, allow empty string to clear, and limit descriptions to 500 characters, matching MCP descriptions. Store it in the existing Treasury settings document for each gateway key. An omitted field keeps its saved value. Gateway tokens remain write-only and are excluded from responses and logs. This is an additive document-field change, with no relational migration.
- **MCP servers.** Preserve add, edit, remove, labels and descriptions, direct HTTP URLs, ordered catalog-backed addresses, lookup and registration, stdio command and args, token overrides, and restart timing. Display endpoints appropriate to the transport. Edit the direct URL or the ordered addresses for the applicable HTTP mode. Keep unresolved catalog rows visible and explain which address needs repair before saving. Preserve known origin IDs and order on description-only edits. Maintain the existing write-only header and override semantics.

## Tuning

Use one searchable Tuning settings panel with the existing groups and setting rows. Put a labeled Save icon immediately left of the panel search, and reserve the slot in clean and dirty states. Save remains a single operation for the whole draft, including edits hidden by search. Validate all pending fields, reveal and focus a hidden invalid field, and retain the draft on failure. Keep file defaults, staged resets, Cancel, route-leave and unload protection, and the existing permission and runtime behavior. Keep Cancel with the dirty actions and reserve its space if it shares the header.

## Acceptance

- The approved shell, roster, panel headers, and drawers match the reference in Light and Dark on desktop and narrow layouts. No duplicate page heading, hover corner leak, or Save-slot shift.
- Mouse or keyboard can open a row, edit, resize, save or discard with confirmation where required, and return focus to the list. Search preserves pending changes.
- Real agents, gateways, MCP servers, and every tuning group use their existing APIs. Old data and URLs still work. Failed operations remain retryable and secret values stay write-only.
- Work applies to Legion Admin and the gateway description contract. Keep other admin apps' production layouts outside this rollout.
