<script setup lang="ts">
import { ImageTile } from "@citadel/ui";
import { useImagePreview } from "../../../composables/useImagePreview";

/** A picture waiting to be sent: the local file just added, or the stored one of a retried question. */
const props = defineProps<{ name: string; file?: File; fileId?: string; busy?: boolean }>();
const emit = defineEmits<{ remove: [] }>();

const { url } = useImagePreview(() => props.file ?? props.fileId);
</script>

<template>
  <ImageTile :src="url" :name="name" :busy="busy" @remove="emit('remove')" />
</template>
