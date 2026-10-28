/* AudioWorklet global: sampleRate is the actual device/context rate. */
class DictationPcm extends AudioWorkletProcessor {
  constructor() {
    super();
    this.phase = 0;
    this.sum = 0;
    this.weight = 0;
    this.samples = [];
    this.sealed = false;
    this.port.onmessage = (event) => {
      if (event.data?.type !== "flush") return;
      this.emit();
      this.sealed = true;
      this.port.postMessage({ type: "flushed" });
    };
  }

  emit() {
    if (!this.samples.length) return;
    const pcm = new ArrayBuffer(this.samples.length * 2);
    const view = new DataView(pcm);
    this.samples.forEach((value, index) => view.setInt16(index * 2,
      Math.round(value * (value < 0 ? 32768 : 32767)), true));
    this.port.postMessage(pcm, [pcm]);
    this.samples = [];
  }

  process(inputs) {
    const channels = inputs[0];
    if (this.sealed || !channels?.length) return true;
    const ratio = sampleRate / 16000;
    for (let i = 0; i < channels[0].length; i++) {
      let sample = 0;
      for (const channel of channels) sample += channel[i] / channels.length;
      // Area resampling retains phase between render quanta (including 44.1 kHz).
      let remaining = 1;
      while (remaining > 1e-10) {
        const take = Math.min(remaining, ratio - this.phase);
        this.sum += sample * take;
        this.weight += take;
        this.phase += take;
        remaining -= take;
        if (this.phase >= ratio - 1e-10) {
          this.samples.push(Math.max(-1, Math.min(1, this.sum / this.weight)));
          this.phase = this.sum = this.weight = 0;
          if (this.samples.length === 1600) {
            this.emit();
          }
        }
      }
    }
    return true;
  }
}
registerProcessor("dictation-pcm", DictationPcm);
