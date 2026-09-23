/*
 * The live microphone path, browser side.
 *
 * getUserMedia -> AudioWorklet -> 20 ms Float32 chunks -> WebSocket /live/audio.
 * The server's pipeline does everything else; this file knows nothing about
 * triggers or verdicts.
 *
 * Four details are load-bearing and each has a failure it prevents:
 *
 * 1. THE GRAPH NEEDS A SINK. An AudioWorkletNode with no output connected is
 *    never pulled and process() never runs -- a silent, working-looking screen.
 *    So the node ends in a zero-gain GainNode wired to the destination.
 * 2. THE SAMPLE RATE IS WHATEVER THE BROWSER GAVE US. We ask for 16 kHz and
 *    most browsers honour it, but we read ctx.sampleRate and send it, so the
 *    server resamples if the request was ignored. Never resample twice.
 * 3. SILENCE IS NOT SUCCESS. macOS denies microphone access by returning
 *    DIGITAL SILENCE rather than an error, so a level watchdog reports "no
 *    audio" after `noAudioWarnMs` of near-zero input. The screen must not look
 *    healthy while nothing is arriving.
 * 4. THE DEVICE IS RELEASED ON STOP. Closing the AudioContext turns off the
 *    browser's recording indicator. A demo that leaves the mic light on after
 *    "stop" looks like spyware.
 */
const SentinelLive = (() => {
  let ctx = null;
  let stream = null;
  let sourceNode = null;
  let worklet = null;
  let sink = null;

  let ws = null;
  let running = false;
  let sendAudio = false;
  let sampleRate = 16000;

  let onLevel = null;
  let onState = null;
  let onError = null;

  let silentMs = 0;
  let warnedSilent = false;
  let noAudioWarnMs = 700;
  let closingSocket = false;

  let recording = false;
  let recordChunks = [];
  let recordTarget = 0;
  let recordTimer = null;
  let recordResolve = null;

  // ---------------------------------------------------------------- helpers
  function rms(buf) {
    let sum = 0;
    for (let i = 0; i < buf.length; i += 1) sum += buf[i] * buf[i];
    return Math.sqrt(sum / buf.length);
  }

  function describeError(err) {
    const name = err && err.name;
    if (name === 'NotAllowedError') {
      return 'microphone permission denied — allow it for this page, then try again';
    }
    if (name === 'NotFoundError' || name === 'OverconstrainedError') {
      return 'no microphone found on this machine';
    }
    if (name === 'NotReadableError') {
      return 'the microphone is in use by another application';
    }
    return (err && err.message) || String(err);
  }

  async function ensureGraph() {
    await disposing;      // a previous teardown must land before we build again
    if (ctx) return;

    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,     // stops the speaker output feeding back
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    let context;
    try {
      context = new AudioContext({ sampleRate: 16000, latencyHint: 'interactive' });
    } catch (err) {
      context = new AudioContext();   // older browser: take the device rate
    }
    ctx = context;
    if (ctx.state === 'suspended') await ctx.resume();

    await ctx.audioWorklet.addModule('/static/pcm-worklet.js');

    sourceNode = ctx.createMediaStreamSource(stream);
    worklet = new AudioWorkletNode(ctx, 'sentinel-pcm', {
      processorOptions: { chunkMs: 20 },
    });
    sink = ctx.createGain();
    sink.gain.value = 0;                    // pull the graph, make no sound
    sourceNode.connect(worklet);
    worklet.connect(sink);
    sink.connect(ctx.destination);
    worklet.port.onmessage = (event) => onChunk(event.data);

    sampleRate = ctx.sampleRate;

    stream.getAudioTracks().forEach((track) => {
      track.onended = () => {
        if (running) fail('microphone disconnected');
      };
    });
  }

  function onChunk(buf) {
    const level = rms(buf);
    if (onLevel) onLevel(level);

    if (sendAudio) {
      silentMs = level < 0.0005 ? silentMs + 20 : 0;
      if (!warnedSilent && silentMs >= noAudioWarnMs) {
        warnedSilent = true;
        if (onState) onState({ silent: true });
      } else if (warnedSilent && silentMs === 0) {
        warnedSilent = false;
        if (onState) onState({ silent: false });
      }
    }

    if (sendAudio && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(buf);                         // binary Float32, 20 ms
    }

    if (recording) {
      recordChunks.push(buf.slice(0));
      if (recordChunks.length >= recordTarget) finishRecording();
    }
  }

  function openSocket() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return new Promise((resolve, reject) => {
      ws = new WebSocket(`${proto}//${location.host}/live/audio`);
      ws.binaryType = 'arraybuffer';
      ws.onopen = () => resolve();
      ws.onerror = () => reject(new Error('the live audio socket failed to open'));
      ws.onmessage = (msg) => {
        let event = null;
        try { event = JSON.parse(msg.data); } catch (err) { return; }
        if (event.type === 'live_ready') {
          if (onState) onState({ ready: true, meta: event.meta, sampleRate: event.sample_rate });
        } else if (event.type === 'live_error' && onError) {
          onError(event.message);
        }
      };
      ws.onclose = () => {
        if (running && !closingSocket) fail('the live audio socket closed');
      };
    });
  }

  async function fail(message) {
    const handler = onError;
    await teardown();
    if (handler) handler(message);
  }

  // ------------------------------------------------------------- public API
  async function start(opts) {
    if (running) return false;
    const options = opts || {};
    onLevel = options.onLevel || null;
    onState = options.onState || null;
    onError = options.onError || null;
    noAudioWarnMs = options.noAudioWarnMs || 700;

    try {
      await ensureGraph();
      await openSocket();
      ws.send(JSON.stringify({
        type: 'start',
        mode: options.mode || 'triggered',
        speaker: options.speaker || null,
        sample_rate: sampleRate,
      }));
      sendAudio = true;
      running = true;
      closingSocket = false;
      silentMs = 0;
      warnedSilent = false;
      if (onState) onState({ running: true, sampleRate });
      return true;
    } catch (err) {
      const message = describeError(err);
      await teardown();
      if (onError) onError(message);
      return false;
    }
  }

  function stop(reason) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      closingSocket = true;
      try { ws.send(JSON.stringify({ type: 'stop' })); } catch (err) { /* closing */ }
    }
    sendAudio = false;
    running = false;
    const handler = onState;
    teardown();
    if (handler) handler({ running: false, reason: reason || null });
  }

  // Teardown is async (closing an AudioContext takes a tick), and a user can
  // hit stop then start before it lands. Every teardown chains onto the last
  // one and every start waits for the chain, so a new capture can never share
  // a context that is being closed underneath it.
  let disposing = Promise.resolve();

  async function doTeardown() {
    running = false;
    sendAudio = false;
    if (recording) cancelRecording();   // a pending record() must not hang forever
    if (recordTimer) { clearInterval(recordTimer); recordTimer = null; }
    if (ws) {
      closingSocket = true;
      try { ws.close(); } catch (err) { /* already closed */ }
      ws = null;
    }
    if (worklet) { worklet.port.onmessage = null; worklet.disconnect(); worklet = null; }
    if (sourceNode) { sourceNode.disconnect(); sourceNode = null; }
    if (sink) { sink.disconnect(); sink = null; }
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
    if (ctx) { try { await ctx.close(); } catch (err) { /* already closed */ } ctx = null; }
    sampleRate = 16000;
  }

  function teardown() {
    disposing = disposing.then(doTeardown, doTeardown);
    return disposing;
  }

  /**
   * Record `seconds` of microphone audio. Resolves with {pcm, sampleRate}.
   * Used by the voices panel; the microphone is released afterwards.
   */
  async function record(seconds, opts) {
    if (running) throw new Error('stop the live run before recording a voice');
    const options = opts || {};
    await ensureGraph();

    recordChunks = [];
    recordTarget = Math.max(1, Math.round((seconds * 1000) / 20));
    recording = true;

    const startedAt = performance.now();
    if (options.onTick) options.onTick(0, seconds);
    recordTimer = setInterval(() => {
      if (!recording) return;
      const elapsed = (performance.now() - startedAt) / 1000;
      if (options.onTick) options.onTick(Math.min(seconds, elapsed), seconds);
    }, 100);

    return new Promise((resolve) => { recordResolve = resolve; });
  }

  function finishRecording() {
    recording = false;
    if (recordTimer) { clearInterval(recordTimer); recordTimer = null; }
    const chunks = recordChunks;
    recordChunks = [];
    let total = 0;
    for (const chunk of chunks) total += chunk.length;
    const pcm = new Float32Array(total);
    let offset = 0;
    for (const chunk of chunks) { pcm.set(chunk, offset); offset += chunk.length; }
    if (recordResolve) {
      const resolve = recordResolve;
      recordResolve = null;
      resolve({ pcm, sampleRate });
    }
  }

  function cancelRecording() {
    recording = false;
    recordChunks = [];
    if (recordTimer) { clearInterval(recordTimer); recordTimer = null; }
    if (recordResolve) {
      const resolve = recordResolve;
      recordResolve = null;
      resolve(null);
    }
  }

  /** Float32 -> little-endian int16 -> base64, for POST /voices. */
  function toInt16Base64(pcm) {
    const view = new DataView(new ArrayBuffer(pcm.length * 2));
    for (let i = 0; i < pcm.length; i += 1) {
      const clamped = Math.max(-1, Math.min(1, pcm[i]));
      view.setInt16(i * 2, Math.round(clamped * 32767), true);
    }
    let binary = '';
    const bytes = new Uint8Array(view.buffer);
    const block = 0x8000;
    for (let i = 0; i < bytes.length; i += block) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + block));
    }
    return btoa(binary);
  }

  return {
    start,
    stop,
    record,
    cancelRecording,
    release: teardown,
    toInt16Base64,
    get running() { return running; },
    get sampleRate() { return sampleRate; },
    isRecording: () => recording,
  };
})();
