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
  const levels = ref<number[]>(Array(24).fill(0));
  const elapsedMs = ref(0);
  const supported = computed(() => typeof MediaRecorder !== "undefined"
    && !!navigator.mediaDevices?.getUserMedia && MediaRecorder.isTypeSupported("audio/webm"));
  let recorder: MediaRecorder | undefined;
  let stream: MediaStream | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let request: AbortController | undefined;
  let generation = 0;
  let audioContext: AudioContext | undefined;
  let source: MediaStreamAudioSourceNode | undefined;
  let analyser: AnalyserNode | undefined;
  let frame: number | undefined;
  let startedAt: number | undefined;

  function releaseMeter(): void {
    if (frame !== undefined) cancelAnimationFrame(frame);
    frame = undefined;
    source?.disconnect();
    analyser?.disconnect();
    source = undefined;
    analyser = undefined;
    if (audioContext) void audioContext.close().catch(() => {});
    audioContext = undefined;
  }

  function startMeter(granted: MediaStream): void {
    levels.value = Array(24).fill(0);
    elapsedMs.value = 0;
    startedAt = performance.now();
    // Metering is optional: a browser audio-graph failure must not break dictation.
    try {
      audioContext = new AudioContext();
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source = audioContext.createMediaStreamSource(granted);
      source.connect(analyser); // No destination: never play the microphone back.
      if (audioContext.state === "suspended") void audioContext.resume().catch(() => {});
    } catch { releaseMeter(); }
    const samples = new Uint8Array(256);
    let lastSample = startedAt;
    const sample = () => {
      const now = performance.now();
      elapsedMs.value = Math.min(150_000, now - startedAt!);
      if (now - lastSample >= 80) {
        let sum = 0;
        if (analyser) {
          analyser.getByteTimeDomainData(samples);
          for (const value of samples) sum += ((value - 128) / 128) ** 2;
        }
        // Compress the RMS range so quiet speech is readable; silence stays flat.
        const rms = Math.sqrt(sum / samples.length);
        const level = Math.min(1, Math.sqrt(rms) * 2);
        levels.value = [...levels.value.slice(1), level];
        lastSample = now;
      }
      frame = requestAnimationFrame(sample);
    };
    frame = requestAnimationFrame(sample);
  }

  function release(): void {
    clearTimeout(timer);
    if (startedAt !== undefined) elapsedMs.value = Math.min(150_000, performance.now() - startedAt);
    startedAt = undefined;
    releaseMeter();
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
    elapsedMs.value = 0;
    levels.value = Array(24).fill(0);
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
      startMeter(granted);
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
  return { state, error, supported, requesting, levels, elapsedMs, toggle, cancel };
}
