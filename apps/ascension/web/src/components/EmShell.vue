<script setup lang="ts">
import EmIcon from "./ui/EmIcon.vue";
defineProps<{ insignia: number | null; shopEnabled?: boolean; shopOpen?: boolean; destination?: string }>();
const emit = defineEmits<{ shop: [] }>();
</script>

<template>
  <div class="shell">
    <header class="mast" :class="{ 'has-account': shopEnabled }">
      <div class="navigation">
        <slot name="navigation"><h1 class="brand em-pixel">ASCENSION</h1></slot>
        <span class="destination">{{ destination ?? "Main menu" }}</span>
      </div>
      <div class="header-tools"><slot name="tools" /></div>
      <div v-if="insignia !== null" class="account-actions">
        <component :is="shopEnabled ? 'button' : 'div'" class="wallet" :type="shopEnabled ? 'button' : undefined" :aria-label="shopEnabled ? 'Open shop, ' + insignia + ' Insignia' : 'Your Insignia'" :aria-pressed="shopEnabled ? shopOpen : undefined" @click="shopEnabled && emit('shop')">
          <EmIcon name="coin" :size="24" /><span class="em-num amount">{{ insignia.toLocaleString() }}</span><span> Insignia</span>
        </component>
        <slot name="actions" />
      </div>
    </header>
    <main class="main" tabindex="0" aria-label="Screen content"><slot /></main>
  </div>
</template>

<style scoped>
.shell { display:flex; flex-direction:column; min-height:0; height:100%; overflow:hidden; border:1px solid #405c70; border-radius:var(--em-radius); background:var(--em-bg); box-shadow:inset 0 0 0 3px #152632; }
.mast { display:flex; align-items:center; gap:20px; flex:none; min-height:68px; padding:10px 20px; border-bottom:1px solid #3c5468; background:linear-gradient(180deg,#142430,#0e1c28); }
.navigation { display:flex; align-items:center; gap:16px; min-width:0; }
.brand { margin:0; font-size:28px; font-weight:700; color:var(--em-accent); letter-spacing:.25px; }
.destination { border-left:1px solid var(--em-accent); padding-left:20px; color:var(--em-text); font-weight:700; font-size:16px; white-space:nowrap; }
.header-tools { display:flex; align-items:center; justify-content:center; flex:1; min-width:0; }
.account-actions { display:flex; align-items:center; gap:10px; margin-left:auto; }
.wallet { display:flex; align-items:center; gap:8px; min-height:44px; padding:4px 0 4px 16px; border:0; border-left:1px solid #3c5468; color:var(--em-text); background:transparent; font:inherit; font-weight:700; font-size:16px; white-space:nowrap; cursor:pointer; }
.wallet > .em-icon { color:var(--em-accent); }
.main { flex:1; min-height:0; overflow:auto; padding:8px; }
@media(max-width:1100px) { .mast { gap:12px; padding-inline:14px; } .brand { font-size:22px; } .destination { font-size:13px; padding-left:12px; } .navigation { gap:10px; } .wallet { font-size:13px; } }
@media(max-width:700px) {
 .mast { flex-wrap:wrap; min-height:60px; padding:10px; gap:8px; }
 .navigation { gap:8px; flex:1 1 auto; } .brand { font-size:16px; } .destination { font-size:11px; padding-left:8px; }
 .wallet { font-size:11px; padding-left:8px; gap:4px; min-height:36px; } .wallet > .em-icon { width:18px; height:18px; }
 .header-tools:has(> :not(:empty)) { order:3; flex-basis:100%; }
 .header-tools:empty { display:none; } .main { padding:6px; } .account-actions { gap:4px; }
}
@media(max-width:430px) { .account-actions { width:100%; justify-content:flex-end; } .wallet { border-left:0; min-height:26px; } }
</style>
