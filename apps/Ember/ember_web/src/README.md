# Ember Web source structure

Route screens, private components, and supporting code live together under
`features/`. Start with the feature when looking for a page or changing its
behavior. Each feature owns its clients, state, and helpers when applicable.

```text
src/
  features/
    chat/
      views/          # Chat and public shared-chat screens
      components/     # Composer, transcript, sidebar, dialogs
      composables/    # Chat routing, attachments, scrolling, saved prompts
      api/            # Conversations, folders, prompts, shares, triage
      stores/         # Chat, folders, prompts, entry-agent state
      services/       # Persistence, streaming, slash-command execution
      utils/          # Composer, transcript, folders, chat preferences
    auth/views/       # Login, registration, verification, access errors
    capabilities/     # Catalog, generic capability pages, private components
    account/          # Profile and security
    agents/
    brains/
    generator/
    memory/
    notes/
    overview/
    pdfMerger/
    settings/
    tickets/
    usage/
    mediaDownloader/
  components/
    ui/
      buttons/        # Actions, copy, delete, save, page links
      forms/          # Inputs, switches, segmented controls, setting rows
      dialogs/        # Base dialog and destructive confirmation
      menus/          # Popup menu, positioning, shared menu types
      status/         # Clocks, countdowns, icon indicators
    layout/           # Navigation, page shell, branding, PWA status
    content/          # Markdown, attachments, downloads
    auth/             # Shared authentication presentation
    analytics/        # Shared charts and heatmap
    tools/
      forms/          # Schema form and tool/command run dialogs
      gui/            # Server-defined form, tab, and result rendering
      catalog/        # Tool cards and integration tool browsing
      ToolResultPanel.vue # Shared result display
  api/
    http.ts           # Shared HTTP transport
    McpClientBase.ts  # Shared MCP transport
    types.ts          # DTOs shared by chat, tools, and content
    contracts/        # Shared protocol constants and limit-window types
    auth/             # Session/account client
    navigation/       # Navigation preferences and page settings
    tools/            # Shared tool catalog, execution, GUI contracts
    files/            # Attachment ingestion
    analytics/        # Shared log client
  stores/
    auth.ts           # Application-wide session
    navigation/       # Navigation preferences and page visibility
  composables/
    useTheme.ts       # Application-wide theme
    time/             # Reusable countdowns and clocks
  router/             # Route registration, guards, page metadata
  utils/
    errors.ts         # Common error/time formatting
    browser/          # Clipboard, drag images, URLs, identifiers
    content/          # Markdown, attachments, download markers
    navigation/       # Page paths, arrangement, Admin links
    analytics/        # Shared chart, heatmap, usage/log formatting
    tools/            # Tool schemas, titles, results, GUI parsing
```

Small features keep their view directly in the feature folder. Add a
`components/`, `composables/`, `views/`, `api/`, `stores/`, `services/`, `lib/`,
or `utils/` folder when the feature needs it; empty folder scaffolding is
unnecessary. Tests stay beside the code they test. PDF rendering and planning
helpers live in `features/pdfMerger/lib/`; there is no generic root `lib/` or
`services/` catch-all.

Within shared components, group related controls by role rather than giving
every component its own directory. Keep tests, types, and positioning helpers
beside their component group. Small cohesive groups (`auth/`, `content/`,
`analytics/`, `layout/`) stay flat; a singleton such as `ToolResultPanel.vue`
does not need another folder.

Keep feature-specific code inside its feature. Promote a component into
`components/` when multiple features use it. State with a feature owner stays in
that feature even when another screen consumes it (for example, Settings uses
chat preferences). Cross-feature callers import the owning module directly;
do not add barrel files or forwarding wrappers just to hide its location.
Shared transport and application-wide session/navigation state stay outside
features. A file move alone is not a reason to introduce another store or
abstraction.
Shared `api/`, `stores/`, `composables/`, `utils/`, and reusable components must
not import from `features/`, including type-only imports and re-exports. Put
contracts used by both layers in `api/contracts/`. The router, bootstrap code,
and `components/layout/` compose the application and may import features.
`architecture.test.ts` enforces this rule as part of `npm test`.

Chat transcript exports live in `features/chat/utils/chatExport.ts`; reusable
text downloads and filename handling live in `utils/browser/textDownload.ts`.
Use `utils/errors.ts` for generic exception messages; keep feature-specific
error-code wording in its feature.
Extract cohesive behavior from large screens into feature composables, while
keeping their UI and public props/events stable.

Routes import their feature views directly. Preserve view filenames because
`App.vue` uses component names for `KeepAlive`. Page-layout checks discover
views recursively, and radius checks cover every feature and shared component.

Ember Admin imports `components/layout/PwaStatus.vue` and
`components/layout/pageLayout.css` directly from this app. Update those consumers
when moving either file. Other shared components have copies in Admin; keep
behavior and design fixes consistent between the apps.

Run `npm run build`, `npm test`, and `npm run test:e2e` from `ember_web` after
restructuring. Check Admin too when changing its shared imports.
