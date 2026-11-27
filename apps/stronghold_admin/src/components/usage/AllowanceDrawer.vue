<script setup lang="ts">
import { ActionMessage, ConfirmModal, RecordDrawer } from "@citadel/ui";
import { computed, ref, watch } from "vue";
import type { AccountUsage } from "../../api/UsageClient";
import {
  ACTION_LABELS, KIND_OPTIONS, blankForm, confirmText, formProblem, needsConfirm, resultMessage, sendAllowance,
  type AllowanceAction, type AllowanceOutcome,
} from "../../utils/allowance";
import { errorMessage } from "../../utils/errors";
import SegmentedControl from "../SegmentedControl.vue";
import RecipientPicker from "./RecipientPicker.vue";

/** One drawer for the three actions. A usage reset, and anything for all users, is confirmed first. */
const props = defineProps<{ action: AllowanceAction | null; accounts: AccountUsage[]; fallbackFocus?: () => void }>();
const emit = defineEmits<{ close: []; done: [outcome: AllowanceOutcome] }>();

/** Kept while the drawer closes, so its title and fields do not change under the reader. */
const shown = ref<AllowanceAction>("resets");
const form = ref(blankForm());
const busy = ref(false);
const error = ref("");
const asking = ref<"send" | "discard" | null>(null);
let run = 0; // a reply for a drawer that has since closed is dropped

watch(() => props.action, (action) => {
  run += 1;
  asking.value = null;
  busy.value = false;
  if (!action) return;
  shown.value = action;
  form.value = blankForm();
  error.value = "";
}, { immediate: true });

const enabled = computed(() => props.accounts.filter((account) => account.is_active).length);
const problem = computed(() => formProblem(shown.value, form.value));
const dirty = computed(() => JSON.stringify(form.value) !== JSON.stringify(blankForm()));

async function send(): Promise<void> {
  asking.value = null;
  const mine = (run += 1);
  const action = shown.value;
  busy.value = true;
  error.value = "";
  try {
    const result = await sendAllowance(action, form.value);
    if (mine === run) emit("done", resultMessage(action, result));
  } catch (err) {
    if (mine === run) error.value = errorMessage(err);
  } finally {
    if (mine === run) busy.value = false;
  }
}

function submit(): void {
  if (busy.value || asking.value) return;
  // Checked again here: a date that was ahead may have passed while the drawer was open.
  const wrong = formProblem(shown.value, form.value);
  if (wrong) { error.value = wrong; return; }
  if (needsConfirm(shown.value, form.value)) asking.value = "send";
  else void send();
}

function requestClose(): void {
  if (busy.value) return;
  if (dirty.value) asking.value = "discard";
  else emit("close");
}

function confirmed(): void {
  if (asking.value === "send") { void send(); return; }
  asking.value = null;
  emit("close");
}
</script>

<template>
  <RecordDrawer :open="action !== null" :title="ACTION_LABELS[shown]" :busy="busy" :note="problem" :fallback-focus="fallbackFocus" @close="requestClose">
    <div class="allowance-form">
      <ActionMessage v-if="error" kind="error" :text="error" />
      <RecipientPicker v-model:all="form.all" v-model:ids="form.ids" :accounts="accounts" :disabled="busy" />
      <fieldset class="fields" :disabled="busy">
        <SegmentedControl v-model="form.windows" :options="KIND_OPTIONS" :label="shown === 'resets' ? 'Reset kind' : 'Windows'" />
        <label v-if="shown === 'resets'">Resets per account
          <input v-model="form.count" type="number" min="1" max="20" step="1" data-test="count" />
        </label>
        <label v-if="shown === 'boost'">Boost (percent)
          <input v-model="form.percent" type="number" min="1" max="1000" step="1" data-test="percent" />
        </label>
        <label v-if="shown !== 'clear'">{{ shown === "boost" ? "Ends" : "Expires (optional)" }}
          <input v-model="form.until" type="datetime-local" data-test="until" />
        </label>
        <p v-if="shown === 'resets'" class="muted">An account holds at most 100 unused resets; one at the limit is skipped.</p>
        <p v-if="shown === 'clear'" class="muted">Sets the chosen windows to zero now. Usage reports keep every record, and no free reset is spent.</p>
        <p v-if="shown === 'boost'" class="muted">When several boosts are active, the highest applies. An unlimited window stays unlimited.</p>
      </fieldset>
    </div>
    <template #footer>
      <button type="button" class="chip" :disabled="busy" @click="requestClose">Cancel</button>
      <button type="button" class="primary" data-test="send" :disabled="busy || !!problem" :aria-busy="busy" @click="submit">{{ ACTION_LABELS[shown] }}</button>
    </template>
  </RecordDrawer>
  <ConfirmModal
    :open="asking !== null"
    :title="asking === 'discard' ? 'Discard changes?' : `${ACTION_LABELS[shown]}?`"
    :message="asking === 'discard' ? 'Your changes will be lost.' : confirmText(shown, form, enabled)"
    :confirm-label="asking === 'discard' ? 'Discard changes' : ACTION_LABELS[shown]"
    :danger="asking === 'send' && shown === 'clear'"
    @confirm="confirmed"
    @close="asking = null"
  />
</template>

<style scoped>
.allowance-form { display: grid; gap: 18px; padding-top: 12px; }
.fields { display: grid; gap: 12px; min-width: 0; margin: 0; padding: 0; border: 0; }
.fields label { display: grid; gap: 4px; font-size: 0.9em; font-weight: 600; }
.fields input { width: 100%; min-width: 0; min-height: 44px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg); color: var(--text); font: inherit; font-weight: 400; }
.fields input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.muted { margin: 0; color: var(--muted); font-size: 0.85em; }
</style>
