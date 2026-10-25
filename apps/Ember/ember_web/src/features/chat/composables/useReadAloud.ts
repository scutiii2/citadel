import { onScopeDispose, ref, type Ref } from "vue";
import { bardClient, type SpeechClip } from "../../../api/files/BardClient";

let stopActive: (() => void) | undefined;
type Prepared = { clip: SpeechClip; error?: never } | { error: unknown; clip?: never };

/** Play one clip to completion, releasing listeners on stop and every failure path. */
function playClip(audio: HTMLAudioElement, clip: SpeechClip, signal: AbortSignal, playing: () => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      audio.removeEventListener("ended", ended);
      audio.removeEventListener("error", failed);
      signal.removeEventListener("abort", aborted);
    };
    const ended = () => { cleanup(); resolve(); };
    const failed = () => { cleanup(); reject(new Error("Audio unavailable. Try reading aloud again.")); };
    const aborted = () => { cleanup(); reject(new DOMException("Stopped", "AbortError")); };
    if (signal.aborted) { aborted(); return; }
    audio.addEventListener("ended", ended);
    audio.addEventListener("error", failed);
    signal.addEventListener("abort", aborted, { once: true });
    audio.src = `/api/bard/audio/${encodeURIComponent(clip.file_id)}`;
    void audio.play().then(() => { if (!signal.aborted) playing(); }).catch((cause: unknown) => {
      cleanup(); reject(cause);
    });
  });
}

/** Synthesize at most one batch ahead; a cancelled run never resumes playback. */
export function useReadAloud(
  audio: Ref<HTMLAudioElement | null>,
  synthesize: (text: string, voice: string, signal?: AbortSignal) => Promise<SpeechClip> = bardClient.speak,
) {
  const state = ref<"idle" | "busy" | "playing" | "error">("idle");
  const error = ref("");
  let controller: AbortController | undefined;

  function clearAudio(): void {
    const el = audio.value;
    if (el?.hasAttribute("src")) {
      el.pause();
      el.removeAttribute("src");
      el.load();
    }
  }

  function stop(): void {
    controller?.abort();
    controller = undefined;
    clearAudio();
    state.value = "idle";
    error.value = "";
    if (stopActive === stop) stopActive = undefined;
  }

  async function start(batches: string[], voice: string): Promise<void> {
    stopActive?.();
    stop();
    if (!batches.length || !audio.value) return;
    stopActive = stop;
    const run = controller = new AbortController();
    state.value = "busy";
    // Catch immediately: prefetch may fail while the current clip is still playing.
    const prepare = (text: string): Promise<Prepared> => synthesize(text, voice, run.signal)
      .then((clip) => ({ clip })).catch((cause: unknown) => ({ error: cause }));
    try {
      let pending = prepare(batches[0]!);
      for (let index = 0; index < batches.length; index++) {
        const result = await pending;
        if (run.signal.aborted) return;
        if (!result.clip) throw result.error;
        const next = batches[index + 1];
        if (next !== undefined) pending = prepare(next);
        await playClip(audio.value, result.clip, run.signal, () => { state.value = "playing"; });
        if (run.signal.aborted) return;
        state.value = "busy";
      }
      state.value = "idle";
    } catch (cause) {
      if (!run.signal.aborted) {
        run.abort();
        state.value = "error";
        error.value = cause instanceof Error ? cause.message : "Bard could not read this message aloud.";
      }
    } finally {
      if (controller === run) {
        clearAudio();
        controller = undefined;
        if (stopActive === stop) stopActive = undefined;
      }
    }
  }

  onScopeDispose(stop);
  return { state, error, start, stop };
}
