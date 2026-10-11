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
  <section class="info-page tickets-admin">
    <div class="ticket-page-column">
      <h2 class="page-title">Tickets</h2>
      <p class="intro page-description">
        A clear view of what needs attention and what’s moving forward.
      </p>
      <TicketsPanel :filters="filters" @filter="updateFilters" />
    </div>
  </section>
</template>

<style scoped>
.tickets-admin {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.ticket-page-column {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: 28px 30px 16px;
}
.page-title { font-size: 1.5rem; }
.page-description { margin-bottom: 24px; }
@media (max-width: 767px) {
  .ticket-page-column { padding: 20px 16px 12px; }
  .page-title { font-size: 1.3rem; }
  .page-description { margin-bottom: 18px; font-size: 0.8rem; }
}
</style>
