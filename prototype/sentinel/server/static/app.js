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
 * The one exception is formatting, and the one near-exception is the timeline,
 * which draws the points it was sent.
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
};

let dirty = true;
const touch = () => { dirty = true; };

// ---------------------------------------------------------------- helpers
const $ = (id) => document.getElementById(id);
const fmt = (v, n = 3) => (v === null || v === undefined) ? '—' : Number(v).toFixed(n);
const secs = (ms) => (ms / 1000).toFixed(1) + 's';
const pct = (v) => (v * 100).toFixed(1) + '%';

function text(el, value) { if (el.textContent !== value) el.textContent = value; }

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
  state.running = true;
  if (meta) {
    state.mode = meta.mode;
    state.groundTruth = meta.ground_truth;
    state.durationS = meta.duration_s || 0;
  }
  touch();
}

function apply(event) {
  switch (event.type) {
    case 'hello':
      state.hello = event;
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
      if (event.duration_s) state.durationS = event.duration_s;
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
    const tag = state.meta.fast ? ' · fast replay' : '';
    text(clock, `${secs(state.clockMs)} / ${state.durationS.toFixed(1)}s${tag}`);
  } else {
    text(clock, 'no call loaded');
  }
}

function renderControls() {
  $('run').disabled = state.running;
  $('stop').disabled = !state.running;
  $('run').textContent = state.running ? 'Running…' : 'Run call';

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
  text($('fa-count'), String(count));

  const label = box.querySelector('.fa-label');
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
  } else {
    label.firstChild.textContent = 'alerts';
    text(note, 'ground truth: spoof — these are true positives');
    box.dataset.state = count > 0 ? 'alarming' : 'idle';
  }
}

const STATE_LABEL = {
  MONITORING: 'MONITORING',
  VERIFIED: 'VERIFIED',
  UNCERTAIN: 'UNCERTAIN — ESCALATE',
  LIKELY_IMPERSONATION: 'LIKELY IMPERSONATION',
};

function renderVerdict() {
  const panel = $('verdict-panel');
  const v = state.verdict;

  if (state.error) {
    panel.dataset.state = 'IDLE';
    text($('verdict-state'), 'RUN FAILED');
    $('reasons').innerHTML = '';
    const li = document.createElement('li');
    li.textContent = state.error;
    $('reasons').appendChild(li);
    return;
  }
  if (!v) {
    panel.dataset.state = 'IDLE';
    text($('verdict-state'), 'READY');
    text($('verdict-risk'), '—');
    text($('verdict-conf'), '—');
    text($('verdict-windows'), '—');
    $('reasons').innerHTML = '';
    $('action').hidden = true;
    return;
  }

  panel.dataset.state = v.state;
  text($('verdict-state'), STATE_LABEL[v.state] || v.state);
  text($('verdict-risk'), v.state === 'MONITORING' ? '—' : fmt(v.risk));
  text($('verdict-conf'), v.state === 'MONITORING' ? '—' : fmt(v.confidence, 2));
  text($('verdict-windows'), String(v.n_windows));

  const band = (state.hello && state.hello.band) || [0, 1];
  text($('band-note'),
    `abstention band [${fmt(band[0], 4)}, ${fmt(band[1], 4)}]` +
    (v.calibration_id ? ` · calibration ${v.calibration_id}` : ''));

  const reasons = $('reasons');
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

  const signature =
    `${state.utterances.length}|${state.triggers.length}|${state.running}`;
  if (box.dataset.signature === signature) return;
  box.dataset.signature = signature;
  box.innerHTML = '';

  text($('transcript-sub'),
    state.meta ? `${state.meta.file} · ground truth ${state.meta.ground_truth || 'unknown'}` : '');

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
    txt.appendChild(document.createTextNode(u.text));

    line.append(t, txt);
    box.appendChild(line);

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
      box.appendChild(detail);
    }
  }
  box.scrollTop = box.scrollHeight;
}

function renderChallenge() {
  const panel = $('challenge-panel');
  const v = state.verdict;
  const prompt = v && v.state === 'UNCERTAIN' ? v.challenge_prompt : '';
  panel.hidden = !prompt;
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
          if (i === 1) td.className = 'risk';
          td.textContent = c;
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

function drawTimeline() {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr;
    canvas.height = h * dpr;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const pad = { l: 44, r: 12, t: 10, b: 22 };
  const plotW = w - pad.l - pad.r;
  const plotH = h - pad.t - pad.b;
  const totalMs = Math.max(1000, (state.durationS || 40) * 1000);
  const x = (ms) => pad.l + (ms / totalMs) * plotW;
  const y = (v) => pad.t + (1 - v) * plotH;

  // --- the abstention band. Drawn first, because everything else is read
  // against it: this is the region where the system declines to guess.
  const band = (state.hello && state.hello.band) || [0.3636, 0.4575];
  ctx.fillStyle = 'rgba(227, 160, 8, 0.13)';
  ctx.fillRect(pad.l, y(band[1]), plotW, y(band[0]) - y(band[1]));
  ctx.strokeStyle = 'rgba(227, 160, 8, 0.45)';
  ctx.setLineDash([4, 4]);
  ctx.lineWidth = 1;
  for (const b of band) {
    ctx.beginPath();
    ctx.moveTo(pad.l, y(b));
    ctx.lineTo(w - pad.r, y(b));
    ctx.stroke();
  }
  ctx.setLineDash([]);

  // --- gated regions: where deep verification was allowed to run.
  ctx.fillStyle = 'rgba(248, 81, 73, 0.10)';
  for (const [start, end] of state.regions) {
    ctx.fillRect(x(start), pad.t, Math.max(1, x(Math.min(end, totalMs)) - x(start)), plotH);
  }
  if (state.mode === 'always_on') {
    ctx.fillStyle = 'rgba(248, 81, 73, 0.07)';
    ctx.fillRect(pad.l, pad.t, plotW, plotH);
  }

  // --- axes
  ctx.strokeStyle = '#263041';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, pad.t + plotH);
  ctx.lineTo(w - pad.r, pad.t + plotH);
  ctx.stroke();

  ctx.fillStyle = '#5b6673';
  ctx.font = '10px ui-monospace, Menlo, monospace';
  ctx.textAlign = 'right';
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    ctx.fillText(v.toFixed(2), pad.l - 6, y(v) + 3);
  }
  ctx.textAlign = 'center';
  const stepS = totalMs > 60000 ? 10 : 5;
  for (let t = 0; t <= totalMs / 1000; t += stepS) {
    ctx.fillText(`${t}s`, x(t * 1000), h - 7);
  }

  // --- silent windows: marked, never interpolated over. A gap in the line is
  // the honest rendering of "we refused to score this" (SPEC Gap 3).
  ctx.fillStyle = 'rgba(139, 152, 169, 0.30)';
  for (const p of state.silent) {
    ctx.fillRect(x(p.t) - 1, pad.t + plotH - 5, 2, 5);
  }

  const line = (points, colour) => {
    if (!points.length) return;
    ctx.strokeStyle = colour;
    ctx.lineWidth = 1.8;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    points.forEach((p, i) => (i ? ctx.lineTo(x(p.t), y(p.v)) : ctx.moveTo(x(p.t), y(p.v))));
    ctx.stroke();
    ctx.fillStyle = colour;
    for (const p of points) {
      ctx.beginPath();
      ctx.arc(x(p.t), y(p.v), 1.7, 0, Math.PI * 2);
      ctx.fill();
    }
  };
  line(state.spk, '#58a6ff');
  line([...state.cm].sort((a, b) => a.t - b.t), '#d2a8ff');

  // --- triggers: a vertical rule, labelled.
  ctx.textAlign = 'left';
  for (const t of state.triggers) {
    const tx = x(t.t_ms);
    ctx.strokeStyle = '#f85149';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(tx, pad.t);
    ctx.lineTo(tx, pad.t + plotH);
    ctx.stroke();
    ctx.fillStyle = '#f85149';
    ctx.font = '9px ui-monospace, Menlo, monospace';
    ctx.save();
    ctx.translate(tx + 3, pad.t + 4);
    ctx.fillText('TRIGGER', 0, 6);
    ctx.restore();
  }

  // --- playhead
  if (state.clockMs > 0) {
    ctx.strokeStyle = 'rgba(230, 237, 243, 0.35)';
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
    renderVerdict();
    renderChallenge();
    renderTranscript();
    renderEvidence();
    renderFooter();
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

$('run').onclick = async () => {
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

$('stop').onclick = () => fetch('/stop', { method: 'POST' });

window.addEventListener('resize', touch);

loadDemos();
connect();
requestAnimationFrame(frame);
