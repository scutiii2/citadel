<script setup lang="ts">
import { FieldLabel } from "@citadel/ui";
import { ActionMessage } from "@citadel/ui";
import { computed, onMounted, ref } from "vue";
import { emailSettingsClient, type EmailChanges, type EmailSettings } from "../api/EmailSettingsClient";
import SettingsPanel from "../components/admin/SettingsPanel.vue";
import { PasswordInput } from "@citadel/ui";
import { ToggleSwitch } from "@citadel/ui";
import { errorMessage } from "../utils/errors";

/** The SMTP account Armory sends mail through. Saved in Armory's database; a send uses the saved values at once.
 * The password is write-only: the page only says whether one is saved. */
const saved = ref<EmailSettings>({ configured: false });
const server = ref("");
const port = ref("");
const security = ref("");
const from = ref("");
const recipients = ref("");
const domains = ref("");
const password = ref("");
const clearPassword = ref(false);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");
const search = ref("");
const panel = ref<InstanceType<typeof SettingsPanel>>();

const lines = (text: string) => text.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);

function apply(view: EmailSettings) {
  saved.value = view;
  server.value = view.smtp_server ?? "";
  port.value = view.smtp_port ? String(view.smtp_port) : "";
  security.value = view.security ?? "";
  from.value = view.from ?? "";
  recipients.value = (view.to ?? []).join("\n");
  domains.value = (view.allowed_recipient_domains ?? []).join("\n");
  password.value = "";
  clearPassword.value = false;
}

onMounted(async () => {
  try {
    apply(await emailSettingsClient.get());
  } catch (err) {
    error.value = errorMessage(err);
  } finally {
    loading.value = false;
  }
});

const same = (a: string[], b: string[] | undefined) => a.join("\n") === (b ?? []).join("\n");

/** Only what differs from the saved values, so an untouched password stays. */
const changes = computed<EmailChanges>(() => {
  const out: EmailChanges = {};
  if (server.value.trim() !== (saved.value.smtp_server ?? "")) out.smtp_server = server.value.trim();
  const typedPort = String(port.value ?? "").trim(); // a number input hands back a number
  if (typedPort !== (saved.value.smtp_port ? String(saved.value.smtp_port) : "")) out.smtp_port = typedPort === "" ? null : Number(typedPort);
  if (security.value !== (saved.value.security ?? "")) out.security = security.value || null;
  if (from.value.trim() !== (saved.value.from ?? "")) out.from = from.value.trim();
  if (!same(lines(recipients.value), saved.value.to)) out.to = lines(recipients.value);
  if (!same(lines(domains.value), saved.value.allowed_recipient_domains)) out.allowed_recipient_domains = lines(domains.value);
  if (password.value) out.password = password.value;
  else if (clearPassword.value) out.password = null;
  return out;
});
const changed = computed(() => Object.keys(changes.value).length > 0);

async function save() {
  if (!changed.value || saving.value) return;
  saving.value = true;
  error.value = notice.value = "";
  await panel.value?.keepFocus(async () => {
    try {
      apply(await emailSettingsClient.save(changes.value));
      notice.value = "Saved. The next email uses it.";
    } catch (err) {
      error.value = errorMessage(err);
    } finally {
      saving.value = false;
    }
  });
}

function discard() {
  apply(saved.value);
  error.value = notice.value = "";
}
</script>

<template>
  <SettingsPanel ref="panel" v-model:search="search" title="Email" heading="Mail account" label="email settings" :dirty="changed" :saving="saving" @save="save" @discard="discard">
    <template #help>
      <p>The mail account Armory sends from. It is saved in Armory's database, and the next email uses it at once.</p>
      <p>Gmail, Outlook, Yahoo and iCloud need an app password. The password is never shown again after it is saved.</p>
    </template>
    <p v-if="loading" class="note muted" role="status">Loading…</p>
    <form v-else class="form" data-test="form" @submit.prevent="save">
      <p v-if="!saved.configured" class="note muted" data-test="empty">Email is not set up. Fill in the server, port and sender, then save.</p>
      <ActionMessage v-if="error" kind="error" :text="error" class="note" />
      <p v-if="notice" class="note muted" role="status" data-test="notice">{{ notice }}</p>
      <section v-show="panel?.matches('Mail server', 'Server', 'Port', 'Connection', 'Sender address', 'Password')" class="group fields" aria-labelledby="smtp-title">
        <h3 id="smtp-title">Mail server</h3>
        <p class="lede">The account Armory sends mail through.</p>
        <div class="field">
          <FieldLabel title="Server" for="smtp-server">The address of your mail provider's SMTP server, such as smtp.gmail.com.</FieldLabel>
          <input id="smtp-server" v-model="server" :disabled="saving" autocomplete="off" spellcheck="false" placeholder="smtp.gmail.com" data-test="server" />
        </div>
        <div class="field">
          <FieldLabel title="Port" for="smtp-port">The server's port, such as 465 for ssl or 587 for starttls. 1 to 65535.</FieldLabel>
          <input id="smtp-port" v-model="port" type="number" min="1" max="65535" step="1" :disabled="saving" placeholder="465" data-test="port" />
        </div>
        <div class="field">
          <FieldLabel title="Connection" for="smtp-security">How the connection is protected: ssl, starttls, or none (no encryption). Left on the default, Armory chooses from the port: 465 is ssl, any other port is starttls.</FieldLabel>
          <select id="smtp-security" v-model="security" :disabled="saving" data-test="security">
            <option value="">Choose from the port (465 is ssl, others starttls)</option>
            <option value="ssl">ssl</option>
            <option value="starttls">starttls</option>
            <option value="none">none (no encryption)</option>
          </select>
        </div>
        <div class="field">
          <FieldLabel title="Sender address" for="smtp-from">The address the mail is sent from.</FieldLabel>
          <input id="smtp-from" v-model="from" type="email" :disabled="saving" autocomplete="off" data-test="from" />
        </div>
        <div class="field">
          <PasswordInput
            v-model="password"
            label="Password"
            autocomplete="off"
            data-test="password"
            :disabled="saving || clearPassword"
            :placeholder="saved.has_password ? 'Leave empty to keep the saved password' : 'None saved (a relay without a login needs none)'"
          />
          <p class="help" data-test="password-state">{{ saved.has_password ? "A password is saved. It is never shown again." : "No password is saved." }}</p>
          <ToggleSwitch v-if="saved.has_password" :checked="clearPassword" :disabled="saving" data-test="clear-password" @change="clearPassword = ($event.target as HTMLInputElement).checked">Remove the saved password</ToggleSwitch>
        </div>
      </section>

      <section v-show="panel?.matches('Recipients', 'Standing recipients', 'Domains')" class="group fields" aria-labelledby="who-title">
        <h3 id="who-title">Recipients</h3>
        <p class="lede">Who the mail may be sent to.</p>
        <div class="field">
          <FieldLabel title="Standing recipients" for="smtp-to">One address per line. Empty is fine if every send names its own address.</FieldLabel>
          <textarea id="smtp-to" v-model="recipients" rows="3" :disabled="saving" spellcheck="false" data-test="to"></textarea>
        </div>
        <div class="field">
          <FieldLabel title="Domains a caller may name any address at" for="smtp-domains">One domain per line. Empty means no domain.</FieldLabel>
          <textarea id="smtp-domains" v-model="domains" rows="3" :disabled="saving" spellcheck="false" data-test="domains"></textarea>
        </div>
      </section>
    </form>
  </SettingsPanel>
</template>

<style scoped>
.note { margin: 0; padding: 12px 16px 0; }
.error { color: var(--danger); }
.muted { color: var(--muted); }
.form { display: grid; }
.group { display: grid; gap: 16px; max-width: 720px; padding: 16px; }
.group + .group { border-top: 1px solid var(--border); }
.group h3 { margin: 0; font-size: 1em; }
.field { display: grid; gap: 4px; min-width: 0; }
.field > label:first-child { font-size: 0.9em; font-weight: 600; }
.field > input, .field > select, .field > textarea { width: 100%; min-width: 0; min-height: 44px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); }
.help { margin: 0; font-size: 0.85em; color: var(--muted); }
.group.fields { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); max-width: none; align-items: start; }
.group.fields > h3, .group.fields > .lede { grid-column: 1 / -1; }
.lede { margin: -8px 0 0; color: var(--muted); font-size: 0.9em; }
</style>
