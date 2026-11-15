import { attachmentsClient, type DictationResult } from "../../../api/files/AttachmentsClient";

export type LiveMode = "live" | "periodic" | "stop";

export interface DictationOptions {
  onStart?: () => void;
  onPartial?: (text: string) => void;
  onCancel?: () => void;
  partial?: (blob: Blob, signal?: AbortSignal) => Promise<DictationResult>;
}

/** Live transports never own the recording: closing them leaves the WebM fallback intact. */
export class LiveDictation {
  private socket?: WebSocket;
  private worklet?: AudioWorkletNode;
  private interval?: ReturnType<typeof setInterval>;
  private deadline?: ReturnType<typeof setTimeout>;
  private setupDeadline?: ReturnType<typeof setTimeout>;
  private requestDeadline?: ReturnType<typeof setTimeout>;
  private resolveReady?: () => void;
  private request?: AbortController;
  private active = true;
  private mode: "socket" | "http" | "upload" = "socket";
  private finishing = false;
  private resolveFinal?: (text: string | null) => void;
  private queued: ArrayBuffer[] = [];
  private sealed?: () => void;
  private options: DictationOptions;
  private status: (text: string) => void;
  private snapshot: () => Blob;
  private onMode: (mode: LiveMode) => void;

  constructor(
    options: DictationOptions,
    status: (text: string) => void,
    snapshot: () => Blob,
    onMode: (mode: LiveMode) => void = () => {},
  ) { this.options = options; this.status = status; this.snapshot = snapshot; this.onMode = onMode; }

  start(context?: AudioContext, source?: MediaStreamAudioSourceNode): Promise<void> {
    if (!context?.audioWorklet || !source || typeof AudioWorkletNode === "undefined") {
      this.fallback();
      return Promise.resolve();
    }
    const ready = new Promise<void>((resolve) => { this.resolveReady = resolve; });
    try {
      const url = new URL("/api/attachments/dictate/stream", location.href);
      url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
      this.socket = new WebSocket(url);
      this.deadline = setTimeout(() => this.fallback(), 5000);
      this.setupDeadline = setTimeout(() => this.fallback(), 5000);
      this.socket.onopen = () => { clearTimeout(this.deadline); this.onMode("live"); this.flush(); };
      this.socket.onclose = this.socket.onerror = () => this.fallback();
      this.socket.onmessage = (event) => {
        if (!this.active || this.mode !== "socket") return;
        try {
          const message = JSON.parse(String(event.data)) as { type?: string; text?: unknown };
          if (message.type === "error") { this.fallback(); return; }
          if (typeof message.text !== "string") return;
          if (message.type === "partial" && !this.finishing) this.options.onPartial?.(message.text);
          if (message.type === "final" && this.finishing) {
            this.resolveFinal?.(message.text);
            this.close();
          }
        } catch { this.fallback(); }
      };
      void context.audioWorklet.addModule(`${import.meta.env.BASE_URL}dictation-pcm.js`).then(() => {
        if (!this.active || this.mode !== "socket" || this.finishing) return;
        this.worklet = new AudioWorkletNode(context, "dictation-pcm");
        this.worklet.port.onmessage = (event: MessageEvent<ArrayBuffer | { type: string }>) => {
          if (!(event.data instanceof ArrayBuffer)) {
            if (event.data.type === "flushed") this.sealed?.();
            return;
          }
          if (!this.active || this.finishing || this.mode !== "socket") return;
          this.queued.push(event.data);
          // Five seconds maximum queued PCM, also bounds a stalled browser socket.
          if (this.queued.length > 50 || (this.socket?.bufferedAmount ?? 0) > 160000) this.fallback();
          else this.flush();
        };
        source.connect(this.worklet);
        // A silent output keeps processing alive without microphone playback.
        this.worklet.connect(context.destination);
        clearTimeout(this.setupDeadline);
        this.resolveReady?.();
        this.resolveReady = undefined;
      }).catch(() => this.fallback());
    } catch { this.fallback(); }
    return ready;
  }

  async seal(): Promise<void> {
    if (!this.worklet || this.mode !== "socket") return;
    await new Promise<void>((resolve) => {
      const timeout = setTimeout(() => { this.fallback(); resolve(); }, 500);
      this.sealed = () => { clearTimeout(timeout); this.sealed = undefined; resolve(); };
      this.worklet!.port.postMessage({ type: "flush" });
    });
  }

  private flush(): void {
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    for (const pcm of this.queued) this.socket.send(pcm);
    this.queued = [];
  }

  private releaseSocket(): void {
    clearTimeout(this.deadline);
    clearTimeout(this.setupDeadline);
    this.resolveReady?.();
    this.resolveReady = undefined;
    this.sealed?.();
    this.queued = [];
    if (this.worklet) {
      this.worklet.port.onmessage = null;
      this.worklet.port.close();
      this.worklet.disconnect();
      this.worklet = undefined;
    }
    if (this.socket) {
      this.socket.onopen = this.socket.onclose = this.socket.onerror = this.socket.onmessage = null;
      this.socket.close();
      this.socket = undefined;
    }
  }

  private fallback(): void {
    if (!this.active || this.mode !== "socket") return;
    this.mode = "http";
    this.releaseSocket();
    if (this.finishing) { this.resolveFinal?.(null); return; }
    this.onMode("periodic");
    this.status("Live text uses periodic updates.");
    this.interval = setInterval(() => { void this.tick(); }, 2500);
  }

  private async tick(): Promise<void> {
    if (!this.active || this.finishing || this.request) return;
    const blob = this.snapshot();
    if (!blob.size) return;
    const request = new AbortController();
    this.request = request;
    // A hung partial must not permanently stall the fallback chain.
    this.requestDeadline = setTimeout(() => request.abort(), 120000);
    try {
      const result = await (this.options.partial ?? attachmentsClient.dictatePartial)(blob, request.signal);
      if (this.active && !this.finishing && this.mode === "http") this.options.onPartial?.(result.text);
    } catch {
      if (!this.active || this.finishing) return;
      this.mode = "upload";
      clearInterval(this.interval);
      this.onMode("stop");
      this.status("Live text is unavailable. Transcribes on stop.");
    } finally {
      clearTimeout(this.requestDeadline);
      this.request = undefined;
    }
  }

  finish(): Promise<string | null> {
    this.finishing = true;
    clearInterval(this.interval);
    clearTimeout(this.requestDeadline);
    this.request?.abort();
    if (this.mode !== "socket" || this.socket?.readyState !== WebSocket.OPEN || !this.worklet) {
      this.close();
      return Promise.resolve(null);
    }
    return new Promise((resolve) => {
      this.resolveFinal = resolve;
      this.deadline = setTimeout(() => { resolve(null); this.close(); }, 120000);
      try {
        this.flush();
        this.socket!.send(JSON.stringify({ type: "stop" }));
      } catch { this.fallback(); }
    });
  }

  close(): void {
    this.active = false;
    clearInterval(this.interval);
    clearTimeout(this.requestDeadline);
    this.request?.abort();
    this.resolveFinal?.(null);
    this.resolveFinal = undefined;
    this.releaseSocket();
  }
}
