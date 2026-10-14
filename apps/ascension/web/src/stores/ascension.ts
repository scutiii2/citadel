import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";
import {
  useAscensionClient,
  type ActionChoice,
  type BattleMode,
  type BattleView,
  type Catalog,
  type CopyPurchase,
  type EmblemPurchase,
  type EncounterPreview,
  type Preset,
  type Profile,
  type ShopOffer,
  type ShopWindow,
  type Sale,
  type StarUp,
  type TierUp,
  type LearnResult,
  type LoadoutResult,
  type LoadoutSlot,
  type StartBattleInput,
  type TrialProgress,
  type TrialPreparation,
  type ExpeditionReceipt,
  type ExpeditionStatus,
  newIdempotencyKey,
} from "../api/AscensionClient";
import { ApiError, UnauthorizedError } from "../api/http";
import { errorMessage } from "../utils/errors";
import { useSessionStore } from "./session";

/** Pause between autonomous rounds, so the round log stays readable. */
export const ROUND_PACE_MS = 1500;
/** How often a lost connection is tried again. */
export const RECONNECT_MS = 3000;
/** How often the EMBLEM prompt's countdown is redrawn. */
const PROMPT_TICK_MS = 200;

/** The Ascension page's state: catalog, profile, the current encounter and
 * battle, and the battle loop. The loop runs only while the page is attached
 * (mounted or reactivated in KeepAlive) and visible; Ascension keeps the
 * battle between rounds, so stopping is always safe. Changes resolve to null
 * on failure and say why in `error` (or `unavailable` on 502). */
export const useAscensionStore = defineStore("ascension", () => {
  const session = useSessionStore();
  const ascensionClient = useAscensionClient();

  let observationEpoch = 0;
  let profileReadSerial = 0;
  let expeditionReadSerial = 0;
  const activitySelection = ref<'hub' | 'hunt' | 'trial' | 'expedition'>('hub');
  const huntDifficultyId = ref('outskirts');
  const trialTypeId = ref('enchant');
  const trialStage = ref(1);
  const trials = ref<TrialProgress | null>(null);
  const trialPreparation = ref<TrialPreparation | null>(null);
  const expeditionStatus = ref<ExpeditionStatus | null>(null);
  const expeditionObservedAt = ref(0);
  const expeditionReceipt = ref<ExpeditionReceipt | null>(null);
  const activities = computed(() => catalog.value?.activities ?? null);
  function observeExpedition(status: ExpeditionStatus): void {
    expeditionStatus.value = status;
    expeditionObservedAt.value = performance.now();
  }
  function restoreActivity(context: BattleView['activity']): void {
    if (context?.kind === 'trial') {
      activitySelection.value = 'trial'; trialTypeId.value = context.trial_type ?? 'enchant'; trialStage.value = context.trial_stage ?? 1;
    } else { activitySelection.value = 'hunt'; huntDifficultyId.value = context?.difficulty_id ?? 'outskirts'; }
  }
  const catalog = ref<Catalog | null>(null);
  const profile = ref<Profile | null>(null);
  const squadIds = computed(() => profile.value?.squad ?? []);
  const squadMembers = computed(() => squadIds.value.flatMap(id => {
    const member = profile.value?.ascendeds.find(a => a.ascended_id === id);
    return member ? [member] : [];
  }));
  /** GET /profile answered 404: the account has not chosen a starter yet. */
  const needsStarter = ref(false);
  const encounter = ref<EncounterPreview | null>(null);
  const battle = ref<BattleView | null>(null);
  const loading = ref(false);
  const loaded = ref(false);
  const unavailable = ref(false);
  const reconnecting = ref(false);
  const busy = ref(false);
  const battleBusy = ref(false);
  const error = ref("");
  /** Seconds left on the EMBLEM prompt, counted on this device's monotonic clock. */
  const promptRemaining = ref(0);
  /** The account's current shop window and, on this device's clock (epoch seconds), when it ends. */
  const shop = ref<ShopWindow | null>(null);
  const shopEndsAt = ref(0);
  const promptTotal = ref(0);

  const promptOpen = computed(() => {
    const current = battle.value;
    return current !== null && current.status === "active" && current.phase === "awaiting_emblem" && current.prompt !== null;
  });

  let attached = false;
  // Bumped on every account change: answers for the previous account are ignored.
  let generation = 0;
  let roundTimer: ReturnType<typeof setTimeout> | null = null;
  let promptTimer: ReturnType<typeof setTimeout> | null = null;
  let promptTick: ReturnType<typeof setInterval> | null = null;
  let promptEndsAt = 0;
  let promptRevision: number | null = null;

  function visible(): boolean {
    return typeof document === "undefined" || document.visibilityState !== "hidden";
  }

  function running(): boolean {
    return attached && visible() && session.status === "ready";
  }

  function clearTimers(): void {
    if (roundTimer !== null) clearTimeout(roundTimer);
    if (promptTimer !== null) clearTimeout(promptTimer);
    if (promptTick !== null) clearInterval(promptTick);
    roundTimer = null;
    promptTimer = null;
    promptTick = null;
  }

  function startPrompt(view: BattleView, secondsLeft: number): void {
    if (promptRevision !== view.revision) {
      promptRevision = view.revision;
      promptTotal.value = Math.max(0, secondsLeft);
    }
    const ms = Math.max(0, secondsLeft * 1000);
    promptEndsAt = performance.now() + ms;
    promptRemaining.value = ms / 1000;
    promptTick = setInterval(() => {
      promptRemaining.value = Math.max(0, (promptEndsAt - performance.now()) / 1000);
    }, PROMPT_TICK_MS);
    // At zero Ascension settles the prompt itself (the Ascended's own choice, or a basic ATTACK).
    promptTimer = setTimeout(() => {
      promptRemaining.value = 0;
      void advance();
    }, ms);
  }

  function schedule(): void {
    clearTimers();
    const current = battle.value;
    if (!running() || current === null || current.status !== "active") return;
    if (reconnecting.value) {
      roundTimer = setTimeout(() => void refreshBattle(), RECONNECT_MS);
      return;
    }
    if (current.phase === "awaiting_emblem" && current.prompt !== null) {
      startPrompt(current, current.prompt.seconds_left);
      return;
    }
    if (current.mode === "autonomous" && current.phase === "choosing") {
      roundTimer = setTimeout(() => void advance(), ROUND_PACE_MS);
    }
  }

  function setBattle(view: BattleView): void {
    const justFinished = view.status !== "active" && battle.value?.status === "active";
    battle.value = view;
    restoreActivity(view.activity);
    if (profile.value !== null) profile.value = { ...profile.value, emblems: view.emblems };
    // XP, Insignia, copies and faint times changed with the result.
    if (justFinished) { observationEpoch += 1; void refreshProfile(); }
    schedule();
  }

  function report(err: unknown): void {
    if (err instanceof UnauthorizedError) return;
    if (err instanceof ApiError && err.status === 502) {
      unavailable.value = true;
      clearTimers();
      return;
    }
    error.value = errorMessage(err);
  }

  async function refreshProfile(): Promise<void> {
    const started = generation;
    const epoch = observationEpoch;
    const read = ++profileReadSerial;
    try {
      const next = await ascensionClient.profile();
      if (started === generation && epoch === observationEpoch && read === profileReadSerial) { profile.value = next; if (next.server_now !== undefined) observeExpedition({ server_now: next.server_now, expedition: next.expedition ?? null }); }
    } catch (err) {
      if (started === generation && epoch === observationEpoch && read === profileReadSerial) report(err);
    }
  }

  /** One GET of the current battle: after a 409, on return to the page, and while reconnecting. */
  async function refreshBattle(): Promise<void> {
    const current = battle.value;
    if (current === null) return;
    const started = generation;
    try {
      const view = await ascensionClient.battle(current.id);
      if (started !== generation) return;
      reconnecting.value = false;
      setBattle(view);
    } catch (err) {
      if (started !== generation) return;
      if (err instanceof ApiError) {
        report(err);
        return;
      }
      reconnecting.value = true;
      schedule();
    }
  }

  async function battleCall(call: (current: BattleView) => Promise<BattleView>): Promise<void> {
    const current = battle.value;
    if (current === null || battleBusy.value) return;
    const started = generation;
    clearTimers();
    battleBusy.value = true;
    error.value = "";
    try {
      const view = await call(current);
      if (started !== generation) return;
      battleBusy.value = false;
      setBattle(view);
    } catch (err) {
      if (started !== generation) return;
      battleBusy.value = false;
      if (!(err instanceof ApiError)) {
        reconnecting.value = true;
        schedule();
        return;
      }
      if (err.status === 409) {
        // Stale round or revision, wrong phase, a prompt answered too late: show
        // why, read the battle once, never resend the action on its own.
        error.value = err.message;
        await refreshBattle();
        return;
      }
      if (err.status === 404) {
        error.value = err.message;
        battle.value = null;
        void refreshProfile();
        return;
      }
      report(err);
    } finally {
      if (started === generation) battleBusy.value = false;
    }
  }

  function advance(): Promise<void> {
    return battleCall((b) => ascensionClient.advance(b.id, { round: b.round, revision: b.revision }));
  }

  function act(choice: ActionChoice): Promise<void> {
    return battleCall((b) => ascensionClient.action(b.id, { round: b.round, revision: b.revision }, choice));
  }

  function answerEmblem(tier: string): Promise<void> {
    if (!promptOpen.value || promptRemaining.value <= 0) return Promise.resolve();
    return battleCall((b) => ascensionClient.emblem(b.id, { round: b.round, revision: b.revision }, tier));
  }

  function setMode(mode: BattleMode): Promise<void> {
    return battleCall((b) => ascensionClient.setMode(b.id, { round: b.round, revision: b.revision }, mode, null));
  }

  function forfeit(): Promise<void> {
    return battleCall((b) => ascensionClient.forfeit(b.id));
  }

  /** Leaves a finished battle's result for the encounter screen. */
  function closeBattle(): void {
    clearTimers();
    restoreActivity(battle.value?.activity);
    battle.value = null;
    if (activitySelection.value === "trial") void loadTrials();
    reconnecting.value = false;
    error.value = "";
    void refreshProfile();
  }

  async function loadProfile(started: number): Promise<void> {
    const epoch = observationEpoch;
    const read = ++profileReadSerial;
    let next: Profile;
    try {
      next = await ascensionClient.profile();
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        if (started === generation && epoch === observationEpoch && read === profileReadSerial) {
          profile.value = null;
          needsStarter.value = true;
          encounter.value = null;
          battle.value = null;
        }
        return;
      }
      throw err;
    }
    if (started !== generation || epoch !== observationEpoch || read !== profileReadSerial) return;
    profile.value = next;
    if (next.server_now !== undefined) observeExpedition({ server_now: next.server_now, expedition: next.expedition ?? null });
    needsStarter.value = false;
    // A reload restores what was open; it never rolls again.
    if (next.active_battle !== null) {
      const view = await ascensionClient.battle(next.active_battle);
      if (started !== generation || epoch !== observationEpoch || read !== profileReadSerial) return;
      encounter.value = null;
      setBattle(view);
    } else if (next.pending_encounter !== null) {
      const preview = await ascensionClient.encounter(next.pending_encounter);
      if (started !== generation || epoch !== observationEpoch || read !== profileReadSerial) return;
      encounter.value = preview;
      restoreActivity(preview.activity);
    } else {
      encounter.value = null;
    }
  }

  async function load(): Promise<void> {
    const started = generation;
    loading.value = true;
    unavailable.value = false;
    error.value = "";
    try {
      if (catalog.value === null) {
        const fetched = await ascensionClient.catalog();
        if (started !== generation) return;
        catalog.value = fetched;
      }
      await loadProfile(started);
      if (started === generation) loaded.value = true;
    } catch (err) {
      if (started === generation) report(err);
    } finally {
      if (started === generation) loading.value = false;
    }
  }

  function retry(): Promise<void> {
    loaded.value = false;
    return load();
  }

  async function resume(): Promise<void> {
    if (!running()) return;
    if (!loaded.value) {
      if (!loading.value) await load();
      return;
    }
    if (battle.value?.status === "active") await refreshBattle();
    else await refreshProfile();
  }

  function onVisibilityChange(): void {
    if (visible()) void resume();
    else clearTimers();
  }

  /** The page is showing: load or refresh, and let the loop run. */
  function attach(): void {
    if (attached) return;
    attached = true;
    document.addEventListener("visibilitychange", onVisibilityChange);
    void resume();
  }

  /** The page is gone (unmounted, or deactivated in KeepAlive): stop the loop. */
  function detach(): void {
    if (!attached) return;
    attached = false;
    document.removeEventListener("visibilitychange", onVisibilityChange);
    clearTimers();
  }

  async function mutate<T>(call: () => Promise<T>, apply: (result: T) => void | Promise<void>): Promise<T | null> {
    const started = generation;
    observationEpoch += 1;
    busy.value = true;
    error.value = "";
    try {
      const result = await call();
      if (started !== generation) return null;
      observationEpoch += 1;
      await apply(result);
      return result;
    } catch (err) {
      if (started === generation) { observationEpoch += 1; report(err); }
      return null;
    } finally {
      if (started === generation) busy.value = false;
    }
  }

  function createProfile(starterAscendedId: string): Promise<Profile | null> {
    return mutate(
      () => ascensionClient.createProfile(starterAscendedId),
      (created) => {
        profile.value = created;
        needsStarter.value = false;
      },
    );
  }

  function rollEncounter(): Promise<EncounterPreview | null> {
    return mutate(
      () => ascensionClient.rollEncounter(undefined, activitySelection.value === "hunt" ? huntDifficultyId.value : undefined),
      async (preview) => {
        encounter.value = preview;
        restoreActivity(preview.activity);
        await refreshProfile();
      },
    );
  }

  function declineEncounter(): Promise<EncounterPreview | null> {
    const current = encounter.value;
    if (current === null) return Promise.resolve(null);
    return mutate(
      () => ascensionClient.declineEncounter(current.id),
      async () => {
        encounter.value = null;
        await refreshProfile();
      },
    );
  }

  function startBattle(input: StartBattleInput): Promise<BattleView | null> {
    return mutate(
      () => ascensionClient.startBattle(input),
      async (view) => {
        encounter.value = null;
        setBattle(view);
        await refreshProfile();
      },
    );
  }

  function savePreset(ascendedId: string, slot: number, instanceIds: string[]): Promise<Preset | null> {
    return mutate(
      () => ascensionClient.savePreset(ascendedId, slot, instanceIds),
      () => undefined,
    );
  }

  function buyEmblems(tier: string, quantity: number, key?: string): Promise<EmblemPurchase | null> {
    return mutate(() => key ? ascensionClient.buyEmblems(tier, quantity, key) : ascensionClient.buyEmblems(tier, quantity), () => refreshProfile());
  }

  async function loadShop(): Promise<void> {
    const started = generation;
    try {
      const window = await ascensionClient.shop();
      if (started !== generation) return;
      shop.value = window;
      shopEndsAt.value = Date.now() / 1000 + window.seconds_left;
    } catch (err) {
      if (started === generation) report(err);
    }
  }

  async function buyOffer(offer: Pick<ShopOffer, "slot">, key?: string, originalRotation?: number): Promise<CopyPurchase | null> {
    const rotation = originalRotation ?? shop.value?.rotation;
    if (rotation === undefined) return null;
    const result = await mutate(
      () => key ? ascensionClient.buyOffer(rotation, offer.slot, key) : ascensionClient.buyOffer(rotation, offer.slot),
      () => refreshProfile(),
    );
    // A refresh, a sold-out offer or a purchase all change what the shop shows.
    await loadShop();
    return result;
  }

  function sellCopy(ascendedId: string, key?: string): Promise<Sale | null> {
    return mutate(() => key ? ascensionClient.sellCopy(ascendedId, key) : ascensionClient.sellCopy(ascendedId), () => refreshProfile());
  }

  function setSquad(ids: string[]): Promise<{ ascended_ids: string[]; size: number } | null> {
    if (busy.value) return Promise.resolve(null);
    return mutate(() => ascensionClient.putSquad(ids), () => refreshProfile());
  }

  function addToSquad(id: string) {
    return setSquad([...squadIds.value, id]);
  }

  function removeFromSquad(id: string) {
    return setSquad(squadIds.value.filter(member => member !== id));
  }

  function addStar(ascendedId: string): Promise<StarUp | null> {
    return mutate(() => ascensionClient.addStar(ascendedId), () => refreshProfile());
  }

  function learnNode(ascendedId: string, nodeId: string): Promise<LearnResult | null> {
    return mutate(() => ascensionClient.learnNode(ascendedId, nodeId), () => refreshProfile());
  }

  function saveLoadout(ascendedId: string, slots: Partial<Record<LoadoutSlot, string | null>>): Promise<LoadoutResult | null> {
    return mutate(() => ascensionClient.saveLoadout(ascendedId, slots), () => undefined);
  }

  function raiseTier(ascendedId: string): Promise<TierUp | null> {
    return mutate(() => ascensionClient.raiseTier(ascendedId), () => refreshProfile());
  }

  function setDefaultPreset(ascendedId: string, slot: number) {
    return mutate(() => ascensionClient.setDefaultPreset(ascendedId, slot), result => {
      if (profile.value) profile.value = { ...profile.value, ascendeds: profile.value.ascendeds.map(a =>
        a.ascended_id === ascendedId ? { ...a, default_preset_slot: result.slot } : a) };
    });
  }

  /** Deletes all progress. Resolves false (state kept) when another change is
   * running or the server refuses, e.g. 409 while a battle is active. */
  async function loadTrials(): Promise<void> {
    const started = generation;
    try { const result = await ascensionClient.trialProgress(); if (started === generation) trials.value = result; }
    catch (err) { if (started === generation) report(err); }
  }
  async function prepareTrial(typeId: string, stage: number): Promise<void> {
    const started = generation;
    trialTypeId.value = typeId; trialStage.value = stage; trialPreparation.value = null;
    try { const result = await ascensionClient.prepareTrial(typeId, stage); if (started === generation && typeId === trialTypeId.value && stage === trialStage.value) trialPreparation.value = result; }
    catch (err) { if (started === generation) report(err); }
  }
  let trialStartKey: string | null = null;
  let trialStartChoices = '';
  function startTrial(input: { ascended_id: string; preset_slot: number | null; mode: BattleMode }): Promise<BattleView | null> {
    if (busy.value) return Promise.resolve(null);
    const choices = JSON.stringify([trialTypeId.value, trialStage.value, input]);
    if (trialStartKey === null || choices !== trialStartChoices) { trialStartKey = newIdempotencyKey(); trialStartChoices = choices; }
    return mutate(() => ascensionClient.startTrial(trialTypeId.value, trialStage.value, input, trialStartKey!), view => { trialStartKey = null; encounter.value = null; setBattle(view); });
  }
  let departureKey: string | null = null;
  let departureChoices = '';
  function startExpedition(id: string, hours: number): Promise<ExpeditionStatus | null> {
    if (busy.value) return Promise.resolve(null);
    const choices = JSON.stringify([id, hours]);
    if (departureKey === null || departureChoices !== choices) { departureKey = newIdempotencyKey(); departureChoices = choices; }
    return mutate(() => ascensionClient.startExpedition(id, hours, departureKey!), async status => { observeExpedition(status); departureKey = null; expeditionReceipt.value = null; await refreshProfile(); });
  }
  async function refreshExpedition(): Promise<void> {
    const started = generation;
    const epoch = observationEpoch;
    const read = ++expeditionReadSerial;
    try { const status = await ascensionClient.expedition(); if (started === generation && epoch === observationEpoch && read === expeditionReadSerial) observeExpedition(status); }
    catch (err) { if (started === generation && epoch === observationEpoch && read === expeditionReadSerial) report(err); }
  }
  function claimExpedition(id: string): Promise<ExpeditionReceipt | null> {
    if (busy.value) return Promise.resolve(null);
    return mutate(() => ascensionClient.claimExpedition(id), async receipt => { expeditionReceipt.value = receipt; await refreshProfile(); });
  }
  function resetActivities(): void {
    observationEpoch += 1; trialStartKey = null;
    activitySelection.value = 'hub'; huntDifficultyId.value = 'outskirts'; trialTypeId.value = 'enchant'; trialStage.value = 1;
    trials.value = null; trialPreparation.value = null; expeditionStatus.value = null; expeditionReceipt.value = null; departureKey = null;
  }

  async function resetProgress(): Promise<boolean> {
    if (busy.value) return false;
    clearTimers();
    const result = await mutate(
      () => ascensionClient.resetProfile(),
      () => {
        profile.value = null;
        encounter.value = null;
        battle.value = null;
        resetActivities();
        needsStarter.value = true;
        reconnecting.value = false;
        promptRemaining.value = 0;
        promptTotal.value = 0;
        promptRevision = null;
      },
    );
    // A refused reset leaves the battle as it was: let its loop carry on.
    if (result === null && !unavailable.value) schedule();
    return result !== null;
  }

  watch(
    () => session.revision,
    () => {
      generation += 1;
      resetActivities();
      clearTimers();
      catalog.value = null;
      profile.value = null;
      shop.value = null;
      needsStarter.value = false;
      encounter.value = null;
      battle.value = null;
      loading.value = false;
      loaded.value = false;
      unavailable.value = false;
      reconnecting.value = false;
      busy.value = false;
      battleBusy.value = false;
      error.value = "";
      promptRemaining.value = 0;
      promptTotal.value = 0;
      promptRevision = null;
    },
  );

  return {
    activitySelection, huntDifficultyId, trialTypeId, trialStage, activities, trials, trialPreparation,
    expeditionStatus, expeditionObservedAt, expeditionReceipt, loadTrials, prepareTrial, startTrial, startExpedition, refreshExpedition, claimExpedition,
    catalog,
    profile,
    squadIds,
    squadMembers,
    setSquad,
    addToSquad,
    removeFromSquad,
    needsStarter,
    encounter,
    battle,
    loading,
    loaded,
    unavailable,
    reconnecting,
    busy,
    battleBusy,
    error,
    promptRemaining,
    promptTotal,
    promptOpen,
    attach,
    detach,
    retry,
    createProfile,
    rollEncounter,
    declineEncounter,
    startBattle,
    savePreset,
    buyEmblems,
    shop,
    shopEndsAt,
    loadShop,
    buyOffer,
    sellCopy,
    addStar,
    raiseTier,
    learnNode,
    saveLoadout,
    setDefaultPreset,
    resetProgress,
    act,
    answerEmblem,
    setMode,
    forfeit,
    refreshBattle,
    closeBattle,
  };
});
