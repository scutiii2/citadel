<script setup lang="ts">
import PageLayout from "../../../components/layout/PageLayout.vue";
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { capabilityPagesClient, type GuiPageSpec } from "../../../api/tools/CapabilityPagesClient";
import { commandsClient } from "../../../api/tools/CommandsClient";
import { ApiError } from "../../../api/http";
import { McpServerClient } from "../../../api/tools/McpServerClient";
import type { ToolInfo } from "../../../api/types";
import GuiFormSection from "../../../components/tools/gui/GuiFormSection.vue";
import GuiTabsSection from "../../../components/tools/gui/GuiTabsSection.vue";
import { errorMessage } from "../../../utils/errors";
import { GuiPageError, parseGuiPage } from "../../../utils/tools/guiPage";

/** A capability's own page (mcp_server's gui/page.json): a title, notes and
 * one form per tool section. Nothing here is specific to one capability. */
const route = useRoute();
const server = new McpServerClient();

const name = computed(() => String(route.params.name ?? ""));
const loading = ref(true);
const problem = ref("");
const page = ref<GuiPageSpec | null>(null);
const label = ref("");
const tools = ref<Record<string, ToolInfo>>({});

// Only the latest load may write state; a slower earlier one is dropped.
let current = 0;

async function load(): Promise<void> {
  const seq = ++current;
  loading.value = true;
  problem.value = "";
  page.value = null;
  tools.value = {};
  try {
    const requested = name.value;
    const capability = (await commandsClient.capabilities()).find((c) => c.name === requested);
    if (seq !== current) return;
    if (!capability) {
      problem.value = `Unknown capability '${requested}'.`;
      return;
    }
    label.value = capability.label ?? capability.name;
    if (!capability.enabled) {
      problem.value = `${label.value} is turned off.`;
      return;
    }
    const [raw, allTools] = await Promise.all([capabilityPagesClient.get(requested), server.listTools()]);
    if (seq !== current) return;
    page.value = parseGuiPage(raw, capability.tools);
    tools.value = Object.fromEntries(allTools.map((t) => [t.name, t]));
  } catch (err) {
    if (seq !== current) return;
    if (err instanceof GuiPageError) problem.value = `This page's layout is invalid: ${err.message}`;
    else if (err instanceof ApiError && err.status === 404) problem.value = `${label.value || name.value} has no page.`;
    else problem.value = errorMessage(err);
  } finally {
    if (seq === current) loading.value = false;
  }
}

const runTool = (tool: string, args: Record<string, unknown>) => server.runTool(tool, args);

onMounted(load);
watch(name, load);
</script>

<template>
  <PageLayout :title="page?.title ?? 'Capability'" :description="page?.description">
    <div class="capability-body">
      <p><RouterLink to="/capabilities">← Capabilities</RouterLink></p>
      <p v-if="loading" class="muted">Loading…</p>
      <p v-else-if="problem" class="error" role="alert">{{ problem }}</p>
      <template v-else-if="page">
        <template v-for="s in page.sections" :key="s.id">
          <section v-if="s.type === 'text'" class="note">
            <h3 v-if="s.title">{{ s.title }}</h3>
            <p>{{ s.text }}</p>
          </section>
          <GuiTabsSection v-else-if="s.type === 'tabs'" :section="s" :tools="tools" :run-tool="runTool" />
          <GuiFormSection v-else-if="tools[s.tool]" :section="s" :tool="tools[s.tool]" :run-tool="runTool" />
          <p v-else class="error">The tool {{ s.tool }} is not available right now.</p>
        </template>
      </template>
    </div>
  </PageLayout>
</template>

<style scoped>

.muted {
  color: var(--muted);
}
.error {
  color: var(--danger);
}
</style>
