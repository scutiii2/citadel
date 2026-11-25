<script setup lang="ts">
import ActionMessage from "../components/admin/ActionMessage.vue";
import PasswordInput from "../components/PasswordInput.vue";
import PageLayout from "../components/PageLayout.vue";
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { authClient, type KnownDevice } from "../api/AuthClient";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import PanelHelp from "../components/admin/PanelHelp.vue";
import "../components/admin/admin.css";
import { useAuthStore } from "../stores/auth";
import { errorMessage, formatUtc } from "../utils/errors";

const auth = useAuthStore();
const router = useRouter();

// Theme and log out live here too, as in the Profile menu.
async function logout(): Promise<void> {
  await auth.logout();
  await router.replace({ name: "login" });
}

// The router only opens this page with an account.
const account = computed(() => auth.account!);
const initial = computed(() => account.value.username.charAt(0).toUpperCase());

// Which security form is open; one at a time keeps the page short.
const openForm = ref<"email" | "password" | null>(null);

function toggle(form: "email" | "password"): void {
  openForm.value = openForm.value === form ? null : form;
}

const emailForm = reactive({ email: "", password: "", busy: false, error: "" });
const passwordForm = reactive({ next: "", confirm: "", current: "", busy: false, error: "", done: false });

const passwordMismatch = computed(() => passwordForm.confirm !== "" && passwordForm.next !== passwordForm.confirm);

async function changeEmail(): Promise<void> {
  emailForm.error = "";
  emailForm.busy = true;
  try {
    const result = await auth.changeEmail(emailForm.password, emailForm.email.trim());
    emailForm.email = "";
    emailForm.password = "";
    if (result.account.email_verified) {
      emailForm.error = "That is already your email.";
    } else {
      // Permissions are off until the new address is verified.
      await router.replace({ name: "verify-email", query: result.verification_email_sent ? {} : { unsent: "1" } });
    }
  } catch (err) {
    emailForm.error = errorMessage(err);
  } finally {
    emailForm.busy = false;
  }
}

// Devices this account logged in from; a login from a new one is noted in
// the activity log. Forgetting one makes its next login "new" again.
const devices = ref<KnownDevice[]>([]);
const devicesError = ref("");

async function loadDevices(): Promise<void> {
  try {
    devices.value = await authClient.devices();
    devicesError.value = "";
  } catch (err) {
    devicesError.value = errorMessage(err);
  }
}

// Forgetting a device asks first, in the confirmation dialog.
const pendingForget = ref<KnownDevice | null>(null);

async function forgetDevice(device: KnownDevice): Promise<void> {
  pendingForget.value = null;
  try {
    await authClient.forgetDevice(device.id);
    devices.value = devices.value.filter((d) => d.id !== device.id);
  } catch (err) {
    devicesError.value = errorMessage(err);
  }
}

onMounted(loadDevices);

async function changePassword(): Promise<void> {
  passwordForm.error = "";
  passwordForm.done = false;
  if (passwordMismatch.value) return;
  passwordForm.busy = true;
  try {
    await auth.changePassword(passwordForm.current, passwordForm.next);
    passwordForm.next = "";
    passwordForm.confirm = "";
    passwordForm.current = "";
    passwordForm.done = true;
  } catch (err) {
    passwordForm.error = errorMessage(err);
  } finally {
    passwordForm.busy = false;
  }
}
</script>

<template>
  <PageLayout v-if="auth.account" class="account-view admin-panel" title="Profile" wide>
    <div class="column">
      <div v-if="!account.email_verified" class="banner" role="status">
        <span>Verify your email address to use this workspace.</span>
        <button type="button" class="chip verify" @click="router.push('/verify-email')">Verify now</button>
      </div>

      <section class="admin-panel-card hero" aria-labelledby="account-identity">
        <h2 id="account-identity" class="sr-only">Account</h2>
        <div class="profile">
          <div class="avatar" aria-hidden="true">{{ initial }}</div>
          <div class="who">
            <div class="name">{{ account.username }}</div>
            <div class="email">{{ account.email }}</div>
            <div class="hero-tags">
              <span class="status" :class="{ verified: account.email_verified }">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6z" /><path v-if="account.email_verified" d="m8.5 12 2.5 2.5 4.5-5" /><path v-else d="M12 8v5m0 3v.1" /></svg>
                {{ account.email_verified ? 'Email verified' : 'Verification needed' }}
              </span>
              <span v-for="r in account.roles" :key="r" class="tag role">{{ r }}</span>
            </div>
          </div>
          <div class="hero-actions">
            <PanelHelp title="Account"><p>Your identity in this workspace, how you sign in, and the devices you have used. Only you can change your email and password here.</p><p>Theme and sidebar choices are in Settings.</p></PanelHelp>
            <button type="button" class="chip logout" @click="logout">Log out</button>
          </div>
        </div>
      </section>

      <div class="split">
      <section class="admin-panel-card security" aria-labelledby="account-security">
        <header class="admin-panel-head">
          <h2 id="account-security">Security</h2>
          <div class="admin-panel-tools"><PanelHelp title="Security"><p>Change the email address or password you sign in with. A new email must be verified with an emailed code before you can use the workspace again.</p><p>Password changes sign out your other devices.</p></PanelHelp></div>
        </header>
        <div class="rows">
          <div class="row">
            <div class="row-copy"><div class="row-title">Email address</div><div class="muted small">{{ account.email }}</div></div>
            <button type="button" class="chip toggle-email" :aria-expanded="openForm === 'email'" aria-controls="account-email-form" @click="toggle('email')">{{ openForm === 'email' ? 'Close' : 'Change email' }}</button>
          </div>
          <form v-if="openForm === 'email'" id="account-email-form" class="stack" :aria-busy="emailForm.busy" @submit.prevent="changeEmail">
            <label>New email<input v-model="emailForm.email" type="email" autocomplete="email" required /></label>
            <PasswordInput v-model="emailForm.password" label="Current password" autocomplete="current-password" required />
            <ActionMessage v-if="emailForm.error" kind="error" :text="emailForm.error" />
            <button class="primary" :disabled="emailForm.busy" :aria-busy="emailForm.busy">Change email</button>
          </form>
          <div class="row">
            <div class="row-copy"><div class="row-title">Password</div><div class="muted small">Use a strong, unique password.</div></div>
            <button type="button" class="chip toggle-password" :aria-expanded="openForm === 'password'" aria-controls="account-password-form" @click="toggle('password')">{{ openForm === 'password' ? 'Close' : 'Change password' }}</button>
          </div>
          <form v-if="openForm === 'password'" id="account-password-form" class="stack" :aria-busy="passwordForm.busy" @submit.prevent="changePassword">
            <PasswordInput v-model="passwordForm.next" label="New password" autocomplete="new-password" minlength="8" required />
            <PasswordInput v-model="passwordForm.confirm" label="Repeat new password" autocomplete="new-password" required />
            <PasswordInput v-model="passwordForm.current" label="Current password" autocomplete="current-password" required />
            <ActionMessage v-if="passwordMismatch" kind="error" text="The new passwords don't match." />
            <ActionMessage v-else-if="passwordForm.error" kind="error" :text="passwordForm.error" />
            <ActionMessage v-else-if="passwordForm.done" kind="ok" text="Password changed." />
            <button class="primary" :disabled="passwordForm.busy || passwordMismatch" :aria-busy="passwordForm.busy">Change password</button>
          </form>
        </div>
      </section>

      <section class="admin-panel-card" aria-labelledby="account-access">
        <header class="admin-panel-head">
          <h2 id="account-access">Roles &amp; access</h2>
          <div class="admin-panel-tools"><PanelHelp title="Roles &amp; access"><p>The roles you hold and the permissions they grant in this workspace. Roles are managed by your workspace administrator.</p></PanelHelp></div>
        </header>
        <div class="access-body">
          <div class="roles"><span v-for="r in account.roles" :key="r" class="tag role">{{ r }}</span><span v-if="!account.roles.length" class="muted small">No roles</span></div>
          <details class="permissions">
            <summary><span>{{ account.permissions.length }} {{ account.permissions.length === 1 ? 'permission' : 'permissions' }}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg></summary>
            <p v-if="auth.needsVerification && account.permissions.length" class="muted small">Permissions are inactive until your email is verified.</p>
            <div class="perm-list"><code v-for="p in account.permissions" :key="p">{{ p }}</code></div>
          </details>
        </div>
      </section>
      </div>

      <section class="admin-panel-card" aria-labelledby="account-devices">
        <header class="admin-panel-head">
          <h2 id="account-devices">Remembered devices</h2>
          <div class="admin-panel-tools">
            <span v-if="!devicesError" class="tag">{{ devices.length }} {{ devices.length === 1 ? 'device' : 'devices' }}</span>
            <PanelHelp title="Remembered devices"><p>Devices you have used to sign in. A login from a new device is noted in the activity log.</p><p>Forgetting a device makes its next sign-in appear as a new device.</p></PanelHelp>
          </div>
        </header>
        <ActionMessage v-if="devicesError" kind="error" :text="devicesError" class="device-message" />
        <p v-else-if="devices.length === 0" class="device-message muted">None recorded yet.</p>
        <ul v-else class="devices">
          <li v-for="d in devices" :key="d.id" :title="d.user_agent || '(no browser name)'">
            <svg class="device-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></svg>
            <div class="device-main">
              <div class="device-name"><strong>{{ d.label }}</strong><span v-if="d.current" class="tag ok">This device</span></div>
              <div class="device-meta"><span>Last used · {{ formatUtc(d.last_seen_at) }}</span><span>{{ d.ip_subnet }}</span><span>First seen · {{ formatUtc(d.first_seen_at) }}</span></div>
            </div>
            <button v-if="!d.current" type="button" class="chip forget" @click="pendingForget = d">Forget</button>
          </li>
        </ul>
      </section>

      <ConfirmModal v-if="pendingForget" open title="Forget device" :message="`Forget ${pendingForget.label}? Its next login is noted in the activity log as a new device.`" confirm-label="Forget" @confirm="forgetDevice(pendingForget)" @close="pendingForget = null" />
    </div>
  </PageLayout>
</template>

<style scoped>
.column { display: grid; gap: 16px; }
svg { fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex: none; }
.muted { color: var(--muted); }
.small { font-size: 0.85em; }
.profile { display: flex; align-items: center; gap: 18px; padding: 20px 18px; }
.split { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; align-items: start; }
.hero-tags { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 10px; }
.hero-actions { display: flex; align-items: center; gap: 8px; flex: none; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.avatar { display: grid; flex: none; place-items: center; width: 64px; height: 64px; border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border)); border-radius: var(--radius-md); background: color-mix(in srgb, var(--accent) 12%, var(--surface)); color: var(--accent); font-size: 1.6em; font-weight: 650; }
.who { flex: 1; min-width: 0; }
.name { font-size: 1.3em; font-weight: 650; overflow-wrap: anywhere; }
.email { margin-top: 2px; color: var(--muted); font-size: 0.9em; overflow-wrap: anywhere; }
.status { display: inline-flex; align-items: center; gap: 6px; flex: none; font-size: 0.85em; color: var(--warning); }
.status.verified { color: var(--success); }
.status svg { width: 16px; height: 16px; }
.rows { display: grid; }
.row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-top: 1px solid var(--border); }
.row:first-child { border-top: 0; }
.row-copy { min-width: 0; overflow-wrap: anywhere; }
.row-title { font-size: 0.9em; font-weight: 600; }
.row .small { margin-top: 2px; }
.chip { display: inline-flex; flex: none; align-items: center; min-height: 36px; padding: 5px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); background: transparent; color: var(--text); cursor: pointer; font: inherit; font-size: 0.84rem; }
.chip:hover { background: var(--surface); }
.tag { display: inline-flex; align-items: center; padding: 2px 9px; border: 1px solid var(--border); border-radius: var(--radius-full); background: var(--code-bg); color: var(--muted); font-size: 0.75em; overflow-wrap: anywhere; }
.tag.ok { color: var(--success); border-color: color-mix(in srgb, var(--success) 30%, var(--border)); }
.tag.role { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 25%, var(--border)); background: color-mix(in srgb, var(--accent) 7%, var(--surface)); }
.banner { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px; padding: 10px 14px; border: 1px solid color-mix(in srgb, var(--warning) 35%, var(--border)); border-radius: var(--radius-lg); background: color-mix(in srgb, var(--warning) 5%, var(--surface)); color: var(--warning); font-size: 0.9em; }
.stack { display: grid; gap: 10px; margin: 0 14px 14px; padding: 14px; border-radius: var(--radius-md); background: var(--code-bg); }
.stack label { display: grid; gap: 5px; font-size: 0.85em; }
.stack input { width: 100%; min-width: 0; min-height: 44px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); background: var(--bg); font: inherit; }
.primary { display: inline-flex; align-items: center; gap: 8px; justify-self: start; min-height: 36px; padding: 5px 16px; border: none; border-radius: var(--radius-md); background: var(--accent); color: var(--accent-contrast); cursor: pointer; font: inherit; font-size: 0.85em; font-weight: 650; }
.primary:disabled { opacity: 0.5; cursor: default; }
.error { margin: 0; color: var(--danger); }
.notice { margin: 0; color: var(--success); }
.access-body { display: grid; gap: 12px; padding: 14px; }
.roles { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.permissions summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; cursor: pointer; font-size: 0.85em; list-style: none; }
.permissions summary::-webkit-details-marker { display: none; }
.permissions summary svg { width: 15px; height: 15px; color: var(--muted); }
.permissions[open] summary svg { transform: rotate(90deg); }
.permissions > p { margin: 10px 0 0; }
.perm-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.perm-list code { max-width: 100%; padding: 4px 6px; border-radius: var(--radius-sm); background: var(--code-bg); color: var(--muted); font: 0.7em var(--mono); overflow-wrap: anywhere; }
.devices { margin: 0; padding: 0; list-style: none; }
.devices li { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-top: 1px solid var(--border); }
.device-icon { box-sizing: border-box; width: 36px; height: 36px; padding: 9px; border-radius: var(--radius-md); background: var(--code-bg); color: var(--muted); }
.device-main { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.device-name { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 0.9em; }
.device-meta { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 4px; color: var(--muted); font-size: 0.75em; }
.device-message { margin: 0; padding: 14px; font-size: 0.9em; }
@media (max-width: 767px) {
  .profile { flex-wrap: wrap; }
  .split { grid-template-columns: minmax(0, 1fr); }
  .chip, .primary { min-height: 44px; }
  .row { flex-wrap: wrap; }
  .devices li { align-items: flex-start; }
}
</style>
