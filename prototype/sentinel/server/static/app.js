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
};

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
    const tag = state.meta.fast ? ' · fast replay' : '';
    text(clock, `${secs(state.clockMs)} / ${state.durationS.toFixed(1)}s${tag}`);
  } else {
    text(clock, 'no call loaded');
  }

  // Who the call is being checked against. The enrolment is the whole premise,
  // so a call running against a speaker with no reference has to say so.
  const m = state.meta;
  if (m && m.speaker_id) {
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
  text($('run-label'), state.running ? 'Running…' : 'Run call');

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

// The pipeline in the rail is not decoration: each stage shows how many things
// it actually produced, so "we only verify when triggered" is visible as a
// number rather than a claim.
function renderRail() {
  const c = counts();
  const challengeOn = Boolean(
    state.verdict && state.verdict.state === 'UNCERTAIN' && state.verdict.challenge_prompt);

  const stages = [
    ['trigger', c.triggers],
    ['verify', c.deep],
    ['challenge', challengeOn ? 1 : 0],
    ['evidence', c.flagged],
  ];

  // "on" is the furthest stage that has produced anything -- where the run got to.
  let furthest = null;
  for (const [name, n] of stages) if (n > 0) furthest = name;

  for (const [name, n] of stages) {
    const step = $(`step-${name}`);
    text($(`ct-${name}`), String(n));
    step.classList.toggle('fired', n > 0);
    step.classList.toggle('on', name === furthest);
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
  const totalMs = Math.max(1000, (state.durationS || 40) * 1000);
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
