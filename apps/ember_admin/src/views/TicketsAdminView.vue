<script setup lang="ts">
import PageLayout from "../components/PageLayout.vue";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import TicketsPanel from "../components/admin/TicketsPanel.vue";
import type { TicketFilterState } from "../utils/ticketFormat";
import "../components/admin/admin.css";
import "../components/infoPage.css";

const STATUSES = ["open", "in_progress", "resolved", "closed"] as const;
const PRIORITIES = ["low", "normal", "high", "urgent"] as const;

const route = useRoute();
const router = useRouter();

const filters = computed<TicketFilterState>(() => {
  const { status, priority, tag, mode } = route.query;
  return {
    status: (STATUSES as readonly unknown[]).includes(status) ? (status as TicketFilterState["status"]) : "all",
    priority: (PRIORITIES as readonly unknown[]).includes(priority) ? (priority as TicketFilterState["priority"]) : "all",
    tag: typeof tag === "string" ? tag : "",
    mode: mode === "review" || mode === "groups" ? mode : "board",
  };
});

function updateFilters(next: TicketFilterState): void {
  void router.replace({
    query: {
      ...route.query,
      status: next.status === "all" ? undefined : next.status,
      priority: next.priority === "all" ? undefined : next.priority,
      tag: next.tag || undefined,
      mode: next.mode === "board" ? undefined : next.mode,
    },
  });
}
</script>

<template>
  <PageLayout class="info-content tickets-admin" title="Tickets" description="A clear view of what needs attention and what’s moving forward." wide fill>
    <TicketsPanel :filters="filters" @filter="updateFilters" />
  </PageLayout>
</template>
