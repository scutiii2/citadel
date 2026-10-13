<script setup lang="ts">
defineProps<{ quantity: number; max: number; name: string; disabled?: boolean; suffix?: string }>();
const emit = defineEmits<{ change: [quantity: number] }>();
</script>

<template>
  <div class="em-quantity">
    <button type="button" :aria-label="`Decrease ${name} quantity`" :disabled="disabled || quantity <= 1" @click="emit('change', quantity - 1)">−</button>
    <span class="em-num">{{ quantity }}{{ suffix ? ` ${suffix}` : '' }}</span>
    <button type="button" :aria-label="`Increase ${name} quantity`" :disabled="disabled || quantity >= max" @click="emit('change', quantity + 1)">+</button>
  </div>
</template>

<style scoped>
.em-quantity { display:flex; align-items:center; justify-content:space-between; width:100%; min-height:32px; border:1px solid #f5c18c; border-radius:var(--em-radius); color:var(--em-on-accent); background:linear-gradient(#f7c590,#e9a461); }
button { min-width:36px; align-self:stretch; padding:3px 8px; color:inherit; border:0; background:transparent; font:inherit; font-size:18px; cursor:pointer; }
button:disabled { opacity:.4; cursor:default; } span { flex:1; text-align:center; font-size:12px; font-weight:600; border-inline:1px solid #b7784766; }
@media(max-width:700px) { .em-quantity { min-height:44px; } button { min-width:40px; } }
</style>
