import { computed, onScopeDispose, ref } from "vue";
import { attachmentsClient, type DictationResult } from "../../../api/files/AttachmentsClient";

type DictationState = "idle" | "recording" | "transcribing" | "error";

/** Own the microphone and request together so cancelled work cannot edit another draft. */
export function useDictation(
  insert: (text: string) => void,
  transcribe: (blob: Blob, signal?: AbortSignal) => Promise<DictationResult> = attachmentsClient.dictate,
) {
  const state = ref<DictationState>("idle");
  const error = ref("");
  const requesting = ref(false);
  const supported = computed(() => typeof MediaRecorder !== "undefined"
    && !!navigator.mediaDevices?.getUserMedia && MediaRecorder.isTypeSupported("audio/webm"));
  let recorder: MediaRecorder | undefined;
  let stream: MediaStream | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let request: AbortController | undefined;
  let generation = 0;

  function release(): void {
    clearTimeout(timer);
    stream?.getTracks().forEach((track) => track.stop());
    stream = undefined;
  }

  function cancel(): void {
    generation++;
    request?.abort();
    if (recorder) {
      recorder.onstop = null;
      recorder.ondataavailable = null;
      recorder.onerror = null;
      if (recorder.state !== "inactive") recorder.stop();
      recorder = undefined;
    }
    release();
    requesting.value = false;
    state.value = "idle";
    error.value = "";
  }

  function fail(message: string): void {
    cancel();
    state.value = "error";
    error.value = message;
  }

  function stop(): void {
    if (recorder?.state === "recording") {
      state.value = "transcribing";
      recorder.stop();
      release();
    }
  }

  async function toggle(): Promise<void> {
    if (state.value === "recording") { stop(); return; }
    if (requesting.value || state.value === "transcribing") return;
    if (!supported.value) { fail("This browser cannot record WebM audio."); return; }
    const run = ++generation;
    requesting.value = true;
    error.value = "";
    try {
      const granted = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (run !== generation) { granted.getTracks().forEach((track) => track.stop()); return; }
      stream = granted;
      const chunks: Blob[] = [];
      recorder = new MediaRecorder(granted, { mimeType: "audio/webm" });
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onerror = () => fail("Microphone recording failed. Try again.");
      recorder.onstop = () => {
        release();
        if (run !== generation) return;
        state.value = "transcribing";
        request = new AbortController();
        void transcribe(new Blob(chunks, { type: "audio/webm" }), request.signal).then((result) => {
          if (run !== generation) return;
          insert(result.text);
          state.value = "idle";
        }).catch((cause: unknown) => {
          if (run === generation) fail(cause instanceof Error ? cause.message : "Scribe could not transcribe the recording.");
        });
      };
      recorder.start();
      state.value = "recording";
      timer = setTimeout(stop, 150_000);
    } catch (cause) {
      if (run !== generation) return;
      fail(cause instanceof DOMException && cause.name === "NotAllowedError"
        ? "Microphone permission was denied. Allow microphone access and try again."
        : "Could not start the microphone. Check that it is connected and try again.");
    } finally {
      if (run === generation) requesting.value = false;
    }
  }

  onScopeDispose(cancel);
  return { state, error, supported, requesting, toggle, cancel };
}
