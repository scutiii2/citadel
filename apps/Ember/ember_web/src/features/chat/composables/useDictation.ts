import { computed, onScopeDispose, ref } from "vue";
import { attachmentsClient, type DictationResult } from "../../../api/files/AttachmentsClient";
import { LiveDictation, type DictationOptions, type LiveMode } from "./liveDictation";

type DictationState = "idle" | "recording" | "transcribing" | "error";

/** Own the microphone and request together so cancelled work cannot edit another draft. */
export function useDictation(
  insert: (text: string) => void,
  transcribe: (blob: Blob, signal?: AbortSignal) => Promise<DictationResult> = attachmentsClient.dictate,
  options: DictationOptions = {},
) {
  const state = ref<DictationState>("idle");
  const error = ref("");
  const requesting = ref(false);
  const liveStatus = ref("");
  const liveMode = ref<LiveMode | "">("");
  let live: LiveDictation | undefined;
  let ownsDraft = false;
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
    live?.close();
    live = undefined;
    if (ownsDraft) options.onCancel?.();
    ownsDraft = false;
    liveStatus.value = "";
    liveMode.value = "";
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

  async function stop(): Promise<void> {
    if (recorder?.state === "recording") {
      clearTimeout(timer);
      state.value = "transcribing";
      const run = generation;
      await live?.seal();
      if (run !== generation) return;
      recorder?.stop();
      release();
    }
  }

  async function toggle(): Promise<void> {
    if (state.value === "recording") { await stop(); return; }
    if (requesting.value || state.value === "transcribing") return;
    if (!supported.value) { fail("This browser cannot record WebM audio."); return; }
    const run = ++generation;
    ownsDraft = true;
    options.onStart?.();
    liveStatus.value = "";
    liveMode.value = "";
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
        const blob = new Blob(chunks, { type: "audio/webm" });
        const signal = request.signal;
        const transport = live;
        void (async () => {
          const text = await transport?.finish();
          if (run !== generation) return;
          const result = text == null ? await transcribe(blob, signal) : { text };
          if (run !== generation) return;
          insert(result.text);
          ownsDraft = false;
          live = undefined;
          liveStatus.value = "";
    liveMode.value = "";
          state.value = "idle";
        })().catch((cause: unknown) => {
          if (run === generation) fail(cause instanceof Error ? cause.message : "Scribe could not transcribe the recording.");
        });
      };
      startMeter(granted);
      live = new LiveDictation(options, (text) => { liveStatus.value = text; }, () => {
        if (recorder?.state === "recording") recorder.requestData();
        return new Blob(chunks, { type: "audio/webm" });
      }, (mode) => { liveMode.value = mode; });
      // Do not advertise recording until PCM capture is connected. Otherwise a
      // successful stream would miss words spoken while the worklet downloads.
      await live.start(audioContext, source);
      if (run !== generation) return;
      startedAt = performance.now();
      elapsedMs.value = 0;
      recorder.start(250);
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
  return { state, error, supported, requesting, liveStatus, liveMode, levels, elapsedMs, toggle, cancel };
}
