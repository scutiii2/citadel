<script setup lang="ts">
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
    mode: mode === "review" ? "review" : "groups",
  };
});

function updateFilters(next: TicketFilterState): void {
  void router.replace({
    query: {
      ...route.query,
      status: next.status === "all" ? undefined : next.status,
      priority: next.priority === "all" ? undefined : next.priority,
      tag: next.tag || undefined,
      mode: next.mode === "review" ? "review" : undefined,
    },
  });
}
</script>

<template>
  <section class="info-page tickets-admin">
    <div class="column page-column">
      <h2 class="page-title">Tickets</h2>
      <p class="intro page-description">
        Reports from people and from the assistant, grouped by similar issue. Priority rises as a group grows; set one by hand to pin it.
      </p>
      <TicketsPanel :filters="filters" @filter="updateFilters" />
    </div>
  </section>
</template>
