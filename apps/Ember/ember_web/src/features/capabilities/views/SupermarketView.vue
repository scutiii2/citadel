<script setup lang="ts">
import { onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import PageLayout from "../../../components/layout/PageLayout.vue";

// Compatibility for old direct imports. The router redirects bookmarks before rendering.
const route = useRoute(), router = useRouter();
onMounted(() => { void router.replace({ path: "/capabilities", query: { ...route.query, state: undefined }, hash: route.hash }); });
</script>
<template><PageLayout title="Capabilities"><p role="status">Opening capabilities…</p></PageLayout></template>
