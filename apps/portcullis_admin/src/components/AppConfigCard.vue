<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { appConfigClient, type AppConfig, type AppConfigChanges } from "../api/AppConfigClient";
import { errorMessage } from "../utils/errors";

/** Sessions, new accounts, login protection and backups. Saved in Portcullis's database; Portcullis reads them when it
 * starts, so a change is used from its next start. Where Portcullis listens, its cookie and the other services'
 * addresses stay in configs/config_app.json. */
const SIGNALS = ["user_agent", "accept_language", "ip_subnet"];

type Form = {
  session_hours: string; default_role: string; require_email_verification: boolean;
  rl_enabled: boolean; rl_scope: string; rl_max: string; rl_window: string; rl_lockout: string;
  allow: string; deny: string;
  hd_enabled: boolean; hsts: string;
  fp_enabled: boolean; signals: string[];
  bk_enabled: boolean; bk_keep: string; bk_every: string;
};

const saved = ref<AppConfig | null>(null);
const form = ref<Form | null>(null);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");

const lines = (text: string) => text.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
const num = (value: string | number) => (String(value).trim() === "" ? NaN : Number(value));

function toForm(view: AppConfig): Form {
  return {
    session_hours: String(view.session_hours), default_role: view.default_role, require_email_verification: view.require_email_verification,
    rl_enabled: view.rate_limit.enabled, rl_scope: view.rate_limit.scope, rl_max: String(view.rate_limit.max_attempts),
    rl_window: String(view.rate_limit.window_seconds), rl_lockout: String(view.rate_limit.lockout_seconds),
    allow: view.ip_filter.allow_list.join("\n"), deny: view.ip_filter.deny_list.join("\n"),
    hd_enabled: view.headers.enabled, hsts: String(view.headers.hsts_max_age),
    fp_enabled: view.fingerprint.enabled, signals: [...view.fingerprint.signals],
    bk_enabled: view.backup.enabled, bk_keep: String(view.backup.keep), bk_every: String(view.backup.every_hours),
  };
}

function apply(view: AppConfig) {
  saved.value = view;
  form.value = toForm(view);
}

onMounted(async () => {
  try {
    apply(await appConfigClient.get());
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
});

/** Only what differs from the saved values; a group carries only its changed fields. */
const changes = computed<AppConfigChanges>(() => {
  const out: AppConfigChanges = {};
  if (!saved.value || !form.value) return out;
  const was = toForm(saved.value);
  const now = form.value;
  if (String(now.session_hours).trim() !== was.session_hours) out.session_hours = num(now.session_hours);
  if (now.default_role.trim() !== was.default_role) out.default_role = now.default_role.trim();
  if (now.require_email_verification !== was.require_email_verification) out.require_email_verification = now.require_email_verification;
  const rate: Record<string, unknown> = {};
  if (now.rl_enabled !== was.rl_enabled) rate.enabled = now.rl_enabled;
  if (now.rl_scope !== was.rl_scope) rate.scope = now.rl_scope;
  if (String(now.rl_max).trim() !== was.rl_max) rate.max_attempts = num(now.rl_max);
  if (String(now.rl_window).trim() !== was.rl_window) rate.window_seconds = num(now.rl_window);
  if (String(now.rl_lockout).trim() !== was.rl_lockout) rate.lockout_seconds = num(now.rl_lockout);
  if (Object.keys(rate).length) out.rate_limit = rate;
  const filter: Record<string, unknown> = {};
  if (lines(now.allow).join("\n") !== was.allow) filter.allow_list = lines(now.allow);
  if (lines(now.deny).join("\n") !== was.deny) filter.deny_list = lines(now.deny);
  if (Object.keys(filter).length) out.ip_filter = filter;
  const headers: Record<string, unknown> = {};
  if (now.hd_enabled !== was.hd_enabled) headers.enabled = now.hd_enabled;
  if (String(now.hsts).trim() !== was.hsts) headers.hsts_max_age = num(now.hsts);
  if (Object.keys(headers).length) out.headers = headers;
  const fingerprint: Record<string, unknown> = {};
  if (now.fp_enabled !== was.fp_enabled) fingerprint.enabled = now.fp_enabled;
  if (SIGNALS.filter((s) => now.signals.includes(s)).join() !== was.signals.join()) fingerprint.signals = SIGNALS.filter((s) => now.signals.includes(s));
  if (Object.keys(fingerprint).length) out.fingerprint = fingerprint;
  const backup: Record<string, unknown> = {};
  if (now.bk_enabled !== was.bk_enabled) backup.enabled = now.bk_enabled;
  if (String(now.bk_keep).trim() !== was.bk_keep) backup.keep = num(now.bk_keep);
  if (String(now.bk_every).trim() !== was.bk_every) backup.every_hours = num(now.bk_every);
  if (Object.keys(backup).length) out.backup = backup;
  return out;
});
const changed = computed(() => Object.keys(changes.value).length > 0);

async function save() {
  saving.value = true;
  error.value = notice.value = "";
  try {
    apply(await appConfigClient.save(changes.value));
    notice.value = "Saved. Portcullis uses it from its next start.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

async function useDefaults() {
  if (!saved.value?.stored.length) return;
  saving.value = true;
  error.value = notice.value = "";
  try {
    apply(await appConfigClient.save(Object.fromEntries(saved.value.stored.map((key) => [key, null]))));
    notice.value = "Back to the defaults. Portcullis uses them from its next start.";
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <section class="card" aria-labelledby="app-config-title">
    <h2 id="app-config-title" class="title">Sessions, login protection and backups</h2>
    <p class="help">Saved in Portcullis's database and used from its next start.</p>
    <p v-if="loading" class="muted">Loading…</p>
    <form v-else-if="form" class="fields" data-test="form" @submit.prevent="save">
      <fieldset class="group">
        <legend>Accounts</legend>
        <div class="field"><label for="ac-hours">Session length (hours)</label><input id="ac-hours" v-model="form.session_hours" type="number" min="1" :disabled="saving" data-test="session_hours" /></div>
        <div class="field"><label for="ac-role">Role of a new account</label><input id="ac-role" v-model="form.default_role" autocomplete="off" :disabled="saving" data-test="default_role" /></div>
        <label class="check"><input v-model="form.require_email_verification" type="checkbox" :disabled="saving" data-test="require_email_verification" /> Accounts must verify their email</label>
      </fieldset>

      <fieldset class="group">
        <legend>Login rate limit</legend>
        <label class="check"><input v-model="form.rl_enabled" type="checkbox" :disabled="saving" data-test="rl_enabled" /> Limit failed logins</label>
        <div class="field"><label for="ac-scope">Count failures by</label>
          <select id="ac-scope" v-model="form.rl_scope" :disabled="saving" data-test="rl_scope"><option value="both">address and account</option><option value="ip">address</option><option value="account">account</option></select></div>
        <div class="field"><label for="ac-max">Failures allowed</label><input id="ac-max" v-model="form.rl_max" type="number" min="1" :disabled="saving" data-test="rl_max" /></div>
        <div class="field"><label for="ac-window">Within (seconds)</label><input id="ac-window" v-model="form.rl_window" type="number" min="1" :disabled="saving" data-test="rl_window" /></div>
        <div class="field"><label for="ac-lockout">Locked out for (seconds)</label><input id="ac-lockout" v-model="form.rl_lockout" type="number" min="1" :disabled="saving" data-test="rl_lockout" /></div>
      </fieldset>

      <fieldset class="group">
        <legend>IP filter</legend>
        <div class="field"><label for="ac-allow">Allowed networks</label><textarea id="ac-allow" v-model="form.allow" rows="2" spellcheck="false" :disabled="saving" data-test="allow"></textarea>
          <p class="help">One address or network (for example 10.0.0.0/8) per line. Empty allows everyone not denied.</p></div>
        <div class="field"><label for="ac-deny">Denied networks</label><textarea id="ac-deny" v-model="form.deny" rows="2" spellcheck="false" :disabled="saving" data-test="deny"></textarea></div>
      </fieldset>

      <fieldset class="group">
        <legend>Security headers and devices</legend>
        <label class="check"><input v-model="form.hd_enabled" type="checkbox" :disabled="saving" data-test="hd_enabled" /> Send security headers</label>
        <div class="field"><label for="ac-hsts">HSTS (seconds, 0 = off)</label><input id="ac-hsts" v-model="form.hsts" type="number" min="0" :disabled="saving" data-test="hsts" />
          <p class="help">Turn on only once the site is served over HTTPS.</p></div>
        <label class="check"><input v-model="form.fp_enabled" type="checkbox" :disabled="saving" data-test="fp_enabled" /> Log a login from a new device</label>
        <div class="signals">
          <label v-for="signal in SIGNALS" :key="signal" class="check"><input v-model="form.signals" type="checkbox" :value="signal" :disabled="saving" :data-test="`signal-${signal}`" /> {{ signal }}</label>
        </div>
      </fieldset>

      <fieldset class="group">
        <legend>Backups</legend>
        <label class="check"><input v-model="form.bk_enabled" type="checkbox" :disabled="saving" data-test="bk_enabled" /> Back up the database</label>
        <div class="field"><label for="ac-keep">Backups to keep</label><input id="ac-keep" v-model="form.bk_keep" type="number" min="1" :disabled="saving" data-test="bk_keep" /></div>
        <div class="field"><label for="ac-every">Hours between backups</label><input id="ac-every" v-model="form.bk_every" type="number" min="1" :disabled="saving" data-test="bk_every" /></div>
      </fieldset>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="muted" role="status" data-test="notice">{{ notice }}</p>
      <div class="actions">
        <button v-if="saved?.stored.length" type="button" class="chip" :disabled="saving" data-test="defaults" @click="useDefaults">Use the defaults</button>
        <button type="submit" class="primary" data-test="save" :disabled="saving || !changed">{{ saving ? "Saving…" : "Save" }}</button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.card { display: grid; gap: 12px; max-width: 560px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.title { margin: 0; font-size: 1em; font-weight: 600; }
.fields { display: grid; gap: 16px; }
.group { display: grid; gap: 12px; margin: 0; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.group legend { padding: 0 6px; font-size: 0.9em; font-weight: 600; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label { font-size: 0.9em; font-weight: 600; }
.field > input, .field > select, .field > textarea { width: 100%; min-width: 0; min-height: 44px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--bg); font: inherit; }
.check { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; }
.signals { display: flex; flex-wrap: wrap; gap: 4px 16px; }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.error { margin: 0; color: var(--danger); }
.muted { margin: 0; color: var(--muted); }
.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
</style>
