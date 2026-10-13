<script setup lang="ts">
import EmIcon from "./ui/EmIcon.vue";

/** The page's frame: the masthead (logo, tagline, Insignia wallet) over the content.
 * The wallet shows only once there is a profile. */
defineProps<{ insignia: number | null; shopEnabled?: boolean; shopOpen?: boolean; destination?: string }>();
const emit = defineEmits<{ shop: [] }>();
</script>

<template>
  <div class="shell">
    <header class="mast" :class="{ 'has-account': shopEnabled }">
      <div class="navigation"><slot name="navigation">
        <h1 class="brand em-pixel"><EmIcon name="flame" :size="22" /> ASCENSION</h1>
        <p class="tagline">Collect. Forge. Battle.</p>
      </slot><span class="destination">{{ destination ?? "Main menu" }}</span></div>
      <div v-if="insignia !== null" class="account-actions">
      <component :is="shopEnabled ? 'button' : 'div'" class="wallet" :type="shopEnabled ? 'button' : undefined" :aria-label="shopEnabled ? 'Open shop, ' + insignia + ' Insignia' : 'Your Insignia'" :aria-pressed="shopEnabled ? shopOpen : undefined" @click="shopEnabled && emit('shop')">
        <EmIcon name="coin" />
        <span class="em-num amount">{{ insignia }}</span>
        Insignia
      </component>
      <slot name="actions" />
      </div>
      <span v-else class="wallet-gap" aria-hidden="true" />
    </header>
    <div v-if="$slots.heading" class="screen-heading"><slot name="heading" /></div>
    <main class="main" tabindex="0" aria-label="Screen content"><slot /></main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
.mast {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--em-space-4);
  flex: none;
  min-height: 80px;
  padding: 0 var(--em-space-7);
  border-bottom: 1px solid var(--em-divider);
  background: var(--em-header);
}
.navigation {
  display: flex;
  align-items: center;
  gap: var(--em-space-5);
  min-width: 0;
}
.mast.has-account { grid-template-columns: minmax(0, 1fr) auto; }
.has-account .navigation { grid-column: 1; grid-row: 1; justify-self: start; }
.account-actions { display: flex; align-items: center; gap: var(--em-space-2); }
.has-account .account-actions { grid-column: 2; grid-row: 1; }
.screen-heading {
  flex: none;
  width: 100%;
  padding: var(--em-space-5) var(--em-space-7);
  border-bottom: 1px solid var(--em-divider);
}
.screen-heading :deep(.head) { margin-bottom: 0; }
.brand {
  display: flex;
  align-items: center;
  gap: var(--em-space-3);
  margin: 0;
  font-size: 20px;
  line-height: 1.2;
  color: var(--em-accent);
}
.tagline {
  margin: 0;
  font-size: 12px;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--em-muted);
}
.wallet {
  display: flex;
  align-items: center;
  justify-self: end;
  gap: 9px;
  padding: 8px 14px;
  border: 1px solid var(--em-border);
  background: var(--em-panel);
  font-weight: 600;
  color: var(--em-text);
  font-family: inherit;
  font-size: inherit;
  min-height: var(--em-target);
}
button.wallet { cursor: pointer; }
button.wallet:hover, button.wallet[aria-pressed="true"] { border-color: var(--em-accent); color: var(--em-accent); }
.wallet svg {
  color: var(--em-accent);
}
.amount {
  font-size: 16px;
}
.main {
  flex: 1;
  min-height: 0;
  width: 100%;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  scrollbar-gutter: stable;
  padding: var(--em-space-5) var(--em-space-7) var(--em-space-7);
}
@media (max-width: 900px) {
  .mast.has-account { grid-template-columns: minmax(0, 1fr); padding-block: var(--em-space-2); }
  .has-account .navigation { grid-column: 1; grid-row: 2; justify-self: start; }
  .has-account .account-actions { grid-column: 1; grid-row: 1; flex-wrap: wrap; }
}
@media (max-width: 700px) {
  .mast {
    grid-template-columns: minmax(0, 1fr) auto;
    min-height: 64px;
    gap: var(--em-space-2);
    padding: 0 var(--em-space-4);
  }
  .brand {
    gap: 8px;
    font-size: 16px;
  }
  .tagline {
    display: none;
  }
  .wallet {
    padding: 6px 9px;
    font-size: 12px;
  }
  .main {
    padding: var(--em-space-5) var(--em-space-4) var(--em-space-6);
  }
  .navigation { gap: var(--em-space-2); }
  .screen-heading { padding: var(--em-space-4); }
}
</style>

<style scoped>
.mast { min-height:74px; border-bottom:1px solid #65869c; box-shadow:inset 0 -3px 0 #06111b; padding-inline:24px; background:linear-gradient(180deg,#11283a,#0a1a27); }
.destination { border-left:1px solid var(--em-accent); padding-left:20px; color:var(--em-text); font-weight:600; white-space:nowrap; }
.brand { font-size:24px; text-shadow:0 2px 0 #83532e; } .tagline { display:none; }
.wallet { background:#0a1a28; border-color:#617d90; box-shadow:inset 0 0 0 2px #07111c; }
.main { padding:24px; } .screen-heading { padding:20px 24px; background:linear-gradient(90deg,#142b3c,#091a27); }
@media(max-width:1100px) { .navigation { flex-wrap:wrap; gap:10px; } .destination { font-size:11px; padding-left:10px; } }
@media(max-width:900px) { .mast.has-account { grid-template-columns:minmax(0,1fr) auto; } .has-account .navigation { grid-row:1; } .has-account .account-actions { grid-column:2; grid-row:1; } .account-actions { gap:4px; } }
@media(max-width:700px) { .mast { padding:10px 12px; } .mast.has-account { grid-template-columns:minmax(0,1fr); gap:8px; } .has-account .account-actions { grid-column:1; grid-row:2; } .destination { margin-left:auto; } .main { padding:16px 12px; } .screen-heading { padding:16px 12px; } .brand { font-size:18px; } }
</style>
