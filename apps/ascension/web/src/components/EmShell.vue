<script setup lang="ts">
import EmIcon from "./ui/EmIcon.vue";
import brandIcon from "../assets/brand/ascension-logo-icon.webp";
defineProps<{ insignia: number | null; shopEnabled?: boolean; shopOpen?: boolean }>();
const emit = defineEmits<{ shop: [] }>();
</script>

<template>
  <div class="shell">
    <header class="mast" :class="{ 'has-account': shopEnabled }">
      <div class="navigation">
        <slot name="navigation"><h1 class="brand" aria-label="ASCENSION"><img class="brand-icon" :src="brandIcon" alt="" /><span class="brand-label">ASCENSION</span></h1></slot>
      </div>
      <div class="header-tools"><slot name="tools" /></div>
      <div class="account-actions">
        <div v-if="insignia !== null" class="wallet em-num" :aria-label="insignia + ' Insignia'"><EmIcon name="coin" :size="21" /><span>{{ insignia.toLocaleString() }}</span></div>
        <button v-if="shopEnabled" type="button" class="shop-action" aria-label="Shop" data-label="Shop" :aria-pressed="shopOpen" @click="emit('shop')"><EmIcon name="shop" :size="22" /><span class="nav-label">Shop</span></button>
        <slot name="actions" />
      </div>
    </header>
    <main class="main" tabindex="0" aria-label="Screen content"><slot /></main>
  </div>
</template>

<style scoped>
.shell { display:flex; flex-direction:column; min-height:0; height:100%; overflow:hidden; background:linear-gradient(90deg,#03101de8,#04132380),var(--em-sanctuary-scene) center / cover; }
.mast { display:flex; align-items:center; gap:20px; flex:none; min-height:72px; padding:0 24px; border-bottom:1px solid var(--em-divider); background:#03101dc9; }
.navigation { display:flex; align-items:center; gap:16px; min-width:0; }
.brand { margin:0; display:flex; align-items:center; gap:18px; color:var(--em-accent); }
.brand-label { color:var(--em-text); font:14px var(--em-font-heading); letter-spacing:6px; }
.brand-icon { width:36px; height:44px; object-fit:contain; }
.header-tools { display:flex; align-items:center; justify-content:center; flex:1; min-width:0; }
.account-actions { display:flex; align-items:center; gap:10px; margin-left:auto; }
.wallet { display:flex; align-items:center; gap:8px; min-height:44px; color:var(--em-text); font-weight:600; font-size:14px; white-space:nowrap; }
.shop-action { display:flex; align-items:center; justify-content:center; gap:8px; min-width:44px; min-height:44px; padding:8px 12px; border:0; border-bottom:2px solid transparent; color:var(--em-muted); background:transparent; font:inherit; cursor:pointer; }
.shop-action:hover,.shop-action[aria-pressed=true] { color:var(--em-accent); border-bottom-color:var(--em-accent); }
.wallet > .em-icon { color:var(--em-accent); }
.main { flex:1; min-height:0; overflow:auto; padding:24px; scrollbar-color:#395065 #071724; scrollbar-width:thin; }
.mast :deep([data-label]) { position:relative; }
.mast :deep([data-label]::after) { content:attr(data-label); position:absolute; top:calc(100% + 8px); left:0; z-index:20; padding:6px 10px; border:1px solid var(--em-border); border-radius:var(--em-radius); background:var(--em-raised); color:var(--em-text); font:600 13px/1.5 var(--em-font-body); white-space:nowrap; pointer-events:none; visibility:hidden; }
.mast :deep([data-label]:hover::after) { visibility:visible; transition:visibility 0s 1s; }
.mast :deep([data-label]:focus-visible::after) { visibility:visible; }
.account-actions :deep([data-label]::after) { left:auto; right:0; }
@media(max-width:1100px) { .mast { gap:8px; padding-inline:14px; } .navigation { gap:8px; } .wallet { font-size:13px; } .brand-label { display:none; } .account-actions { gap:4px; } }
@media(max-width:700px) {
 .mast { flex-wrap:wrap; min-height:60px; padding:10px; gap:8px; }
 .navigation { gap:8px; flex:1 1 auto; } .brand { font-size:16px; } .wallet { font-size:11px; padding-left:8px; gap:4px; min-height:36px; } .wallet > .em-icon { width:18px; height:18px; }
 .header-tools:has(> :not(:empty)) { order:3; flex-basis:100%; }
 .header-tools:empty { display:none; } .main { padding:6px; } .account-actions { gap:4px; }
}
@media(orientation:portrait), (max-width:700px) {
 .mast { flex-wrap:nowrap; gap:4px; min-height:60px; padding:0 8px; }
 .navigation { flex:0 1 auto; gap:2px; } .nav-label,.brand-label { display:none; }
 .brand-icon { width:24px; height:36px; }
 .header-tools { display:none; } .account-actions { gap:0; }
 .wallet { gap:4px; font-size:11px; padding:0; border:0; }
 .shop-action { padding:6px; } .main { padding:16px 12px; }
}
@media(max-width:380px) { .mast { padding-inline:4px; } .wallet { font-size:10px; } .main { padding-inline:10px; } }
</style>
