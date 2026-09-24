/*
 * Sentinel UI. One file, no framework, no build step.
 *
 * The shape is: a WebSocket pushes events, `apply()` folds each one into a
 * plain `state` object, and a requestAnimationFrame loop renders whatever
 * state currently says. Nothing here recomputes anything the backend already
 * decided -- every number on screen arrives in an event and is displayed as
 * received. That is deliberate: if the UI derived risks or verdicts of its own,
 * the screen and the evidence log could disagree, and the log is the thing we
 * claim is authoritative.
 *
 * The exceptions are formatting, counting things the UI was already sent (how
 * many windows, how many segments), and the timeline, which draws the points
 * it was given. No threshold is ever re-applied here.
 */
'use strict';

// ---------------------------------------------------------------- state
const state = {
  connected: false,
  hello: null,              // calibration provenance, band, config numbers
  meta: null,               // which call is running
  runStart: null,
  utterances: [],
  triggers: [],
  regions: [],              // gated spans, computed server-side by the gating policy
  spk: [],                  // {t, v} voice-match risk per window
  cm: [],                   // {t, v} artifact risk per window
  silent: [],               // windows the VAD refused to score
  verdict: null,
  final: null,
  stats: null,
  lagMs: 0,
  alerts: 0,
  falseAlarms: 0,
  mode: 'triggered',
  groundTruth: null,
  durationS: 0,
  clockMs: 0,
  running: false,
  error: null,
  // --- the live path (PLAN-LIVE.md F1/F2/F3) ---
  source: 'file',           // 'file' | 'live'
  live: false,              // the run on screen came from the microphone
  liveCfg: null,            // hello.live
  lookupCfg: null,          // hello.lookup (the threshold on screen)
  voices: [],               // enrolled voices, from /voices
  speaker: '',              // voice the live run is checked against
  lookups: [],              // voice_lookup events
  liveUi: { recording: false, level: 0, silent: false, note: 'idle' },
  assess: null,             // last try-a-line result
};

// Finished runs, keyed by call AND mode, so the two modes can be put beside
// each other. Only what this browser session actually measured -- nothing is
// restored from a previous page load, so every number on screen is one the
// person watching saw happen. Comparing across two different calls would not
// be a comparison of anything, hence the call in the key.
const runsSeen = {};

let dirty = true;
const touch = () => { dirty = true; };

// ---------------------------------------------------------------- helpers
const $ = (id) => document.getElementById(id);
const fmt = (v, n = 3) => (v === null || v === undefined) ? '—' : Number(v).toFixed(n);
const secs = (ms) => (ms / 1000).toFixed(1) + 's';
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

function text(el, value) { if (el.textContent !== value) el.textContent = value; }
function show(el, on) { if (el.hidden === on) el.hidden = !on; }

// ---------------------------------------------------------------- events
function resetRun(meta) {
  state.meta = meta || null;
  state.runStart = null;
  state.utterances = [];
  state.triggers = [];
  state.regions = [];
  state.spk = [];
  state.cm = [];
  state.silent = [];
  state.verdict = null;
  state.final = null;
  state.stats = null;
  state.lagMs = 0;
  state.alerts = 0;
  state.falseAlarms = 0;
  state.clockMs = 0;
  state.error = null;
  state.lookups = [];
  state.gallery = null;
  state.running = true;
  if (meta) {
    state.mode = meta.mode;
    state.groundTruth = meta.ground_truth;
    state.durationS = meta.duration_s || 0;
    state.live = Boolean(meta.live);
    // The source toggle follows the run: a live run must not leave the UI
    // showing the recorded-call controls, and vice versa.
    state.source = state.live ? 'live' : 'file';
    if (state.live && meta.speaker_id) state.speaker = meta.speaker_id;
  }
  touch();
}

function apply(event) {
  switch (event.type) {
    case 'hello':
      state.hello = event;
      state.liveCfg = event.live || null;
      state.lookupCfg = event.lookup || null;
      state.voices = event.voices || [];
      if (!state.speaker && state.voices.length) state.speaker = state.voices[0].speaker_id;
      if (!modeManuallySet && event.default_mode) {
        selectedMode = event.default_mode;
        state.mode = event.default_mode;
      }
      break;

    case 'run_meta':
      resetRun(event);
      break;

    case 'run_start':
      state.runStart = event;
      state.mode = event.mode;
      state.groundTruth = event.ground_truth;
      state.live = Boolean(event.live);
      state.gallery = event.gallery || null;
      if (event.duration_s) state.durationS = event.duration_s;
      break;

    case 'voice_lookup':
      // Open-set identification against the enrolment gallery. Kept separate
      // from the verdict because it is a separate signal; the UI shows it as
      // one, threshold included.
      state.lookups.push(event);
      if (state.lookups.length > 600) state.lookups.shift();
      break;

    case 'utterance':
      state.utterances.push(event);
      state.clockMs = Math.max(state.clockMs, event.t_end_ms);
      break;

    case 'trigger':
      state.triggers.push(event);
      if (event.active_regions) state.regions = event.active_regions;
      break;

    case 'risk_score': {
      const point = { t: event.t_end_ms, v: event.value, seq: event.seq };
      if (event.status !== 'OK') {
        state.silent.push(point);
      } else if (event.kind === 'cm') {
        state.cm.push(point);
      } else {
        state.spk.push(point);
      }
      state.clockMs = Math.max(state.clockMs, event.t_end_ms);
      break;
    }

    case 'verdict':
      state.verdict = event;
      state.lagMs = event.pipeline_lag_ms || 0;
      state.alerts = event.alerts || 0;
      state.falseAlarms = event.false_alarms || 0;
      state.mode = event.mode || state.mode;
      state.clockMs = Math.max(state.clockMs, event.t_ms);
      break;

    case 'final':
      state.final = event;
      state.verdict = event;
      state.stats = event.stats;
      if (event.stats) {
        state.alerts = event.stats.alerts;
        state.falseAlarms = event.stats.false_alarms;
        // Recorded on `final` only: a run that crashed or was stopped never
        // becomes half of a comparison.
        if (state.meta && state.meta.demo) {
          runsSeen[`${state.meta.demo}|${state.meta.mode}`] = {
            alerts: event.stats.alerts,
            falseAlarms: event.stats.false_alarms,
          };
        }
      }
      break;

    case 'run_error':
      state.error = event.message;
      break;

    case 'run_end':
      state.running = false;
      if (event.error) state.error = event.error;
      break;
  }
  touch();
}

// ---------------------------------------------------------------- socket
let socket = null;

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  socket = new WebSocket(`${proto}//${location.host}/stream`);

  socket.onopen = () => { state.connected = true; touch(); };
  socket.onmessage = (msg) => apply(JSON.parse(msg.data));
  socket.onclose = () => {
    state.connected = false;
    touch();
    // A dropped socket mid-demo must heal itself. On reconnect the server
    // replays the run from the top, so nothing is lost.
    setTimeout(connect, 1000);
  };
  socket.onerror = () => socket.close();
}

// ---------------------------------------------------------------- counts
// Counting what we were already sent. Live during a run, authoritative once
// the final event lands and brings the server's own tally with it.
function counts() {
  const s = state.stats;
  const v = state.verdict;
  return {
    scored: s ? s.windows_scored : state.spk.length,
    deep: s ? s.windows_deep : state.cm.length,
    flagged: (v && v.segments) ? v.segments.length : 0,
    triggers: s ? s.triggers : state.triggers.length,
  };
}

// ---------------------------------------------------------------- render
function renderHeader() {
  const cal = state.hello && state.hello.calibration;
  if (cal) {
    text($('prov-id'), cal.calibration_id);
    text($('prov-dataset'), cal.dataset);
    text($('prov-eer'), `${(cal.eer * 100).toFixed(2)}% on ${cal.n_test_trials} trials`);
  }

  const conn = $('chip-conn');
  conn.dataset.state = state.connected ? 'on' : 'off';
  text(conn, state.connected ? 'connected' : 'reconnecting…');

  // SPEC §12: if we fall behind real time, say so. Do not hide it.
  const warn = (state.hello && state.hello.lag_warn_ms) || 500;
  const lag = $('chip-lag');
  if (state.lagMs > warn) {
    lag.hidden = false;
    lag.dataset.state = 'warn';
    text(lag, `behind real time by ${state.lagMs} ms`);
  } else {
    lag.hidden = true;
  }

  const clock = $('chip-clock');
  if (state.meta) {
    if (state.live) {
      // A live run has no known duration; the clock counts up and says so.
      text(clock, `${secs(state.clockMs)} · live${state.running ? '' : ' · ended'}`);
    } else {
      const tag = state.meta.fast ? ' · fast replay' : '';
      text(clock, `${secs(state.clockMs)} / ${state.durationS.toFixed(1)}s${tag}`);
    }
  } else {
    text(clock, 'no call loaded');
  }

  // Who the call is being checked against. The enrolment is the whole premise,
  // so a call running against a speaker with no reference has to say so.
  const m = state.meta;
  if (m && m.live) {
    const voice = state.voices.find((v) => v.speaker_id === m.speaker_id);
    text($('who-name'), 'Live microphone');
    text($('who-sub'), voice
      ? `checking the voice against ${voice.display_name}`
      : (state.voices.length
        ? 'no reference voice selected — lookup only'
        : 'no voices enrolled — nothing to compare the voice against'));
  } else if (m && m.speaker_id) {
    text($('who-name'), `Speaker ${m.speaker_id}`);
    text($('who-sub'), m.enrolled === false
      ? 'NOT ENROLLED — no reference voice to compare against'
      : 'enrolled reference voice');
  } else {
    text($('who-name'), 'No call loaded');
    text($('who-sub'), 'pick a call in the rail, then run it');
  }
}

function renderControls() {
  $('run').disabled = state.running;
  $('stop').disabled = !state.running;
  // The label names what the button actually does for the chosen source. A
  // live run is not "running a call"; it is listening, and saying so matters.
  text($('run-label'), state.running
    ? (state.source === 'live' ? 'Listening…' : 'Running…')
    : (state.source === 'live' ? 'Start listening' : 'Run call'));

  for (const source of ['file', 'live']) {
    $(`src-${source}`).setAttribute('aria-checked', String(state.source === source));
  }
  show($('file-controls'), state.source === 'file');
  show($('live-controls'), state.source === 'live');
  show($('fast-wrap'), state.source === 'file');
  show($('prompts'), state.source === 'live');
  $('demo').disabled = state.source === 'live';
  renderSpeakerSelect();
  renderMic();

  for (const mode of ['triggered', 'always_on']) {
    $(`mode-${mode}`).setAttribute('aria-checked', String(state.mode === mode));
  }

  // Panel 6. The counter only means "false alarm" on a call we know is
  // genuine -- on the attack call an alert is a true positive, and labelling
  // it otherwise would be the kind of sleight of hand this project is arguing
  // against. So the panel changes what it counts, and says which.
  const box = $('falsealarm');
  const genuine = state.groundTruth === 'bonafide';
  const count = genuine ? state.falseAlarms : state.alerts;

  // The mode of the run on screen -- taken from the run's own metadata, not from
  // `state.mode`, which follows the toggle and can be moved after a run has
  // finished. Reading the toggle here would file a naive result under Sentinel.
  const demo = state.meta && state.meta.demo;
  const runMode = state.meta && state.meta.mode;

  const readingFor = (mode) => {
    if (!demo) return null;
    if (mode === runMode) return count;          // live, or just finished
    const seen = runsSeen[`${demo}|${mode}`];
    return seen ? (genuine ? seen.falseAlarms : seen.alerts) : null;
  };
  const naive = readingFor('always_on');
  const sentinel = readingFor('triggered');
  const comparing = naive !== null && sentinel !== null;

  show($('fa-single'), !comparing);
  show($('fa-compare'), comparing);

  if (comparing) {
    renderCompare(box, genuine, runMode, naive, sentinel);
    return;
  }

  text($('fa-count'), String(count));

  const label = $('fa-label');
  const note = $('fa-note');
  if (!state.meta) {
    box.dataset.state = 'idle';
    label.firstChild.textContent = 'false alarms';
    text(note, 'pick a call');
  } else if (genuine) {
    label.firstChild.textContent = 'false alarms';
    text(note, state.mode === 'always_on'
      ? 'naive mode: every window over threshold'
      : 'Sentinel mode: nothing scored until a trigger');
    box.dataset.state = count > 0 ? 'alarming' : (state.running || state.final ? 'clean' : 'idle');
  } else if (state.groundTruth === 'spoof') {
    label.firstChild.textContent = 'alerts';
    text(note, 'ground truth: spoof — these are true positives');
    box.dataset.state = count > 0 ? 'alarming' : 'idle';
  } else {
    // Live microphone. There is no ground truth to judge an alert against, so
    // the panel says exactly that: calling these "true positives" would invent
    // a fact about a call nobody knows the truth of (SPEC §12). The count is
    // still shown -- it is just not scored.
    label.firstChild.textContent = 'alerts';
    text(note, 'live audio — no ground truth; an alert is not a verdict');
    box.dataset.state = count > 0 ? 'alarming' : 'idle';
  }
}

// Both modes on the same call, side by side. The side matching the run on
// screen is marked, so a number that is still climbing is never mistaken for a
// finished one.
function renderCompare(box, genuine, runMode, naive, sentinel) {
  // Fewer is better on a genuine call, more is better on an attack. One rule,
  // written once, so neither mode is flattered by the colour it happens to get.
  const good = (v) => genuine ? v === 0 : v > 0;

  for (const [mode, value] of [['always_on', naive], ['triggered', sentinel]]) {
    const side = $(`cmp-${mode}`);
    text(side.querySelector('b'), String(value));
    side.classList.toggle('ok', good(value));
    side.classList.toggle('bad', !good(value));
    side.classList.toggle('live', mode === runMode);
  }

  text($('cmp-title'), genuine ? 'false alarms' : 'alerts');
  text($('cmp-note'), genuine
    ? 'same call, same models — only the gating differs'
    : (good(naive) && good(sentinel)
        ? 'ground truth: spoof — both modes caught it'
        : 'ground truth: spoof — these are true positives'));

  // Neutral background: with one good number and one bad one, colouring the
  // whole panel either way would take a side the panel has not earned.
  box.dataset.state = 'compare';
}

// ---------------------------------------------------------------- live UI
// The speaker picker for live runs: which enrolled voice the call is checked
// against. "No reference" is a legitimate choice -- the lookup still runs, and
// the verdict honestly says it has nothing to compare against.
function renderSpeakerSelect() {
  const select = $('speaker');
  const signature = state.voices.map((v) => v.speaker_id).join('|');
  if (select.dataset.signature !== signature) {
    select.dataset.signature = signature;
    select.innerHTML = '';
    const none = document.createElement('option');
    none.value = '';
    none.textContent = 'No reference — lookup only';
    select.appendChild(none);
    for (const voice of state.voices) {
      const option = document.createElement('option');
      option.value = voice.speaker_id;
      option.textContent = `${voice.display_name} (${Number(voice.duration_s || 0).toFixed(1)}s)`;
      select.appendChild(option);
    }
  }
  if (state.voices.some((v) => v.speaker_id === state.speaker)) select.value = state.speaker;
  else if (!state.speaker) select.value = '';
}

function renderMic() {
  const live = state.source === 'live';
  const level = live ? state.liveUi.level : 0;
  // A bar, never a number: this answers "is sound arriving", and it is not a
  // measurement the system uses for anything.
  $('mic-level').style.width = (clamp(level * 6, 0, 1) * 100).toFixed(0) + '%';
  const dot = $('mic-dot');
  dot.dataset.state = state.liveUi.recording ? 'rec'
    : (live ? (state.liveUi.silent ? 'silent' : 'on') : 'off');
  text($('mic-note'), state.liveUi.recording ? 'recording…'
    : state.liveUi.silent ? 'no audio'
    : (state.running && live ? 'listening' : (live ? 'ready' : 'idle')));
}

function renderVoices() {
  const box = $('voice-list');
  const signature = state.voices.map((v) => `${v.speaker_id}:${v.display_name}`).join('|');
  if (box.dataset.signature !== signature) {
    box.dataset.signature = signature;
    box.innerHTML = '';
    if (!state.voices.length) {
      const p = document.createElement('p');
      p.className = 'tiny';
      p.textContent = 'No voices enrolled yet. Record one to give the system something to compare against.';
      box.appendChild(p);
    }
    for (const voice of state.voices) {
      const row = document.createElement('div');
      row.className = 'voice';
      const name = document.createElement('b');
      name.textContent = voice.display_name;
      const meta = document.createElement('span');
      meta.className = 'vmeta';
      meta.textContent = `${voice.speaker_id} · ${Number(voice.duration_s || 0).toFixed(1)}s`;
      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'vdel';
      del.title = 'Delete this voice fingerprint';
      del.setAttribute('aria-label', `Delete ${voice.display_name}`);
      del.textContent = '×';
      del.onclick = () => deleteVoice(voice.speaker_id);
      row.append(name, meta, del);
      box.appendChild(row);
    }
  }
  $('voice-record').disabled = state.running || state.liveUi.recording;
}

// The lookup chip: who the system is hearing, with the threshold it used. A
// name is only shown once the tracker has confirmed it across windows.
function renderLookup() {
  const chip = $('chip-lookup');
  const last = state.lookups.length ? state.lookups[state.lookups.length - 1] : null;
  if (!last) {
    chip.hidden = !(state.running && state.live);
    if (!chip.hidden) text(chip, 'lookup —');
    return;
  }
  chip.hidden = false;
  const match = last.match;
  if (!match || !match.best) {
    chip.dataset.state = 'idle';
    text(chip, 'lookup: no voice');
    return;
  }
  const threshold = state.lookupCfg ? state.lookupCfg.accept_similarity : null;
  if (last.announced_id) {
    chip.dataset.state = 'known';
    text(chip, `speaking: ${match.best.display_name} ${fmt(match.best.similarity, 2)}`);
  } else if (match.accepted) {
    chip.dataset.state = 'pending';
    text(chip, `confirming ${match.best.display_name} (${last.consecutive})`);
  } else {
    chip.dataset.state = 'unknown';
    text(chip, `unknown voice · best ${match.best.display_name} ` +
      `${fmt(match.best.similarity, 2)}` +
      (threshold !== null ? ` < ${fmt(threshold, 2)}` : ''));
  }
}

function renderAssess() {
  const box = $('assess-out');
  const a = state.assess;
  if (!a) { box.hidden = true; return; }
  box.hidden = false;
  box.innerHTML = '';

  const head = document.createElement('div');
  head.className = 'assess-head' + (a.fired ? ' hot' : (a.margin >= 0 ? ' near' : ''));
  head.textContent = a.fired
    ? `FIRES — ${a.intent_label}`
    : (a.margin >= 0 ? 'considered, not confirmed' : 'stays quiet');
  box.appendChild(head);

  const margin = document.createElement('div');
  margin.className = 'assess-margin';
  const label = document.createElement('span');
  label.textContent = `margin ${a.margin >= 0 ? '+' : ''}${fmt(a.margin, 2)}`;
  const track = document.createElement('span');
  track.className = 'mtrack';
  const mark = document.createElement('i');
  // Same -0.5..+0.5 window the chip colour uses, with the firing line drawn.
  mark.style.left = (clamp((a.margin + 0.5), 0, 1) * 100).toFixed(1) + '%';
  track.appendChild(mark);
  const thr = document.createElement('s');
  thr.className = 'mthr';
  thr.style.left = '55%';                 // +0.05 margin on the same scale
  track.appendChild(thr);
  margin.append(label, track);
  box.appendChild(margin);

  const detail = document.createElement('div');
  detail.className = 'assess-detail';
  detail.textContent = `nearest: ${a.intent_label || '—'} ${fmt(a.intent_similarity, 2)}` +
    ` · vs ordinary line ${fmt(a.benign_similarity, 2)}`;
  box.appendChild(detail);

  const why = document.createElement('div');
  why.className = 'assess-why';
  why.textContent = a.reason + (a.benign_text ? ` · closest ordinary line: “${a.benign_text}”` : '');
  box.appendChild(why);
}

// Suggested lines for the presenter. Clicking one scores it as text; saying it
// out loud exercises the real audio path. Nothing is injected anywhere.
//
// The group a line sits in is a claim about the engine, and every line here was
// measured (`scripts/eval_trigger.py`) before it was written down. The last
// group is the point: two indirect paraphrases we DO NOT catch are shown on
// screen as measured misses, because a card that promises a trigger the system
// does not deliver would be the demo lying about itself. `tests/test_trigger.py`
// pins both misses, and the browser E2E checks each group's claim end to end.
const PROMPTS = [
  {
    group: 'Ordinary call — should stay quiet',
    lines: [
      'The statement was sent to your registered email address on Monday.',
      "I'll transfer you to the other line, please hold.",
      'Your card will be delivered within seven working days.',
      'For your security that needs both approvers — I cannot action it on my own.',
    ],
  },
  {
    group: 'Indirect high-risk — should trigger',
    lines: [
      'Read me back whatever just came through on your handset.',
      "Let's not wake the second pair of eyes on this one.",
      'If anyone from the branch rings, you were in a meeting.',
    ],
  },
  {
    group: 'Measured misses — stay quiet, and we say so',
    lines: [
      'Just move it over to the new details before close of business.',
      'Put it through on your own authority, I will sign off when I am back.',
    ],
  },
];

function renderPrompts() {
  const box = $('prompt-groups');
  if (box.dataset.built) return;
  box.dataset.built = '1';
  for (const group of PROMPTS) {
    const g = document.createElement('div');
    g.className = 'prompt-group';
    const b = document.createElement('b');
    b.textContent = group.group;
    g.appendChild(b);
    for (const line of group.lines) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'prompt';
      btn.textContent = `“${line}”`;
      btn.onclick = () => { $('assess-text').value = line; scoreLine(); };
      g.appendChild(btn);
    }
    box.appendChild(g);
  }
}

// SPEC §12: the honesty banner follows the source. A live microphone is not a
// phone call, and a recorded replay is not live -- each says what it is.
function renderHonesty() {
  const live = state.source === 'live';
  text($('honesty-title'), live ? 'Live microphone' : 'Simulated live call');
  text($('honesty-body'), live
    ? 'Audio is analysed in memory on this machine and is never written to disk.'
    : 'Recorded audio streamed in real time. This is not a live phone call, and nothing here dials out.');
  $('honesty').dataset.state = live ? 'live' : 'sim';
}

// Each stage in the rail points at the panel that carries its evidence, so the
// hover text names the destination rather than repeating the stage.
const STEP_HINT = {
  trigger: 'Go to the timeline, where the triggers are marked',
  verify: 'Go to the verdict and how much was verified',
  challenge: 'Go to the challenge line',
  evidence: 'Go to the flagged segments',
};

// The challenge is the only stage that can have no panel to go to.
const CHALLENGE_ABSENT =
  'No challenge issued — one is only written when the verdict is Uncertain.';

// The pipeline in the rail is not decoration: each stage shows how many things
// it actually produced, so "we only verify when triggered" is visible as a
// number rather than a claim.
function renderRail() {
  const c = counts();
  const challengeOn = Boolean(
    state.verdict && state.verdict.state === 'UNCERTAIN' && state.verdict.challenge_prompt);

  // Third field: whether this stage's panel is on screen to go to. Only the
  // challenge can be absent, and it is read from state rather than from the
  // panel's own `hidden` -- renderChallenge has not run yet this frame.
  const stages = [
    ['trigger', c.triggers, true],
    ['verify', c.deep, true],
    ['challenge', challengeOn ? 1 : 0, challengeOn],
    ['evidence', c.flagged, true],
  ];

  // "on" is the furthest stage that has produced anything -- where the run got to.
  let furthest = null;
  for (const [name, n] of stages) if (n > 0) furthest = name;

  for (const [name, n, live] of stages) {
    const step = $(`step-${name}`);
    text($(`ct-${name}`), String(n));
    step.classList.toggle('fired', n > 0);
    step.classList.toggle('on', name === furthest);

    // A stage whose panel is not on screen -- the challenge, which only exists
    // on an Uncertain verdict -- stops looking clickable and says why on hover.
    // A button that silently does nothing reads as broken.
    step.classList.toggle('nolink', !live);
    step.setAttribute('aria-disabled', live ? 'false' : 'true');
    const hint = live ? STEP_HINT[name] : CHALLENGE_ABSENT;
    if (step.title !== hint) step.title = hint;
  }
}

const STATE_LABEL = {
  MONITORING: 'Monitoring',
  VERIFIED: 'Verified',
  UNCERTAIN: 'Uncertain — escalate',
  LIKELY_IMPERSONATION: 'Likely impersonation',
};

const BAND_BADGE = {
  VERIFIED: ['below the band', 'badge cool'],
  UNCERTAIN: ['inside the band', 'badge warn'],
  LIKELY_IMPERSONATION: ['above the band', 'badge hot'],
};

// The abstention band, drawn to scale across 0..1. Widths come from the
// server's thresholds, never from anything computed here.
function renderBandStrip(risk) {
  const band = (state.hello && state.hello.band) || [0.3636, 0.4575];
  const lo = clamp(band[0], 0, 1) * 100;
  const hi = clamp(band[1], 0, 1) * 100;

  $('band-ok').style.flex = `0 0 ${lo.toFixed(2)}%`;
  $('band-ab').style.flex = `0 0 ${Math.max(0, hi - lo).toFixed(2)}%`;
  $('band-no').style.flex = '1';
  $('key-ok').style.flex = `0 0 ${lo.toFixed(2)}%`;
  $('key-ab').style.flex = `0 0 ${Math.max(0, hi - lo).toFixed(2)}%`;
  $('key-no').style.flex = '1';

  const mark = $('band-mark');
  if (risk === null || risk === undefined) {
    mark.hidden = true;
  } else {
    mark.hidden = false;
    mark.style.left = clamp(risk * 100, 1.2, 98.8).toFixed(2) + '%';
  }
}

function renderVerdict() {
  const panel = $('verdict-panel');
  const v = state.verdict;
  const reasons = $('reasons');

  if (state.error) {
    panel.dataset.state = 'IDLE';
    text($('verdict-state'), 'Run failed');
    text($('verdict-risk'), '—');
    text($('verdict-conf'), '—');
    text($('verdict-windows'), '—');
    text($('verdict-segments'), '—');
    show($('risk-badge'), false);
    renderBandStrip(null);
    show($('cal-note'), false);
    if (reasons.dataset.signature !== 'error:' + state.error) {
      reasons.dataset.signature = 'error:' + state.error;
      reasons.innerHTML = '';
      const li = document.createElement('li');
      li.textContent = state.error;
      reasons.appendChild(li);
    }
    show($('action'), false);
    return;
  }

  if (!v) {
    panel.dataset.state = 'IDLE';
    text($('verdict-state'), 'Ready');
    text($('verdict-risk'), '—');
    text($('verdict-conf'), '—');
    text($('verdict-windows'), '—');
    text($('verdict-segments'), '—');
    show($('risk-badge'), false);
    renderBandStrip(null);
    text($('band-note'), 'abstention band —');
    show($('cal-note'), false);
    if (reasons.dataset.signature !== 'idle') {
      reasons.dataset.signature = 'idle';
      reasons.innerHTML = '';
      const li = document.createElement('li');
      li.className = 'placeholder';
      li.textContent = 'Nothing decided yet. Run a call.';
      reasons.appendChild(li);
    }
    show($('action'), false);
    return;
  }

  const monitoring = v.state === 'MONITORING';
  panel.dataset.state = v.state;
  text($('verdict-state'), STATE_LABEL[v.state] || v.state);
  text($('verdict-risk'), monitoring ? '—' : fmt(v.risk));
  text($('verdict-conf'), monitoring ? '—' : fmt(v.confidence, 2));
  text($('verdict-windows'), String(v.n_windows));
  text($('verdict-segments'), String((v.segments || []).length));

  renderBandStrip(monitoring ? null : v.risk);

  const badge = $('risk-badge');
  const spec = BAND_BADGE[v.state];
  if (spec && !monitoring) {
    badge.hidden = false;
    badge.className = spec[1];
    text(badge, spec[0]);
  } else {
    badge.hidden = true;
  }

  // SPEC §12: the risk number is never presented naked -- the band it was read
  // against, and the calibration that produced the band, sit beside it. They
  // get a line each so an identifier never wraps mid-hash.
  const band = (state.hello && state.hello.band) || [0, 1];
  text($('band-note'), `abstention band [${fmt(band[0], 4)}, ${fmt(band[1], 4)}]`);
  const cal = $('cal-note');
  show(cal, Boolean(v.calibration_id));
  if (v.calibration_id) text(cal, `calibration ${v.calibration_id}`);

  const signature = v.reasons.join('||');
  if (reasons.dataset.signature !== signature) {
    reasons.dataset.signature = signature;
    reasons.innerHTML = '';
    for (const reason of v.reasons) {
      const li = document.createElement('li');
      li.textContent = reason;
      reasons.appendChild(li);
    }
  }

  const action = $('action');
  if (v.recommended_action) {
    action.hidden = false;
    if (action.dataset.value !== v.recommended_action) {
      action.dataset.value = v.recommended_action;
      action.innerHTML = '';
      const k = document.createElement('span');
      k.className = 'action-k';
      k.textContent = 'recommended action';
      const body = document.createElement('div');
      body.textContent = v.recommended_action;
      action.append(k, body);
    }
  } else {
    action.hidden = true;
  }
}

// Three circles, sized by how many windows survived each stage. The gap
// between "scored" and "deep" is the saving the whole design exists to make,
// so it is drawn to scale rather than stated.
function renderReach() {
  const c = counts();
  const max = Math.max(c.scored, 1);
  const R1 = 42;
  const radius = (n, lo, hi) => clamp(R1 * Math.sqrt(n / max), lo, hi);
  const r1 = c.scored > 0 ? R1 : 0;
  const r2 = c.deep > 0 ? radius(c.deep, 19, 37) : 0;
  const r3 = c.flagged > 0 ? radius(c.flagged, 16, 29) : 0;

  const place = (id, r, left, top, n) => {
    const el = $(id);
    if (!r) { el.style.display = 'none'; return; }
    el.style.display = 'grid';
    el.style.width = el.style.height = (r * 2) + 'px';
    el.style.left = left + 'px';
    el.style.top = top + 'px';
    const b = el.querySelector('b');
    b.textContent = String(n);
    b.style.fontSize = clamp(r * 0.5, 13, 21).toFixed(1) + 'px';
    el.querySelector('s').style.display = r < 26 ? 'none' : 'block';
  };

  place('bub-scored', r1, 0, 0, c.scored);
  place('bub-deep', r2, R1 * 2 - 12, R1 - r2, c.deep);
  place('bub-flagged', r3, R1 - r3 + 5, R1 * 2 - r3 * 0.5, c.flagged);

  const note = $('cov-note');
  if (!c.scored) {
    text(note, 'Nothing scored yet.');
  } else {
    text(note, `The expensive check ran on ${c.deep} of ${c.scored} windows` +
      (state.mode === 'always_on'
        ? ' — naive mode scores every one of them.'
        : ' — only inside the triggered region.'));
  }
}

// The two aggregate scores the verdict was fused from, with the extreme each
// one reached during the call.
function renderTimelineHead() {
  const v = state.verdict;
  text($('tl-cm'), v && v.cm_risk !== null && v.cm_risk !== undefined ? fmt(v.cm_risk) : '—');
  text($('tl-spk'), v && v.speaker_risk !== null && v.speaker_risk !== undefined ? fmt(v.speaker_risk) : '—');
  text($('tl-cm-peak'), state.cm.length
    ? 'peak ' + fmt(Math.max(...state.cm.map((p) => p.v))) : '');
  text($('tl-spk-floor'), state.spk.length
    ? 'floor ' + fmt(Math.min(...state.spk.map((p) => p.v))) : '');
}

const OVERLAY_DISCLOSURE =
  'Lines marked SCRIPTED are injected, not transcribed. The demo audio is read ' +
  'speech from ASVspoof and contains no financial instruction, so these lines ' +
  'demonstrate the trigger mechanism on audio that is not a fraud call. The same ' +
  'overlay runs on both calls — only verification tells them apart.';

function renderTranscript() {
  const box = $('transcript');
  const overlayOn = Boolean(state.runStart && state.runStart.scripted_overlay);

  // Never ship the overlay silently (IMPLEMENTATION-PLAN 2.6). Marking the
  // individual lines is not enough on its own -- a judge should be told what
  // they are before reading them, and should not have to scroll back up for it.
  const note = $('overlay-note');
  note.hidden = !overlayOn;
  if (overlayOn) text(note, OVERLAY_DISCLOSURE);

  text($('transcript-sub'),
    state.meta ? `${state.meta.file} · ground truth ${state.meta.ground_truth || 'unknown'}` : '');

  const signature =
    `${state.utterances.length}|${state.triggers.length}|${state.running}`;
  if (box.dataset.signature === signature) return;
  box.dataset.signature = signature;
  box.innerHTML = '';

  if (!state.utterances.length) {
    const p = document.createElement('p');
    p.className = 'placeholder';
    p.textContent = state.running ? 'Listening…' : 'Waiting for the call to start.';
    box.appendChild(p);
    return;
  }

  const triggerAt = new Map();
  for (const t of state.triggers) triggerAt.set(t.utterance.t_end_ms + '|' + t.utterance.text, t);

  for (const u of state.utterances) {
    const trigger = triggerAt.get(u.t_end_ms + '|' + u.text);
    const line = document.createElement('div');
    line.className = 'line' + (u.scripted ? ' scripted' : '') + (trigger ? ' triggered' : '');

    const t = document.createElement('span');
    t.className = 't';
    t.textContent = secs(u.t_end_ms);

    const txt = document.createElement('span');
    txt.className = 'txt';
    if (u.scripted) {
      const tag = document.createElement('span');
      tag.className = 'tag scripted';
      tag.textContent = 'SCRIPTED';
      txt.appendChild(tag);
    }
    if (trigger) {
      const tag = document.createElement('span');
      tag.className = 'tag trig';
      tag.textContent = 'TRIGGER';
      txt.appendChild(tag);
    }
    if (u.scripted || trigger) {
      // The tags take their own line, so the words are never wrapped around them.
      const body = document.createElement('div');
      body.textContent = u.text;
      txt.appendChild(body);
    } else {
      txt.appendChild(document.createTextNode(u.text));
    }

    if (trigger) {
      const detail = document.createElement('div');
      detail.className = 'trigger-detail';
      detail.textContent = trigger.intent;
      const meta = document.createElement('span');
      meta.className = 'meta';
      // The two-stage structure IS the answer to "isn't this just keyword
      // matching?", so the stage and the margin are on screen, not in a log.
      meta.textContent =
        `stage: ${trigger.stage} · closer to a fraud instruction than to normal ` +
        `call content by ${trigger.margin >= 0 ? '+' : ''}${fmt(trigger.margin, 2)}` +
        (trigger.matched_terms.length ? ` · matched "${trigger.matched_terms.join('", "')}"` : ' · no keyword overlap');
      detail.appendChild(meta);
      txt.appendChild(detail);
    }

    // The margin chip: what the trigger thought of EVERY line, not only the
    // ones that fired. This is the "trigger points" view -- a near-miss is
    // visibly considered, and the tooltip names the intent family it was
    // closest to and the ordinary line that beat it.
    const a = u.assessment;
    if (a && a.min_words_met) {
      const chip = document.createElement('span');
      chip.className = 'mchip' + (a.fired ? ' hot' : (a.margin >= 0 ? ' near' : ''));
      chip.textContent = (a.margin >= 0 ? '+' : '') + fmt(a.margin, 2);
      chip.title = `${a.intent_label || 'nearest intent'} — ${a.reason}` +
        (a.benign_text ? `\nclosest ordinary line: “${a.benign_text}”` : '');
      txt.appendChild(chip);
    }

    line.append(t, txt);
    box.appendChild(line);
  }
  box.scrollTop = box.scrollHeight;
}

function renderChallenge() {
  const panel = $('challenge-panel');
  const v = state.verdict;
  const prompt = v && v.state === 'UNCERTAIN' ? v.challenge_prompt : '';
  panel.hidden = !prompt;
  // With no challenge on screen the timeline takes the whole width rather than
  // leaving a hole where the card would have been.
  $('bottom').dataset.challenge = prompt ? 'on' : 'off';
  if (prompt) text($('challenge-prompt'), prompt);
}

function renderEvidence() {
  const v = state.verdict;
  const segments = (v && v.segments) || [];
  const box = $('evidence');
  const signature = `${segments.length}|${v ? v.state : ''}|${v ? v.risk : ''}`;

  text($('evidence-sub'), segments.length
    ? `${segments.length} window(s) at or above ${fmt((state.hello && state.hello.evidence_risk_floor) || 0, 4)} fused risk`
    : '');

  if (box.dataset.signature !== signature) {
    box.dataset.signature = signature;
    box.innerHTML = '';
    if (!segments.length) {
      const p = document.createElement('p');
      p.className = 'placeholder';
      p.textContent = v && v.state === 'VERIFIED'
        ? 'No suspicious segments — nothing crossed the evidence threshold.'
        : 'No suspicious segments.';
      box.appendChild(p);
    } else {
      const table = document.createElement('table');
      table.className = 'segments';
      const head = document.createElement('tr');
      for (const h of ['window', 'fused', 'artifacts', 'voice match']) {
        const th = document.createElement('th');
        th.textContent = h;
        head.appendChild(th);
      }
      table.appendChild(head);
      let anySingle = false;
      for (const s of segments) {
        const tr = document.createElement('tr');
        const single = (s.n_inputs || 2) < 2;
        if (single) anySingle = true;
        const cells = [
          `${(s.t_start_ms / 1000).toFixed(1)}–${(s.t_end_ms / 1000).toFixed(1)}s`,
          fmt(s.fused_risk) + (single ? ' *' : ''),
          fmt(s.cm_risk),
          fmt(s.speaker_risk),
        ];
        cells.forEach((c, i) => {
          const td = document.createElement('td');
          if (i === 1) {
            // The fused column carries its own magnitude, so thirty rows read
            // as a shape instead of a wall of digits.
            td.className = 'risk';
            const bar = document.createElement('i');
            bar.style.width = (30 + clamp(s.fused_risk || 0, 0, 1) * 70).toFixed(0) + '%';
            const span = document.createElement('span');
            span.textContent = c;
            td.append(bar, span);
          } else {
            td.textContent = c;
          }
          if (single) td.title = 'Only one signal was usable on this window — not a genuine two-way match.';
          tr.appendChild(td);
        });
        table.appendChild(tr);
      }
      box.appendChild(table);
      if (anySingle) {
        const note = document.createElement('p');
        note.className = 'placeholder';
        note.textContent = '* fused from a single signal — the other check had no usable reading on that window.';
        box.appendChild(note);
      }
    }
  }

  // Model and calibration ids, per SPEC §1 step 7. These are what make the
  // verdict attributable when calibration.json is later replaced.
  const ids = $('ids');
  const rows = [];
  if (v && v.model_ids) rows.push(['models', v.model_ids.join('  +  ')]);
  if (v && v.calibration_id) rows.push(['calibration', v.calibration_id]);
  if (state.meta && state.meta.evidence_log) rows.push(['evidence log', state.meta.evidence_log]);
  if (state.meta && state.meta.speaker_id) {
    rows.push(['enrolled as', state.meta.speaker_id + (state.meta.enrolled ? '' : ' (NOT ENROLLED)')]);
  }
  const idSignature = JSON.stringify(rows);
  if (ids.dataset.signature !== idSignature) {
    ids.dataset.signature = idSignature;
    ids.innerHTML = '';
    for (const [k, val] of rows) {
      const row = document.createElement('div');
      row.className = 'row';
      const b = document.createElement('b');
      b.textContent = k;
      const s = document.createElement('span');
      s.textContent = val;
      row.append(b, s);
      ids.appendChild(row);
    }
  }
}

function renderFooter() {
  const s = state.stats;
  if (s) {
    text($('footer-stats'),
      `${s.windows_total} windows (${s.windows_scored} scored, ${s.windows_silent} silent, ` +
      `${s.windows_deep} deep) · ${s.utterances} utterances · ${s.triggers} triggers · ` +
      `alerts ${s.alerts} · max lag ${s.max_lag_ms} ms · ` +
      (s.audio_dropped_ms ? `dropped ${s.audio_dropped_ms} ms of live audio · ` : '') +
      `${s.wall_s}s wall clock for ${s.stream_s}s of audio`);
  } else if (state.running) {
    text($('footer-stats'),
      `${state.spk.length} windows scored · ${state.cm.length} deep · ` +
      `${state.silent.length} silent · ${state.triggers.length} triggers`);
  } else {
    text($('footer-stats'), '—');
  }

  const cal = state.hello && state.hello.calibration;
  if (cal) {
    text($('footer-provenance'),
      `${cal.backbone || ''} · fusion ${cal.fusion} · ${cal.notes || ''}`.trim());
  }
}

// ---------------------------------------------------------------- timeline
const canvas = $('canvas');
const ctx = canvas.getContext('2d');

// The chart card is dark in both themes, so its palette is fixed.
const TL = {
  spk: '#b6a6f8',      // voice match
  cm: '#d8f24d',       // synthesis artifacts
  trigger: '#ff5a40',
  band: 'rgba(240, 180, 41, 0.085)',
  bandLine: 'rgba(240, 180, 41, 0.38)',
  gate: 'rgba(255, 255, 255, 0.055)',
  gateLine: 'rgba(255, 255, 255, 0.16)',
  gateText: 'rgba(255, 255, 255, 0.5)',
  grid: 'rgba(255, 255, 255, 0.05)',
  axis: '#767d85',
  silent: 'rgba(255, 255, 255, 0.28)',
  playhead: 'rgba(255, 255, 255, 0.3)',
};

// Which stretches of audio the expensive check actually covered.
//
// The gate's own regions arrive on the trigger event, which is what makes the
// shading appear the instant a trigger fires -- before any deep score exists.
// But that snapshot is taken at trigger time and does not include the hold
// that runs on afterwards, so on its own it under-reports the tail. Each deep
// score we were sent is direct evidence that the window it covers was
// verified, so the two are merged. Nothing is inferred: every span here comes
// from an event the server sent.
function gateSpans(totalMs) {
  if (state.mode === 'always_on') return [[0, totalMs]];

  const hopMs = ((state.hello && state.hello.hop_s) || 0.5) * 1000;
  const windowMs = ((state.hello && state.hello.window_s) || 3) * 1000;
  const spans = [];
  for (const [start, end] of state.regions) spans.push([start, Math.min(end, totalMs)]);
  for (const p of state.cm) spans.push([Math.max(0, p.t - windowMs), Math.min(p.t, totalMs)]);
  if (!spans.length) return [];

  spans.sort((a, b) => a[0] - b[0]);
  const merged = [spans[0].slice()];
  for (let i = 1; i < spans.length; i += 1) {
    const last = merged[merged.length - 1];
    if (spans[i][0] <= last[1] + hopMs) last[1] = Math.max(last[1], spans[i][1]);
    else merged.push(spans[i].slice());
  }
  return merged;
}

function rrect(x, y, w, h, r) {
  if (ctx.roundRect) { ctx.beginPath(); ctx.roundRect(x, y, w, h, r); return; }
  ctx.beginPath(); ctx.rect(x, y, w, h);
}

function drawTimeline() {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (!w || !h) return;
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr;
    canvas.height = h * dpr;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  // The bottom margin is a lane for the trigger markers, so a label never
  // lands on top of the data it is labelling.
  const pad = { l: 42, r: 14, t: 10, b: 42 };
  const plotW = w - pad.l - pad.r;
  const plotH = h - pad.t - pad.b;
  const TOP = 1.28;                       // headroom above 1.00 for the gate label
  // A live call has no known length: the axis grows with the clock so the
  // playhead stays on screen for as long as the person keeps talking.
  const totalMs = Math.max(
    1000,
    state.live ? Math.max(state.clockMs * 1.15, 30000)
               : (state.durationS || 40) * 1000,
  );
  const x = (ms) => pad.l + (ms / totalMs) * plotW;
  const y = (v) => pad.t + (1 - v / TOP) * plotH;

  ctx.strokeStyle = TL.grid;
  ctx.lineWidth = 1;
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    ctx.beginPath();
    ctx.moveTo(pad.l, y(v));
    ctx.lineTo(w - pad.r, y(v));
    ctx.stroke();
  }

  // --- the abstention band. Drawn first, because everything else is read
  // against it: this is the region where the system declines to guess.
  const band = (state.hello && state.hello.band) || [0.3636, 0.4575];
  ctx.fillStyle = TL.band;
  ctx.fillRect(pad.l, y(band[1]), plotW, y(band[0]) - y(band[1]));
  ctx.strokeStyle = TL.bandLine;
  ctx.setLineDash([5, 5]);
  for (const b of band) {
    ctx.beginPath();
    ctx.moveTo(pad.l, y(b));
    ctx.lineTo(w - pad.r, y(b));
    ctx.stroke();
  }
  ctx.setLineDash([]);

  // --- gated regions: where deep verification was allowed to run. Neutral,
  // not alarming -- the shading marks effort spent, not suspicion.
  const spans = gateSpans(totalMs);
  const gateLabel = state.mode === 'always_on'
    ? 'EVERY WINDOW DEEP-VERIFIED' : 'DEEP VERIFICATION ACTIVE';
  for (const [start, end] of spans) {
    const x0 = x(start);
    const x1 = Math.max(x0 + 2, x(end));
    ctx.fillStyle = TL.gate;
    rrect(x0, pad.t, x1 - x0, plotH, 14); ctx.fill();
    ctx.strokeStyle = TL.gateLine;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    rrect(x0, pad.t, x1 - x0, plotH, 14); ctx.stroke();
    ctx.setLineDash([]);
    if (x1 - x0 > 150) {
      ctx.fillStyle = TL.gateText;
      ctx.font = '700 9px Hanken, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(gateLabel, (x0 + x1) / 2, pad.t + 15);
    }
  }

  // --- axes
  ctx.fillStyle = TL.axis;
  ctx.font = '10px DMMono, ui-monospace, Menlo, monospace';
  ctx.textAlign = 'right';
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    ctx.fillText(v.toFixed(2), pad.l - 9, y(v) + 3.5);
  }
  ctx.textAlign = 'center';
  const stepS = totalMs > 60000 ? 10 : 5;
  for (let t = 0; t <= totalMs / 1000; t += stepS) {
    ctx.fillText(`${t}s`, x(t * 1000), pad.t + plotH + 37);
  }

  // --- silent windows: marked, never interpolated over. A gap in the line is
  // the honest rendering of "we refused to score this" (SPEC Gap 3).
  ctx.fillStyle = TL.silent;
  for (const p of state.silent) {
    ctx.fillRect(x(p.t) - 1, pad.t + plotH - 6, 2, 6);
  }

  const line = (points, colour) => {
    if (!points.length) return;
    ctx.strokeStyle = colour;
    ctx.lineWidth = 2.6;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    points.forEach((p, i) => (i ? ctx.lineTo(x(p.t), y(p.v)) : ctx.moveTo(x(p.t), y(p.v))));
    ctx.stroke();
  };
  line(state.spk, TL.spk);
  line([...state.cm].sort((a, b) => a.t - b.t), TL.cm);

  // --- triggers: a rule through the plot, labelled in the lane below it.
  for (const t of state.triggers) {
    const tx = x(t.t_ms);
    ctx.strokeStyle = TL.trigger;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    ctx.moveTo(tx, pad.t + 22);
    ctx.lineTo(tx, pad.t + plotH + 9);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = TL.trigger;
    rrect(tx - 27, pad.t + plotH + 10, 54, 15, 7.5); ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.font = '700 8.5px Hanken, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('TRIGGER', tx, pad.t + plotH + 20.5);
  }

  // --- playhead
  if (state.clockMs > 0) {
    ctx.strokeStyle = TL.playhead;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x(state.clockMs), pad.t);
    ctx.lineTo(x(state.clockMs), pad.t + plotH);
    ctx.stroke();
  }
}

// ---------------------------------------------------------------- loop
function frame() {
  if (dirty) {
    dirty = false;
    renderHeader();
    renderControls();
    renderRail();
    renderVerdict();
    renderReach();
    renderChallenge();
    renderTranscript();
    renderEvidence();
    renderTimelineHead();
    renderFooter();
    renderVoices();
    renderAssess();
    renderLookup();
    renderHonesty();
    renderPrompts();
    drawTimeline();
  }
  requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- controls
let selectedMode = 'triggered';
let modeManuallySet = false;

async function loadDemos() {
  const demos = await (await fetch('/demos')).json();
  const select = $('demo');
  select.innerHTML = '';
  for (const call of demos.calls) {
    const option = document.createElement('option');
    option.value = call.id;
    option.textContent = `${call.title}  (${call.duration_s.toFixed(0)}s, ground truth: ${call.ground_truth})`;
    option.title = option.textContent;
    select.appendChild(option);
  }
  if (!demos.calls.length) {
    const option = document.createElement('option');
    option.textContent = demos.error || 'no demo audio';
    select.appendChild(option);
    $('run').disabled = true;
  }
}

function setMode(mode) {
  selectedMode = mode;
  modeManuallySet = true;
  state.mode = mode;
  touch();
}

$('mode-triggered').onclick = () => setMode('triggered');
$('mode-always_on').onclick = () => setMode('always_on');

// ---------------------------------------------------------------- source
function setSource(source) {
  if (state.running) return;            // changing source mid-run makes no sense
  state.source = source;
  touch();
}

$('src-file').onclick = () => setSource('file');
$('src-live').onclick = () => setSource('live');
$('speaker').onchange = () => { state.speaker = $('speaker').value; touch(); };

// ---------------------------------------------------------------- voices
async function refreshVoices() {
  try {
    const data = await (await fetch('/voices')).json();
    state.voices = data.voices || [];
    touch();
  } catch (err) { /* the events socket will bring /hello with the list */ }
}

async function deleteVoice(speakerId) {
  try {
    const response = await fetch(`/voices/${encodeURIComponent(speakerId)}`, {
      method: 'DELETE',
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'delete failed');
    state.voices = data.voices || [];
    if (state.speaker === speakerId) {
      state.speaker = state.voices.length ? state.voices[0].speaker_id : '';
    }
  } catch (err) {
    state.error = err.message;
  }
  touch();
}

$('voice-record').onclick = async () => {
  if (state.running || state.liveUi.recording) return;
  const status = $('voice-status');
  state.liveUi.recording = true;
  state.error = null;
  touch();
  try {
    const result = await SentinelLive.record(10, {
      onTick: (elapsed, total) => {
        text(status, `recording… ${Math.max(0, Math.ceil(total - elapsed))}s left`);
        touch();
      },
    });
    if (!result) throw new Error('recording cancelled');
    // Release the microphone before asking for a name: leaving the browser's
    // recording indicator on while a text box is up looks like spyware.
    await SentinelLive.release();

    const name = (window.prompt('Name this voice', 'Coordinator') || '').trim();
    if (!name) throw new Error('a name is required');
    text(status, 'saving…');
    const response = await fetch('/voices', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: name,
        sample_rate: result.sampleRate,
        pcm_int16_b64: SentinelLive.toInt16Base64(result.pcm),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'enrolment failed');
    state.voices = data.voices || [];
    const meta = data.meta || {};
    if (meta.speaker_id) state.speaker = meta.speaker_id;
    text(status, `saved ${meta.speaker_id} · ${meta.embedding_dim}-dim`);
  } catch (err) {
    state.error = err.message;
    text(status, err.message);
    try { await SentinelLive.release(); } catch (e) { /* already released */ }
  } finally {
    state.liveUi.recording = false;
    touch();
  }
};

// ---------------------------------------------------------------- try a line
async function scoreLine() {
  const input = $('assess-text');
  const value = (input.value || '').trim();
  if (!value) return;
  text($('assess-note'), 'scoring…');
  try {
    const response = await fetch('/assess', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'scoring failed');
    state.assess = data.assessment;
    text($('assess-note'), 'text only — no audio claim');
  } catch (err) {
    state.error = err.message;
    text($('assess-note'), err.message);
  }
  touch();
}

$('assess-go').onclick = scoreLine;
$('assess-text').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') scoreLine();
});

// ---------------------------------------------------------------- rail nav
// Clicking a pipeline stage goes to the panel that holds its evidence and rings
// that panel for a moment. The ring is the point: on a wide screen every panel
// is already visible, so a scroll alone would look like nothing happened.
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

let ringTimer = null;

function ring(el, className, ms) {
  clearTimeout(ringTimer);
  for (const stale of document.querySelectorAll('.flash, .nudge')) {
    stale.classList.remove('flash', 'nudge');
  }
  void el.offsetWidth;               // restart it when the same thing is clicked twice
  el.classList.add(className);
  ringTimer = setTimeout(() => el.classList.remove(className), ms);
}

for (const step of document.querySelectorAll('.step')) {
  step.onclick = () => {
    const panel = $(step.dataset.panel);
    if (!panel || panel.hidden) { ring(step, 'nudge', 400); return; }
    panel.scrollIntoView({
      behavior: reduceMotion.matches ? 'auto' : 'smooth',
      block: 'nearest',
    });
    ring(panel, 'flash', 1400);
  };
}

$('run').onclick = async () => {
  if (state.source === 'live') {
    // Live: open the microphone, then the socket. The server starts the run on
    // the socket's `start` message and events arrive over /stream as usual.
    state.running = true;
    state.error = null;
    state.liveUi.silent = false;
    state.liveUi.level = 0;
    touch();
    const started = await SentinelLive.start({
      mode: selectedMode,
      speaker: state.speaker || null,
      noAudioWarnMs: (state.liveCfg && state.liveCfg.no_audio_warn_ms) || 700,
      onLevel: (level) => { state.liveUi.level = level; touch(); },
      onState: (update) => {
        if (update.running === false) state.running = false;
        if (update.silent === true) state.liveUi.silent = true;
        if (update.silent === false) state.liveUi.silent = false;
        touch();
      },
      onError: (message) => {
        state.running = false;
        state.error = message;
        // The server may have started a run before capture failed. Stop it.
        fetch('/stop', { method: 'POST' });
        touch();
      },
    });
    if (!started) state.running = false;
    touch();
    return;
  }

  state.running = true;
  touch();
  const response = await fetch('/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      demo: $('demo').value,
      mode: selectedMode,
      fast: $('fast').checked,
    }),
  });
  if (!response.ok) {
    state.running = false;
    state.error = (await response.json()).error;
    touch();
  }
};

$('stop').onclick = () => {
  // Live runs have two things to stop: the capture in the browser and the
  // pipeline on the server. Closing the socket ends the source; POST /stop
  // joins the thread. Doing both makes either one sufficient.
  if (state.source === 'live' || state.live) SentinelLive.stop('stopped by operator');
  fetch('/stop', { method: 'POST' });
};

// ---------------------------------------------------------------- theme
// The choice is remembered; with no choice made, the OS decides.
const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');

function activeTheme() {
  return document.documentElement.dataset.theme || (darkQuery.matches ? 'dark' : 'light');
}

$('theme').onclick = () => {
  const next = activeTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('sentinel-theme', next); } catch (e) { /* private mode */ }
  touch();
};
darkQuery.addEventListener('change', touch);

window.addEventListener('resize', touch);

loadDemos();
connect();
requestAnimationFrame(frame);
