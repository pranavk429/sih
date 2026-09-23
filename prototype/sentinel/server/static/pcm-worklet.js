/*
 * The audio thread. Runs off the main thread, so a busy tab cannot stretch a
 * chunk, and it is unaffected by the timer throttling that Chrome applies to
 * background tabs.
 *
 * It emits fixed-size chunks (20 ms by default) with sample counting done here,
 * never via setTimeout. Partial input blocks are carried over, so chunk
 * boundaries are exact and there are no clicks at the joins.
 *
 * `sampleRate` is a global in AudioWorkletGlobalScope; the chunk length is
 * computed from it so a 44.1 kHz device and a 48 kHz device both produce 20 ms.
 */
class SentinelPcm extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    const chunkMs = opts.chunkMs || 20;
    this.frameSamples = Math.max(1, Math.round((chunkMs / 1000) * sampleRate));
    this.buf = new Float32Array(this.frameSamples);
    this.n = 0;
  }

  process(inputs) {
    const input = inputs[0];
    const ch = input && input[0];
    if (!ch || ch.length === 0) return true;   // mic muted or not yet connected

    let i = 0;
    while (i < ch.length) {
      const take = Math.min(ch.length - i, this.frameSamples - this.n);
      this.buf.set(ch.subarray(i, i + take), this.n);
      this.n += take;
      i += take;
      if (this.n === this.frameSamples) {
        const out = this.buf.slice();
        this.port.postMessage(out, [out.buffer]);   // transfer: zero-copy
        this.n = 0;
      }
    }
    return true;   // keep the processor alive
  }
}

registerProcessor('sentinel-pcm', SentinelPcm);
