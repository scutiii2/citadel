<script setup lang="ts">
import { ActionMessage } from "@citadel/ui";
import { computed, nextTick, onMounted, ref } from "vue";
import { appConfigClient, type AppConfig, type AppConfigChanges } from "../api/AppConfigClient";
import { useDraftPanel } from "@citadel/ui";
import { errorMessage } from "../utils/errors";
import { AdminSearch } from "@citadel/ui";
import { FieldLabel } from "@citadel/ui";
import { PanelHelp } from "@citadel/ui";
import { ConfirmModal } from "@citadel/ui";
import { ToggleSwitch } from "@citadel/ui";
import { DraftActions } from "@citadel/ui";
import "@citadel/ui/admin.css";

/** Sessions, new accounts, login protection and backups. Saved in Portcullis's database; Portcullis reads them when it
 * starts, so a change is used from its next start. Where Portcullis listens, its cookie and the other services'
 * addresses stay in configs/config_app.json. Search only hides groups: every field stays mounted, and a save
 * checks all of them, revealing the first invalid one if search had hidden it. */
const SIGNALS = ["user_agent", "accept_language", "ip_subnet"];
function setSignal(signal: string, on: boolean): void {
  const f = form.value;
  if (f) f.signals = on ? [...f.signals, signal] : f.signals.filter((s) => s !== signal);
}
const GROUPS = [
  { id: "accounts", title: "Sessions and new users", words: "session length hours role new account" },
  { id: "rate", title: "Login rate limit", words: "failed logins count failures address account lockout window" },
  { id: "ip", title: "IP filter", words: "allowed denied networks address" },
  { id: "headers", title: "Security headers and devices", words: "hsts https new device fingerprint user agent language subnet" },
  { id: "backup", title: "Backups", words: "database keep hours" },
] as const;
type Form = {
  session_hours: string; default_role: string;
  rl_enabled: boolean; rl_scope: string; rl_max: string; rl_window: string; rl_lockout: string;
  allow: string; deny: string;
  hd_enabled: boolean; hsts: string;
  fp_enabled: boolean; signals: string[];
  bk_enabled: boolean; bk_keep: string; bk_every: string;
};
const saved = ref<AppConfig | null>(null);
const form = ref<Form | null>(null);
const formEl = ref<HTMLFormElement>();
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");
const search = ref("");
const searchField = ref<InstanceType<typeof AdminSearch>>();
const lines = (text: string) => text.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
const num = (value: string | number) => (String(value).trim() === "" ? NaN : Number(value));

function toForm(view: AppConfig): Form {
  return {
    session_hours: String(view.session_hours), default_role: view.default_role,
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
const groupShown = (group: (typeof GROUPS)[number]) => {
  const query = search.value.trim().toLowerCase();
  return !query || `${group.title} ${group.words}`.toLowerCase().includes(query);
};
const anyShown = computed(() => GROUPS.some(groupShown));
const { discardOpen, keepFocus, answerDiscard } = useDraftPanel(changed, searchField);

function cancel() {
  if (saved.value) form.value = toForm(saved.value);
  error.value = notice.value = "";
}

/** Checks every field, hidden ones included. The first invalid one is revealed (search cleared) and focused. */
async function firstInvalid(): Promise<boolean> {
  const bad = [...(formEl.value?.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("input, select, textarea") ?? [])].find((el) => !el.checkValidity());
  if (!bad) return false;
  if (bad.closest("fieldset")?.hidden || bad.closest("fieldset")?.style.display === "none") search.value = "";
  await nextTick();
  bad.focus();
  bad.reportValidity();
  return true;
}

async function save() {
  if (saving.value || !changed.value) return;
  error.value = notice.value = "";
  if (await firstInvalid()) return;
  saving.value = true;
  await keepFocus(async () => {
    try {
      apply(await appConfigClient.save(changes.value));
      notice.value = "Saved. Portcullis uses it from its next start.";
    } catch (err) {
      error.value = errorMessage(err);
    } finally {
      saving.value = false;
    }
  });
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
  <section class="admin-panel-card app-config admin-panel" aria-labelledby="app-config-title">
    <header class="admin-panel-head">
      <h2 id="app-config-title">Server settings</h2>
      <div class="admin-panel-tools tools">
        <PanelHelp title="Server settings"><p>Server-wide settings for sessions, new users, failed-login limits, IP filters, security headers and database backups.</p><p>Saved in the Portcullis database and used from its next start. Every setting has its own <b>?</b> with what it does and the values it takes.</p></PanelHelp>
        <DraftActions :dirty="changed" :saving="saving" label="app configuration changes" @cancel="discardOpen = true" @save="save" />
        <AdminSearch ref="searchField" v-model="search" label="Search app configuration" />
      </div>
    </header>
    <p v-if="loading" class="admin-panel-text muted">Loading…</p>
    <ActionMessage v-else-if="error && !form" kind="error" :text="error" class="admin-panel-text" />
    <template v-else-if="form">
      <p v-if="!anyShown" class="admin-panel-text muted">No settings match your search. <button type="button" class="chip" @click="search = ''; searchField?.focus()">Clear search</button></p>
      <form ref="formEl" class="fields" data-test="form" novalidate @submit.prevent="save">
        <fieldset v-show="groupShown(GROUPS[0])" class="group">
          <legend>Sessions and new users</legend>
          <p class="lede">How long a sign-in lasts and what a new user starts with.</p>
          <div class="grid">
            <div class="field"><FieldLabel for="ac-hours" title="Session length (hours)"><p>How long a sign-in lasts before the user has to sign in again.</p><p>A whole number of hours, 1 or more. Example: 12.</p></FieldLabel><input id="ac-hours" v-model="form.session_hours" type="number" min="1" :disabled="saving" data-test="session_hours" /></div>
            <div class="field"><FieldLabel for="ac-role" title="Role of a new user"><p>The role every new user receives when they register or accept an invite.</p><p>Type the name of an existing role exactly, for example Member. Roles are managed on the Roles &amp; permissions page.</p></FieldLabel><input id="ac-role" v-model="form.default_role" autocomplete="off" :disabled="saving" data-test="default_role" /></div>
          </div>
        </fieldset>
        <fieldset v-show="groupShown(GROUPS[1])" class="group">
          <legend>Login rate limit</legend>
          <p class="lede">Slows down password guessing by blocking sign-in after too many failures.</p>
          <div class="toggle-row"><ToggleSwitch :checked="form.rl_enabled" :disabled="saving" data-test="rl_enabled" @change="form.rl_enabled = ($event.target as HTMLInputElement).checked">Limit failed logins</ToggleSwitch><FieldLabel bare title="Limit failed logins"><p><b>On:</b> after too many wrong passwords, further attempts are blocked for a while.</p><p><b>Off:</b> unlimited attempts. Not recommended.</p></FieldLabel></div>
          <div class="grid">
            <div class="field"><FieldLabel for="ac-scope" title="Count failures by"><p>What a failure is counted against.</p><p><b>address and account:</b> each network address and each username separately. <b>address:</b> only the network address. <b>account:</b> only the username.</p></FieldLabel>
              <select id="ac-scope" v-model="form.rl_scope" :disabled="saving" data-test="rl_scope"><option value="both">address and account</option><option value="ip">address</option><option value="account">account</option></select></div>
            <div class="field"><FieldLabel for="ac-max" title="Failures allowed"><p>How many wrong passwords are allowed inside the time window before sign-in is blocked.</p><p>A whole number, 1 or more. Example: 5.</p></FieldLabel><input id="ac-max" v-model="form.rl_max" type="number" min="1" :disabled="saving" data-test="rl_max" /></div>
            <div class="field"><FieldLabel for="ac-window" title="Within (seconds)"><p>The time window failures are counted in.</p><p>Seconds, 1 or more. Example: 900 is 15 minutes.</p></FieldLabel><input id="ac-window" v-model="form.rl_window" type="number" min="1" :disabled="saving" data-test="rl_window" /></div>
            <div class="field"><FieldLabel for="ac-lockout" title="Locked out for (seconds)"><p>How long sign-in stays blocked after the limit is reached.</p><p>Seconds, 1 or more. Example: 900 is 15 minutes.</p></FieldLabel><input id="ac-lockout" v-model="form.rl_lockout" type="number" min="1" :disabled="saving" data-test="rl_lockout" /></div>
          </div>
        </fieldset>
        <fieldset v-show="groupShown(GROUPS[2])" class="group">
          <legend>IP filter</legend>
          <p class="lede">Decides which network addresses may reach Portcullis at all.</p>
          <div class="grid">
            <div class="field"><FieldLabel for="ac-allow" title="Allowed networks"><p>Addresses or networks that may connect. One per line, for example 10.0.0.0/8 or 192.168.1.20.</p><p>Empty allows everyone who is not denied. When filled, only these may connect.</p></FieldLabel><textarea id="ac-allow" v-model="form.allow" rows="3" spellcheck="false" :disabled="saving" data-test="allow"></textarea></div>
            <div class="field"><FieldLabel for="ac-deny" title="Denied networks"><p>Addresses or networks that may never connect. One per line, same format as allowed networks.</p><p>Empty denies no one.</p></FieldLabel><textarea id="ac-deny" v-model="form.deny" rows="3" spellcheck="false" :disabled="saving" data-test="deny"></textarea></div>
          </div>
        </fieldset>
        <fieldset v-show="groupShown(GROUPS[3])" class="group">
          <legend>Security headers and devices</legend>
          <p class="lede">Browser protections and notes about sign-ins from unfamiliar devices.</p>
          <div class="toggle-row"><ToggleSwitch :checked="form.hd_enabled" :disabled="saving" data-test="hd_enabled" @change="form.hd_enabled = ($event.target as HTMLInputElement).checked">Send security headers</ToggleSwitch><FieldLabel bare title="Send security headers"><p><b>On:</b> every response carries browser protections against framing and content sniffing. Recommended.</p><p><b>Off:</b> none are sent.</p></FieldLabel></div>
          <div class="grid">
            <div class="field"><FieldLabel for="ac-hsts" title="HSTS (seconds, 0 = off)"><p>Tells browsers to use HTTPS only for this many seconds.</p><p>0 turns it off. Turn it on only once the site is served over HTTPS, because browsers will refuse plain HTTP for that long. Example: 31536000 is one year.</p></FieldLabel><input id="ac-hsts" v-model="form.hsts" type="number" min="0" :disabled="saving" data-test="hsts" /></div>
          </div>
          <div class="toggle-row"><ToggleSwitch :checked="form.fp_enabled" :disabled="saving" data-test="fp_enabled" @change="form.fp_enabled = ($event.target as HTMLInputElement).checked">Log a login from a new device</ToggleSwitch><FieldLabel bare title="Log a login from a new device"><p><b>On:</b> the activity log notes a sign-in from a device Portcullis has not seen before for that user.</p><p><b>Off:</b> no note is made.</p></FieldLabel></div>
          <div class="signals">
            <div v-for="signal in SIGNALS" :key="signal" class="toggle-row"><ToggleSwitch :checked="form.signals.includes(signal)" :disabled="saving" :data-test="`signal-${signal}`" @change="setSignal(signal, ($event.target as HTMLInputElement).checked)">{{ signal }}</ToggleSwitch><FieldLabel :title="signal"><p v-if="signal === 'user_agent'">The browser and operating system name the request reports.</p><p v-else-if="signal === 'accept_language'">The language list the browser sends.</p><p v-else>The network part of the address the user signs in from, not the full address.</p><p>A device counts as new when any signal turned on here differs from the ones seen before.</p></FieldLabel></div>
          </div>
        </fieldset>
        <fieldset v-show="groupShown(GROUPS[4])" class="group">
          <legend>Backups</legend>
          <p class="lede">Copies of the Portcullis database, kept on a schedule.</p>
          <div class="toggle-row"><ToggleSwitch :checked="form.bk_enabled" :disabled="saving" data-test="bk_enabled" @change="form.bk_enabled = ($event.target as HTMLInputElement).checked">Back up the database</ToggleSwitch><FieldLabel bare title="Back up the database"><p><b>On:</b> Portcullis copies its database on the schedule below.</p><p><b>Off:</b> no backups are made.</p></FieldLabel></div>
          <div class="grid">
            <div class="field"><FieldLabel for="ac-keep" title="Backups to keep"><p>How many of the newest backups are kept. Older ones are deleted.</p><p>A whole number, 1 or more. Example: 14.</p></FieldLabel><input id="ac-keep" v-model="form.bk_keep" type="number" min="1" :disabled="saving" data-test="bk_keep" /></div>
            <div class="field"><FieldLabel for="ac-every" title="Hours between backups"><p>How often a backup runs.</p><p>Hours, 1 or more. Example: 24 is once a day.</p></FieldLabel><input id="ac-every" v-model="form.bk_every" type="number" min="1" :disabled="saving" data-test="bk_every" /></div>
          </div>
        </fieldset>
        <ActionMessage v-if="error" kind="error" :text="error" />
        <ActionMessage v-if="notice" kind="ok" :text="notice" data-test="notice" />
        <div v-if="saved?.stored.length" class="actions">
          <button type="button" class="chip" :disabled="saving" data-test="defaults" @click="useDefaults">Use the defaults</button>
        </div>
      </form>
    </template>
    <ConfirmModal :open="discardOpen" title="Discard unsaved changes?" message="Your app configuration changes have not been saved." confirm-label="Discard changes" @confirm="answerDiscard(true, cancel)" @close="answerDiscard(false, cancel)" />
  </section>
</template>

<style scoped>
.app-config { margin-bottom: 14px; }
.fields { display: grid; gap: 14px; padding: 16px; }
.group { display: grid; gap: 14px; margin: 0; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); }
.group legend { padding: 0 6px; font-size: 0.95em; font-weight: 600; }
.lede { margin: -6px 0 0; font-size: 0.85em; color: var(--muted); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px 18px; }
.field { display: grid; gap: 4px; min-width: 0; align-content: start; }
.field > input, .field > select, .field > textarea { width: 100%; min-width: 0; min-height: 44px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--bg); font: inherit; }
.toggle-row { display: flex; align-items: center; gap: 4px; }
.signals { display: flex; flex-wrap: wrap; gap: 4px 20px; padding-left: 4px; }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.error { margin: 0; color: var(--danger); }
.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.tools { flex-wrap: nowrap; }
</style>
