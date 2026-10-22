<script setup lang="ts">
import { computed, nextTick, onActivated, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { commandsClient, type CapabilityInfo } from "../../../api/tools/CommandsClient";
import { extensionsClient } from "../api/ExtensionsClient";
import { type ExtensionInfo } from "../../../api/contracts/extensions";
import { McpServerClient } from "../../../api/tools/McpServerClient";
import type { UserExtension } from "../api/UserExtensionsClient";
import type { ResourceInfo, ToolInfo, ToolRunResult } from "../../../api/types";
import PageLayout from "../../../components/layout/PageLayout.vue";
import ToggleSwitch from "../../../components/ui/forms/ToggleSwitch.vue";
import ToolRunModal from "../../../components/tools/forms/ToolRunModal.vue";
import ResourceReader from "../components/ResourceReader.vue";
import UserExtensionModal from "../components/UserExtensionModal.vue";
import ConfirmModal from "../../../components/ui/dialogs/ConfirmModal.vue";
import type { SectionPage } from "../components/CapabilitySection.vue";
import { useAccountCapabilitiesStore } from "../stores/accountCapabilities";
import { useAuthStore } from "../../../stores/auth";
import { useUserExtensionsStore } from "../stores/userExtensions";
import { groupTools, inExtensionNamespace } from "../utils/capabilityGroups";
import { CAPABILITY_ICONS } from "../utils/capabilityIcons";
import { errorMessage } from "../../../utils/errors";
import { formatToolResult } from "../../../utils/tools/toolResultFormat";
import { commandsByTool } from "../../../utils/tools/toolCommands";
import { safeWebUrl } from "../../../utils/browser/webUrl";
import { dedicatedCapabilityPage } from "../../../router/capabilityPages";
import { NAV_PAGES } from "../../../router/pages";

// Both account choices and tool discovery live here; old Supermarket links redirect here.
type Tab = "capabilities" | "extensions";
interface Item {
  key: string; id: string; label: string; tab: Tab; kind: "builtin" | "extension" | "private" | "other";
  enabled: boolean; online: boolean | null; locked: boolean; description: string;
  names: string[]; tools: ToolInfo[]; resources: ResourceInfo[]; page: SectionPage | null;
  privateExtension?: UserExtension;
}
const auth = useAuthStore(), account = useAccountCapabilitiesStore(), userExt = useUserExtensionsStore();
const route = useRoute(), router = useRouter(), server = new McpServerClient();
const canTools = computed(() => auth.hasPermission("tools.view"));
const canPrivate = computed(() => auth.hasPermission("chat.use") && auth.hasPermission("extensions.personal.manage"));
const canSeePrivate = computed(() => auth.hasPermission("chat.use"));
const tab = ref<Tab>(!canTools.value || route.query.tab === "extensions" ? "extensions" : "capabilities");
const queries = ref<Record<Tab, string>>({ capabilities: "", extensions: "" });
if (typeof route.query.q === "string") queries.value[tab.value] = route.query.q;
const query = computed({ get: () => queries.value[tab.value], set: (value: string) => { queries.value[tab.value] = value; } });
const selection = ref<Record<Tab, string | null>>({ capabilities: null, extensions: null });
const detailOpen = ref(false), catalog = ref<HTMLElement>(), backButton = ref<HTMLButtonElement>();
const scrolls: Record<Tab, number> = { capabilities: 0, extensions: 0 };
const capabilities = ref<CapabilityInfo[]>([]), extensions = ref<ExtensionInfo[]>([]);
const tools = ref<ToolInfo[]>([]), resources = ref<ResourceInfo[]>([]);
const loading = ref(true), loadError = ref(""), discoveryError = ref(""), actionError = ref("");
const extensionError = ref("");
// The stores optimistically update. Hold each displayed switch at its confirmed value until settled.
const pending = ref<Record<string, boolean>>({});
const confirmed = (key: string, enabled: boolean): boolean => pending.value[key] ?? enabled;
const connection = (status: string): boolean | null => status === "connected" ? true : status === "unknown" ? null : false;
const toolCount = (n: number): string => `${n} tool${n === 1 ? "" : "s"}`;

function capabilityPage(c: CapabilityInfo): SectionPage | null {
  const page = dedicatedCapabilityPage(c.name);
  if (page) return auth.hasPermission(page.permission) ? { to: page.to, external: false } : null;
  return c.has_gui ? { to: `/capabilities/${encodeURIComponent(c.name)}`, external: false } : null;
}
function extensionPage(e: ExtensionInfo): SectionPage | null {
  const page = dedicatedCapabilityPage(e.id);
  if (page?.route) {
    const available = capabilities.value.some(c => c.enabled && confirmed(`builtin:${c.name}`, account.capabilities.includes(c.name)) && dedicatedCapabilityPage(c.name) === page);
    return available && auth.hasPermission(page.permission) ? { to: page.to, external: false } : null;
  }
  const url = safeWebUrl(e.web_url);
  return url ? { to: url, external: true, label: "Open app" } : null;
}
const items = computed<Item[]>(() => {
  const grouped = groupTools(capabilities.value, tools.value, "", extensions.value);
  const claimedResources = new Set(capabilities.value.flatMap(c => c.resources));
  const unclaimed = resources.value.filter(r => !claimedResources.has(r.name) && !claimedResources.has(r.uri));
  const rows: Item[] = grouped.groups.map(({ capability: c, tools: own }) => ({
    key: `builtin:${c.name}`, id: c.name, label: c.label ?? c.name, tab: "capabilities", kind: "builtin",
    enabled: confirmed(`builtin:${c.name}`, account.capabilities.includes(c.name)), online: c.enabled, locked: !c.enabled && !confirmed(`builtin:${c.name}`, account.capabilities.includes(c.name)),
    description: `Tools provided by ${c.label ?? c.name}.`, names: c.tools, tools: own,
    resources: resources.value.filter(r => c.resources.includes(r.name) || c.resources.includes(r.uri)), page: capabilityPage(c),
  }));
  for (const { extension: e, tools: own } of grouped.extensionGroups) rows.push({
    key: `extension:${e.id}`, id: e.id, label: e.label, tab: "extensions", kind: "extension",
    enabled: confirmed(`extension:${e.id}`, account.extensions.includes(e.id)), online: connection(e.status), locked: false,
    description: e.description || `Tools provided by ${e.label}.`, names: e.tools, tools: own,
    resources: unclaimed.filter(r => inExtensionNamespace(e.id, r.name)), page: extensionPage(e),
  });
  if (canSeePrivate.value) for (const e of userExt.items) rows.push({
    key: `private:${e.id}`, id: e.id, label: e.label, tab: "extensions", kind: "private",
    enabled: confirmed(`private:${e.id}`, e.enabled), online: connection(e.status), locked: !canPrivate.value,
    description: e.description || "Tools from your personal MCP server.", names: e.tools, tools: [], resources: [], page: null, privateExtension: e,
  });
  // Without extension metadata, never offer its namespaced tools as unclaimed tools.
  const otherResources = unclaimed.filter(r => !(extensionError.value && r.name.includes("__")) && !extensions.value.some(e => inExtensionNamespace(e.id, r.name)));
  const otherTools = grouped.otherTools.filter(t => !(extensionError.value && t.name.includes("__")));
  if (canTools.value && (otherTools.length || otherResources.length)) rows.push({
    key: "other", id: "other", label: "Other tools", tab: "capabilities", kind: "other", enabled: true, online: true, locked: true,
    description: "Tools and resources not assigned to a capability or extension.", names: otherTools.map(t => t.name), tools: otherTools, resources: otherResources, page: null,
  });
  return rows.sort((a, b) => Number(b.enabled) - Number(a.enabled) || Number(b.online !== false) - Number(a.online !== false) || a.label.localeCompare(b.label));
});
const tabItems = computed(() => items.value.filter(i => i.tab === tab.value));
const shown = computed(() => {
  const words = query.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return tabItems.value.filter(i => words.every(word => [i.id, i.label, i.description, ...i.names, ...i.tools.flatMap(t => [t.title, t.description]), ...i.resources.flatMap(r => [r.name, r.description ?? ""])].join(" ").toLowerCase().includes(word)));
});
const selected = computed(() => tabItems.value.find(i => i.key === selection.value[tab.value]) ?? shown.value[0] ?? tabItems.value[0] ?? null);
watch(() => selected.value?.key, key => { if (key && !selection.value[tab.value]) selection.value[tab.value] = key; });
const enabledCount = computed(() => tabItems.value.filter(i => i.kind !== "other" && i.enabled).length);
const status = (i: Item): string => i.online === false ? "Offline" : i.enabled ? "Enabled" : "Disabled";
const available = (i: Item): boolean => i.enabled && i.online === true && !(i.key in pending.value);
const scope = (i: Item): string => i.kind === "private" ? "Private extension" : i.kind === "extension" ? "Shared extension" : i.kind === "other" ? "Tools" : "Capability";
function icon(i: Item): { box: string; paths: string[] } {
  const page = i.kind === "builtin" ? dedicatedCapabilityPage(i.id) : undefined;
  const native = page && NAV_PAGES.find(p => p.to === page.to);
  return native ? { box: "0 0 24 24", paths: native.icon } : { box: "0 0 16 16", paths: [CAPABILITY_ICONS[i.kind === "builtin" ? "builtin" : i.kind === "other" ? "other" : "extension"]] };
}
async function pickTab(next: Tab, focus = false): Promise<void> {
  if (catalog.value) scrolls[tab.value] = catalog.value.scrollTop;
  tab.value = next; detailOpen.value = false;
  await router.replace({ query: { ...route.query, tab: next, q: undefined, state: undefined } });
  await nextTick();
  if (catalog.value) catalog.value.scrollTop = scrolls[next];
  if (focus) document.getElementById(`caps-tab-${next}`)?.focus();
}
function tabKey(event: KeyboardEvent): void {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const next = !canTools.value ? "extensions" : event.key === "Home" ? "capabilities" : event.key === "End" ? "extensions" : tab.value === "capabilities" ? "extensions" : "capabilities";
  void pickTab(next, true);
}
async function choose(i: Item): Promise<void> {
  selection.value[tab.value] = i.key; detailOpen.value = true;
  await nextTick();
  if (window.matchMedia?.("(max-width: 767px)").matches) backButton.value?.focus();
}
async function back(): Promise<void> {
  detailOpen.value = false; await nextTick();
  catalog.value?.querySelector<HTMLButtonElement>("button.item-link[aria-current=true]")?.focus();
}
watch(() => route.query.tab, value => { if (value === "extensions" || value === "capabilities" && canTools.value) { tab.value = value; detailOpen.value = false; } });

async function change(i: Item, event?: Event): Promise<void> {
  // A native checkbox flips before change fires; restore it until the server confirms.
  if (event?.target instanceof HTMLInputElement) event.target.checked = i.enabled;
  if (i.locked || i.key in pending.value || !account.ready) return;
  pending.value = { ...pending.value, [i.key]: i.enabled }; actionError.value = "";
  try {
    if (i.kind === "builtin") await account.setCapability(i.id, !i.enabled);
    else if (i.kind === "extension") await account.setExtension(i.id, !i.enabled);
    else if (i.kind === "private") await userExt.setEnabled(i.id, !i.enabled);
  } catch (err) { actionError.value = errorMessage(err); }
  finally { const next = { ...pending.value }; delete next[i.key]; pending.value = next; }
}
async function load(): Promise<void> {
  loading.value = true; loadError.value = ""; discoveryError.value = ""; extensionError.value = "";
  try {
    const [caps, exts, toolList, res] = await Promise.all([
      canTools.value ? commandsClient.capabilities() : [],
      extensionsClient.list().catch(err => { extensionError.value = errorMessage(err); return [] as ExtensionInfo[]; }),
      canTools.value ? server.listTools().catch(err => { discoveryError.value = errorMessage(err); return [] as ToolInfo[]; }) : [],
      canTools.value ? server.listResources().catch(() => [] as ResourceInfo[]) : [],
    ]);
    capabilities.value = caps; extensions.value = exts; tools.value = [...toolList].sort((a, b) => a.title.localeCompare(b.title)); resources.value = res;
  } catch (err) { loadError.value = errorMessage(err); }
  finally { loading.value = false; }
}
async function retry(): Promise<void> { await Promise.all([load(), account.refresh(), canSeePrivate.value ? userExt.refresh() : Promise.resolve()]); }

const tool = ref<ToolInfo | null>(null), running = ref(false), result = ref<ToolRunResult | null>(null);
const registry = ref<Awaited<ReturnType<typeof commandsClient.list>>>([]);
const toolCommand = computed(() => tool.value && selected.value ? commandsByTool(registry.value, selected.value.names, selected.value.kind === "extension" ? selected.value.id : null).get(tool.value.name) : undefined);
let commandsLoaded = false;
async function loadCommands(): Promise<void> {
  if (commandsLoaded) return;
  commandsLoaded = true;
  try { registry.value = await commandsClient.list(); } catch { commandsLoaded = false; }
}
let runGeneration = 0;
let toolOwner: string | null = null;
watch([() => selected.value?.key, () => selected.value && available(selected.value)], ([key, usable]) => {
  if (tool.value && (key !== toolOwner || !usable)) {
    ++runGeneration; tool.value = null; result.value = null;
  }
}, { flush: "sync" });
function openTool(name: string): void {
  const i = selected.value;
  if (!i || !available(i) || i.kind === "private") return;
  toolOwner = i.key; tool.value = i.tools.find(t => t.name === name) ?? null; result.value = null; ++runGeneration;
  if (tool.value) void loadCommands();
}
function closeTool(): void { if (!running.value) { tool.value = null; result.value = null; ++runGeneration; } }
async function run(args: Record<string, unknown>): Promise<void> {
  const i = selected.value, current = tool.value;
  if (!i || !current || i.key !== toolOwner || !i.tools.some(t => t.name === current.name) || !available(i) || i.kind === "private" || !auth.hasPermission("tools.execute") || running.value) return;
  const generation = runGeneration; running.value = true; result.value = null;
  try { const value = await server.runTool(current.name, args); if (generation === runGeneration) result.value = value; }
  catch (err) { if (generation === runGeneration) result.value = { text: errorMessage(err), isError: true }; }
  finally { running.value = false; }
}
const reading = ref<string | null>(null), readUri = ref(""), readResult = ref<{uri: string; text: string} | null>(null), readError = ref("");
let readGeneration = 0;
watch([() => selected.value?.key, () => selected.value && available(selected.value)], () => { ++readGeneration; reading.value = null; readResult.value = null; readError.value = ""; }, { flush: "sync" });
async function startRead(r: ResourceInfo): Promise<void> {
  ++readGeneration; readResult.value = null; readError.value = ""; readUri.value = r.uri; reading.value = r.uri;
  if (!r.template) await read(r.uri);
}
async function read(uri: string): Promise<void> {
  if (!selected.value || !available(selected.value)) return;
  const generation = ++readGeneration;
  try { const text = await server.readResource(uri); if (generation === readGeneration) { readResult.value = { uri, text }; reading.value = null; } }
  catch (err) { if (generation === readGeneration) readError.value = errorMessage(err); }
}
const readShown = computed(() => readResult.value ? formatToolResult(readResult.value.text) ?? readResult.value.text : "");
const modalOpen = ref(false), editing = ref<UserExtension | null>(null), pendingRemove = ref<UserExtension | null>(null), removing = ref(false);
function edit(item: UserExtension | null): void { editing.value = item; modalOpen.value = true; }
function saved(extension: UserExtension): void { modalOpen.value = false; selection.value.extensions = `private:${extension.id}`; detailOpen.value = true; }
async function remove(): Promise<void> {
  if (!pendingRemove.value || removing.value) return;
  removing.value = true; actionError.value = "";
  try { await userExt.remove(pendingRemove.value.id); pendingRemove.value = null; detailOpen.value = false; }
  catch (err) { actionError.value = errorMessage(err); }
  finally { removing.value = false; }
}
onMounted(() => { void load(); });
// Capabilities is kept alive; re-probe personal connections when returning to the page.
onActivated(() => { if (canSeePrivate.value) void userExt.refresh(); });
</script>

<template>
  <PageLayout wide fill title="Capabilities" description="Your tools and connected services." class="caps-view" :class="{ 'detail-open': detailOpen }">
    <template #actions><button v-if="tab === 'extensions' && canPrivate" class="add-extension secondary" type="button" @click="edit(null)">+ Add extension</button></template>
    <p v-if="actionError || account.error || userExt.error" class="error action-error" role="alert">{{ actionError || account.error || userExt.error }}</p>
    <p v-if="loading || (!account.ready && !account.error)" class="notice" role="status">Loading capabilities…</p>
    <div v-else-if="loadError || !account.ready" class="load-error"><p class="error" role="alert">{{ loadError || account.error }}</p><button class="retry secondary" type="button" @click="retry">Retry</button></div>
    <div v-else class="workspace">
      <section class="library" aria-label="Capabilities and extensions list">
        <div class="type-tabs" role="tablist" aria-label="Tool type">
          <button v-if="canTools" id="caps-tab-capabilities" role="tab" aria-controls="caps-catalog" :aria-selected="tab === 'capabilities'" :tabindex="tab === 'capabilities' ? 0 : -1" @click="pickTab('capabilities')" @keydown="tabKey">Capabilities</button>
          <button id="caps-tab-extensions" role="tab" aria-controls="caps-catalog" :aria-selected="tab === 'extensions'" :tabindex="tab === 'extensions' ? 0 : -1" @click="pickTab('extensions')" @keydown="tabKey">Extensions</button>
        </div>
        <label class="search-box"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/></svg><input v-model="query" type="search" :aria-label="tab === 'capabilities' ? 'Search capabilities and tools' : 'Search extensions and tools'" :placeholder="tab === 'capabilities' ? 'Search capabilities and tools…' : 'Search extensions and tools…'" /></label>
        <p v-if="discoveryError" class="error discovery-error">Tool details unavailable: {{ discoveryError }} <button class="link" @click="load">Retry</button></p>
        <p v-if="tab === 'extensions' && extensionError" class="error discovery-error" role="alert">Extensions unavailable: {{ extensionError }} <button class="link" @click="load">Retry</button></p>
        <div class="list-heading"><h3>{{ tab === 'capabilities' ? 'Capabilities' : 'Extensions' }}</h3><span>{{ enabledCount }} enabled · {{ tabItems.filter(i => i.kind !== 'other').length }} total</span></div>
        <div id="caps-catalog" ref="catalog" class="catalog" role="tabpanel" :aria-labelledby="`caps-tab-${tab}`" tabindex="0">
          <p v-if="!shown.length" class="notice">{{ query.trim() ? `Nothing matches “${query.trim()}”.` : `No ${tab} are available.` }}</p>
          <article v-for="i in shown" :key="i.key" class="catalog-row" :class="{ active: selected?.key === i.key, disabled: !i.enabled, offline: i.online === false }" :aria-busy="i.key in pending">
            <button type="button" class="item-link" :aria-current="selected?.key === i.key" :aria-label="`View ${i.label}`" @click="choose(i)">
              <span class="item-icon" aria-hidden="true"><svg :viewBox="icon(i).box"><path v-for="d in icon(i).paths" :key="d" :d="d" /></svg></span>
              <span class="row-copy"><span class="row-title">{{ i.label }}</span><span class="row-meta"><span class="row-state"><span aria-hidden="true">{{ i.online === false ? '⊘' : i.enabled ? '✓' : '○' }}</span> {{ status(i) }}</span><span>{{ toolCount(i.names.length) }}</span><span v-if="i.kind === 'private'">Private</span><span v-if="i.key in pending" role="status">Saving…</span></span></span>
            </button>
            <ToggleSwitch v-if="i.kind !== 'other'" small class="row-toggle" :aria-label="`Enable ${i.label}`" :checked="i.enabled" :disabled="i.locked || i.key in pending" :title="i.locked ? i.kind === 'private' ? 'Managing private extensions requires permission.' : 'Offline for everyone.' : 'Enable or disable for your account.'" @change="change(i, $event)" />
          </article>
        </div>
      </section>
      <aside class="detail" aria-label="Selected item details">
        <template v-if="selected">
          <div class="detail-scroll">
            <button ref="backButton" class="back secondary" @click="back">‹ {{ tab === 'capabilities' ? 'Capabilities' : 'Extensions' }}</button>
            <div class="detail-heading"><h3 class="detail-title">{{ selected.label }}</h3><span class="detail-status"><span aria-hidden="true">{{ selected.online === false ? '⊘' : selected.enabled ? '✓' : '○' }}</span> {{ status(selected) }}</span></div>
            <p class="identity">{{ selected.id }} · {{ scope(selected) }}</p><p class="description">{{ selected.description }}</p>
            <section v-if="selected.kind !== 'other'" class="account-control" :aria-busy="selected.key in pending">
              <ToggleSwitch :checked="selected.enabled" :disabled="selected.locked || selected.key in pending" :aria-label="`Enable selected ${selected.label}`" @change="change(selected, $event)">{{ selected.key in pending ? 'Saving…' : selected.enabled ? 'Enabled' : 'Disabled' }} for {{ selected.kind === 'private' ? 'your chats' : 'your account' }}</ToggleSwitch>
              <p v-if="selected.kind === 'builtin' && !selected.online">Offline for everyone. An administrator must bring it back online.</p>
              <p v-else-if="selected.online === false">This server is offline. Your account choice is saved, but its tools are unavailable.</p>
              <p v-else>{{ selected.enabled ? 'Available in your chats' + (selected.page ? ' and its own workspace.' : '.') : 'Enable to use these tools. Disabling keeps your data.' }}</p>
            </section>
            <div class="section-heading"><h4>Included tools</h4><span>{{ selected.names.length }}</span></div>
            <ul class="tool-list"><li v-for="name in selected.names" :key="name"><button type="button" :disabled="!available(selected) || selected.kind === 'private' || !selected.tools.some(t => t.name === name)" @click="openTool(name)"><span>{{ selected.tools.find(t => t.name === name)?.title ?? name }}</span><span aria-hidden="true">›</span></button></li></ul>
            <p v-if="!selected.names.length" class="notice">No tools registered.</p>
            <p v-if="selected.kind === 'private'" class="private-note">Private extension tools are available in chats only and always ask first.</p>
            <p v-if="selected.online === false" class="notice">Offline · Tools cannot run until the connection returns.</p>
            <p v-if="selected.privateExtension?.error" class="error">{{ selected.privateExtension.error }}</p><p v-else-if="selected.kind === 'extension' && extensions.find(e => e.id === selected?.id)?.error" class="error">{{ extensions.find(e => e.id === selected?.id)?.error }}</p>
            <template v-if="selected.resources.length"><div class="section-heading"><h4>Resources</h4><span>{{ selected.resources.length }}</span></div><ul class="resources"><li v-for="r in selected.resources" :key="r.uri"><button type="button" class="resource-link" :disabled="!available(selected)" @click="startRead(r)">{{ r.name }}</button><code>{{ r.uri }}</code></li></ul><ResourceReader v-model:uri="readUri" :reading="reading" :read-result="readResult" :read-error="readError" :text="readShown" @read="read" /></template>
            <div v-if="selected.privateExtension && canPrivate" class="private-controls"><button class="edit-extension secondary" @click="edit(selected.privateExtension)">Edit connection</button><details class="danger-zone"><summary>Danger zone</summary><p>Remove this private extension and its saved headers.</p><button class="remove-extension danger" @click="pendingRemove = selected.privateExtension">Remove extension</button></details></div>
          </div>
          <footer class="detail-footer"><template v-if="selected.page && available(selected)"><a v-if="selected.page.external" :href="selected.page.to" class="primary" target="_blank" rel="noopener noreferrer">{{ selected.page.label ?? 'Open app' }} ↗</a><RouterLink v-else :to="selected.page.to" class="primary">Open {{ selected.label }} →</RouterLink></template><p v-else>{{ selected.kind === 'private' ? 'Tools are available in chats only.' : !available(selected) ? 'Enable and connect to use these tools.' : 'Choose a tool to view its details.' }}</p></footer>
        </template><p v-else class="notice">Choose an item to view its tools.</p>
      </aside>
    </div>
    <!-- Dialogs stay outside the panes hidden by the mobile list/detail mode. -->
    <ToolRunModal :tool="tool" :running="running" :result="result" :command="toolCommand" class="capability-tool-modal" @close="closeTool" @run="run" />
    <UserExtensionModal class="capability-extension-modal" v-if="canPrivate" :open="modalOpen" :extension="editing" @close="modalOpen = false" @saved="saved" />
    <ConfirmModal v-if="pendingRemove" open title="Remove private extension" :message="`Remove &quot;${pendingRemove.label}&quot;? Its saved headers are deleted too.`" confirm-label="Remove" danger :busy="removing" @confirm="remove" @close="!removing && (pendingRemove = null)" />
  </PageLayout>
</template>

<style scoped src="../capabilitiesWorkspace.css"></style>
