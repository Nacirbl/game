/* game.js — the play page, rebuilt.
 *
 * One rule: the server owns the truth. This file fetches public_state
 * (GET /api/game/{sid}?player=me) and renders it. Every WebSocket message
 * is just "something changed" -> refetch -> render. Rendering is a pure
 * function of state, so refresh/reconnect/multi-tab can't desync the UI.
 */
import '/static/card_stack_system.js?v=4';
const CardStack = window.CardStack;

/* ── session identity ─────────────────────────────────────────── */
const sessionId = window.__SESSION_ID__;
const quizTitle = window.__GAME__?.quiz?.title || 'This or That';
const LS_PLAYER_KEY = `tot_game_${sessionId}_player`;

let myName = new URLSearchParams(location.search).get('player')
  || localStorage.getItem(LS_PLAYER_KEY) || '';

if (!myName) {
  // No identity for this game -> the join page asks for a name
  location.replace(`/join/${sessionId}`);
  throw new Error('redirecting to join');
}
localStorage.setItem(LS_PLAYER_KEY, myName);

/* ── state ────────────────────────────────────────────────────── */
let G = null;                 // latest public_state from the server
let localIndex = 0;           // my current question (optimistic, >= server)
let stack = null;
let stackBuilt = false;
let currentScreen = null;
let refreshing = false;

const $ = sel => document.querySelector(sel);
const total = () => G ? G.questions.length : 0;
const myCount = () => Math.max(localIndex,
  G?.me ? Number(Object.keys(G.my_answers).length) : 0);

/* ── api ──────────────────────────────────────────────────────── */
async function api(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    G = await api('GET', `/api/game/${sessionId}?player=${encodeURIComponent(myName)}`);
    render();
  } catch (e) {
    console.warn('state refresh failed:', e.message);
  } finally {
    refreshing = false;
  }
}

/* ── rendering: one function decides the screen ───────────────── */
function render() {
  if (!G) return;

  let target;
  if (G.phase === 'lobby') target = 'lobby';
  else if (G.phase === 'results') target = 'results';
  else if (G.me?.completed && G.mode === 'duo') target = 'waiting';
  else target = 'playing';

  if (target !== currentScreen) {
    switchScreen(target);
    if (target === 'lobby') buildLobby();
    if (target === 'playing') buildPlaying();
    if (target === 'waiting') buildWaiting();
    if (target === 'results') buildResults();
  }

  // granular updates (same screen)
  $('#quiz-title').textContent = G.quiz.title;
  $('#total-questions').textContent = total();
  $('#current-question').textContent = Math.min(myCount() + 1, Math.max(total(), 1));
  $('#progress-fill').style.width = `${total() ? (myCount() / total()) * 100 : 0}%`;

  if (target === 'lobby') updateLobby();
  if (target === 'playing') updatePlaying();
  if (target === 'waiting') updateWaiting();
  if (target === 'results') updateResults();

  // the header status area must not leak stale playing-phase text
  if (target === 'results') {
    const names = G.players.map(p => p.name);
    $('#status-line').textContent = G.opponent
      ? names.join(' & ') : `Nice game, ${G.me?.name ?? myName}!`;
    $('#opponent-progress').textContent = '';
  } else if (target === 'waiting') {
    $('#status-line').textContent = G.me?.name ?? myName;
  }
}

function switchScreen(name) {
  currentScreen = name;
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  $(`#screen-${name}`)?.classList.add('active');
  $('#counter-wrap')?.classList.toggle('active', name === 'playing');
}

/* ── lobby ────────────────────────────────────────────────────── */
function buildLobby() { /* static markup already in the page */ }

function updateLobby() {
  const ul = $('#lobby-players');
  ul.innerHTML = G.players.map(p => {
    const tag = p.connected === false
      ? '<span class="tag away">away</span>'
      : (p.ready ? '<span class="tag ok">ready</span>'
                 : '<span class="tag wait">waiting</span>');
    return `<li><span>${esc(p.name)}${p.name === G.me?.name ? ' (you)' : ''}</span>${tag}</li>`;
  }).join('');

  $('#invite-link').value = `${location.origin}${G.invite_path}`;

  const soloOk = G.players.length === 1;
  $('#btn-solo').style.display = soloOk ? '' : 'none';
  $('#btn-ready').style.display = (!soloOk && !G.me?.ready) ? '' : 'none';

  const hint = soloOk
    ? 'Play solo now — or share the link first to play together.'
    : (G.me?.ready
        ? 'Waiting for your opponent to hit ready…'
        : 'Both players must be ready to start.');
  $('#lobby-hint').textContent = hint;

  $('#status-line').innerHTML = soloOk
    ? 'Solo game'
    : `<span style="color:#4caf50">${esc(G.players.map(p => p.name).join(' & '))}</span>`;
}

window.startSolo = async () => {
  try { await api('POST', `/api/game/${sessionId}/solo`, { player_name: myName }); }
  catch (e) { toast(e.message, 'error'); }
  await refresh();
};

window.signalReady = async () => {
  try { await api('POST', `/api/game/${sessionId}/ready`, { player_name: myName }); }
  catch (e) { toast(e.message, 'error'); }
  await refresh();
};

window.copyInvite = () => copyText(`${location.origin}${G.invite_path}`);
window.shareInvite = () => {
  const url = `${location.origin}${G.invite_path}`;
  const text = `🎮 Play "${G.quiz.title}" with me!`;
  if (navigator.share) navigator.share({ title: G.quiz.title, text, url }).catch(() => copyText(url));
  else copyText(url);
};

/* ── playing ──────────────────────────────────────────────────── */
function buildPlaying() {
  if (!stackBuilt) {
    buildCardDOM();
    const reduceMotion = matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    stack = new CardStack('#card-stack', {
      throwOutDuration: reduceMotion ? 60 : 300,
      snapBackDuration: reduceMotion ? 60 : 300,
      onSwipeLeft: () => handleSwipe('left'),
      onSwipeRight: () => handleSwipe('right'),
      onCardThrown: () => moveToNext(),
    });
    $('#reject-btn').onclick = () => stack.throwCurrentCard('left');
    $('#like-btn').onclick = () => stack.throwCurrentCard('right');
    $('#undo-btn').onclick = undoLast;
    stackBuilt = true;
    showHintOnce();
    fitOptionTexts();
  }
}

function buildCardDOM() {
  const host = $('#card-stack');
  host.innerHTML = '';
  // natural order: cards[0] === question 0 (updateCardPositions sets z-index
  // explicitly, so DOM order doesn't affect stacking)
  G.questions.forEach((q, idx) => {
    const card = document.createElement('div');
    card.className = 'tinder-card';
    card.dataset.questionIndex = idx;
    const [l1, l2] = optionLabels(q);
    card.innerHTML = `
      <div class="choice-overlay left">NOPE</div>
      <div class="choice-overlay right">LIKE</div>
      <div class="card-content">
        <div class="question-prompt">${esc(q.prompt)}</div>
        <div class="options-container">
          <div class="option option-left"><div class="option-text">${esc(l1)}</div></div>
          <div class="vs-indicator">VS</div>
          <div class="option option-right"><div class="option-text">${esc(l2)}</div></div>
        </div>
      </div>`;
    host.appendChild(card);
  });
}

function optionLabels(q) {
  // player-type quizzes label the two sides with the actual player names
  if (G.quiz.type === 'player' && G.players.length === 2 &&
      /Player [12]/.test(q.option1 + q.option2)) {
    return [G.players[0].name, G.players[1].name];
  }
  return [q.option1, q.option2];
}

function updatePlaying() {
  // keep the visual stack locked to progress: syncTo is idempotent, so
  // calling it on every render self-heals any drift (mid-throw races,
  // restored sessions, anything)
  if (stack && !stack.dragging) stack.syncTo(localIndex);
  $('#undo-btn').disabled = !(localIndex > 0 && G.my_answers[String(localIndex - 1)]);
  updateOpponentPill();
}

function updateOpponentPill() {
  const line = $('#status-line');
  const pill = $('#opponent-progress');
  if (G.mode === 'solo' || !G.opponent) {
    line.textContent = `${G.me?.name ?? myName} is playing`;
    pill.textContent = '';
    return;
  }
  const conn = G.opponent.connected === false ? ' (away)' : '';
  line.innerHTML = `<span style="color:#4caf50">${esc(G.opponent.name)}${conn}</span>`;
  pill.textContent = `${G.opponent.name}: ${G.opponent.progress}/${G.opponent.total} answered`;
}

async function handleSwipe(direction) {
  const idx = localIndex;
  const q = G?.questions[idx];
  if (!q) return;
  if (navigator.vibrate) { try { navigator.vibrate(8); } catch {} }

  let playerChoice = null;
  if (G.quiz.type === 'player') {
    const [l1, l2] = optionLabels(q);
    playerChoice = direction === 'left' ? l1 : l2;
  }

  try {
    const res = await api('POST', `/api/game/${sessionId}/answer`, {
      player_name: myName, question_index: idx,
      answer: direction, player_choice: playerChoice,
    });
    if (res.phase === 'results') await refresh();
  } catch (e) {
    console.warn('answer failed, will retry:', e.message);
    queueAnswer(idx, direction, playerChoice);
  }
}

const retryQueue = new Map();   // idx -> {direction, playerChoice}
function queueAnswer(idx, direction, playerChoice) {
  retryQueue.set(idx, { direction, playerChoice });
}
async function flushRetries() {
  for (const [idx, { direction, playerChoice }] of [...retryQueue.entries()]) {
    try {
      await api('POST', `/api/game/${sessionId}/answer`, {
        player_name: myName, question_index: idx,
        answer: direction, player_choice: playerChoice,
      });
      retryQueue.delete(idx);
    } catch { break; }
  }
}

function moveToNext() {
  localIndex++;
  try { stack?._trace(`moveToNext -> local ${localIndex}`); } catch {}
  render();
  if (localIndex >= total()) {
    // finished: server decides results vs waiting
    refresh();
  }
}

async function undoLast() {
  const idx = localIndex - 1;
  if (idx < 0) return;
  try {
    await api('DELETE',
      `/api/game/${sessionId}/answer?player_name=${encodeURIComponent(myName)}&question_index=${idx}`);
    localIndex = idx;
    stack?.restoreTo(idx);
    render();
  } catch (e) { toast(e.message, 'error'); }
}

function showHintOnce() {
  if (localStorage.getItem('tot_swipe_hint_seen') === '1') return;
  const hint = document.createElement('div');
  hint.className = 'swipe-hint';
  hint.innerHTML = `
    <span class="hint-arrow left">‹</span>
    <span class="hint-label">Swipe or tap a side to choose</span>
    <span class="hint-arrow right">›</span>`;
  $('#card-stack').appendChild(hint);
  const off = () => { hint.remove(); localStorage.setItem('tot_swipe_hint_seen', '1'); };
  $('#card-stack').addEventListener('pointerdown', off, { once: true, capture: true });
  setTimeout(off, 8000);
}

function fitOptionTexts() {
  document.querySelectorAll('.option-text').forEach(el => {
    const len = (el.textContent || '').trim().length;
    el.classList.toggle('long', len > 16 && len <= 28);
    el.classList.toggle('very-long', len > 28);
  });
}

// keyboard controls (desktop)
document.addEventListener('keydown', e => {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
  if (currentScreen !== 'playing' || !stack) return;
  stack.throwCurrentCard(e.key === 'ArrowLeft' ? 'left' : 'right');
});

/* ── waiting (duo: done, opponent isn't) ───────────────────────── */
function buildWaiting() { /* static markup */ }

function updateWaiting() {
  const o = G.opponent;
  $('#waiting-text').textContent = o
    ? `Waiting for ${o.name} to finish…` : 'Waiting for your opponent…';
  if (o) {
    const pct = o.total ? Math.round(o.progress / o.total * 100) : 0;
    $('#friend-progress').innerHTML = `
      <div style="color:#666;margin-bottom:.4rem">${esc(o.name)}: ${o.progress}/${o.total}</div>
      <div style="max-width:240px;height:8px;background:#e0e0e0;border-radius:4px;margin:0 auto">
        <div style="width:${pct}%;height:100%;background:#4caf50;border-radius:4px;transition:width .3s"></div>
      </div>`;
  }
}

/* ── results ───────────────────────────────────────────────────── */
const RING_C = 2 * Math.PI * 62;   // ring circumference (r=62)

function matchVerdict(pct) {
  if (pct >= 80) return 'Practically soulmates 💞';
  if (pct >= 60) return 'Beautifully in sync ✨';
  if (pct >= 40) return 'You keep it interesting 🌀';
  if (pct >= 20) return 'Opposites attract 🧲';
  return 'Agree to disagree 🙃';
}

function heroHTML(R) {
  if (R.kind === 'solo') {
    const done = R.summary.answered === R.summary.total;
    return `
      <div class="res-hero">
        <div class="hero-emoji">${done ? '🎉' : '📝'}</div>
        <div class="hero-title">${done ? 'You finished!' : 'Your choices'}</div>
        <div class="hero-sub">${esc(G.quiz.title)}</div>
      </div>`;
  }
  if (R.kind === 'match') {
    const pct = R.summary.compatibility;
    return `
      <div class="res-hero">
        <div class="ring-wrap">
          <svg viewBox="0 0 148 148">
            <circle class="ring-bg" cx="74" cy="74" r="62"></circle>
            <circle class="ring-fill" id="ring-fill" cx="74" cy="74" r="62"
              stroke-dasharray="${RING_C.toFixed(1)}" stroke-dashoffset="${RING_C.toFixed(1)}"></circle>
          </svg>
          <div class="ring-label">
            <div class="pct">${pct}<small>%</small></div>
            <div class="cap">💘 match</div>
          </div>
        </div>
        <div class="hero-title">${matchVerdict(pct)}</div>
        <div class="hero-sub">${R.summary.matches} of ${R.summary.total} answers in common</div>
      </div>`;
  }
  // competition
  const entries = Object.entries(R.summary.scores);
  const [aName, aScore] = entries[0];
  const [bName, bScore] = entries[1] || ['', 0];
  const tie = aScore === bScore;
  const winner = tie ? 'It’s a tie!' : `${aScore > bScore ? aName : bName} wins!`;
  return `
    <div class="res-hero warm">
      <div class="hero-emoji">${tie ? '🤝' : '🏆'}</div>
      <div class="hero-title">${esc(winner)}</div>
      <div class="score-chips">
        <div class="score-chip"><div class="sc-name">${esc(aName)}</div><div class="sc-val">${aScore}</div></div>
        <div class="score-chip"><div class="sc-name">${esc(bName)}</div><div class="sc-val">${bScore}</div></div>
      </div>
    </div>`;
}

function statsHTML(R) {
  if (R.kind === 'solo') {
    const answers = Object.entries(G.my_answers);
    const left = answers.filter(([, a]) => a.choice === 'left').length;
    const right = answers.length - left;
    const lean = left === right ? 'Perfectly balanced' : (left > right ? 'Left leaning' : 'Right leaning');
    return `
      <div class="res-stats">
        <div class="stat-tile"><div class="stat-num">${R.summary.answered}/${R.summary.total}</div><div class="stat-lbl">answered</div></div>
        <div class="stat-tile"><div class="stat-num">${left}</div><div class="stat-lbl">left picks</div></div>
        <div class="stat-tile"><div class="stat-num">${right}</div><div class="stat-lbl">right picks</div></div>
      </div>
      <p style="text-align:center;color:#888;font-size:.85rem;margin:-0.3rem 0 .8rem">${lean} ⚖️</p>`;
  }
  if (R.kind === 'match') {
    const s = R.summary;
    return `
      <div class="res-stats">
        <div class="stat-tile"><div class="stat-num">${s.matches}</div><div class="stat-lbl">in common</div></div>
        <div class="stat-tile"><div class="stat-num">${s.total - s.matches}</div><div class="stat-lbl">different</div></div>
        <div class="stat-tile"><div class="stat-num">${s.total}</div><div class="stat-lbl">questions</div></div>
      </div>`;
  }
  const scores = Object.values(R.summary.scores);
  const best = Math.max(...scores);
  const bothRight = R.questions.filter(q => q.status === 'both_correct').length;
  return `
    <div class="res-stats">
      <div class="stat-tile"><div class="stat-num">${best}</div><div class="stat-lbl">best score</div></div>
      <div class="stat-tile"><div class="stat-num">${bothRight}</div><div class="stat-lbl">both right</div></div>
      <div class="stat-tile"><div class="stat-num">${G.questions.length}</div><div class="stat-lbl">questions</div></div>
    </div>`;
}

function rxButtons(idx) {
  return ['clap', 'haha', 'bruh'].map(r =>
    `<button class="emoji-btn" data-react="${r}" data-idx="${idx}" title="${r}">${reactionEmoji(r)}</button>`).join('');
}

function rxReceived(idx) {
  const rx = (G.reactions || {})[String(idx)] || [];
  if (!rx.length) return '';
  return `<div class="rx-got">${rx.map(r =>
    `<span title="${esc(r.from)}">${reactionEmoji(r.reaction)}</span>`).join('')}</div>`;
}

function resultsRowsHTML(R) {
  if (R.kind === 'solo') {
    return R.questions.map((q, i) => {
      const entry = G.my_answers[String(i)];
      const side = entry?.choice || 'left';
      return `
        <div class="q-row-card" style="animation-delay:${i * 50}ms">
          <div class="q-head"><span class="q-num">${i + 1}</span>
            <span class="q-prompt">${esc(q.prompt)}</span></div>
          <div class="solo-pick ${side}">${esc(entry ? q.my_display : '— skipped —')}</div>
        </div>`;
    }).join('');
  }

  const comp = R.kind === 'competition';
  return R.questions.map((q, i) => {
    let orb = q.status === 'match' ? '💚' : '🧡';
    let aCls = 'a', bCls = 'b';
    if (comp) {
      orb = q.status === 'both_wrong' ? '😐' : '⚡';
      aCls += q.status === 'a_correct' || q.status === 'both_correct' ? ' win' : ' fail';
      bCls += q.status === 'b_correct' || q.status === 'both_correct' ? ' win' : ' fail';
    }
    const aMark = comp ? `<span class="mark">${aCls.includes('win') ? '✅' : '❌'}</span>` : '';
    const bMark = comp ? `<span class="mark">${bCls.includes('win') ? '✅' : '❌'}</span>` : '';
    return `
      <div class="q-row-card" style="animation-delay:${i * 50}ms">
        <div class="q-head"><span class="q-num">${i + 1}</span>
          <span class="q-prompt">${esc(q.prompt)}</span></div>
        <div class="vs-choices">
          <div class="pick ${aCls}">${aMark}<div class="who">${esc(q.a_name)}</div>
            <div class="what">${esc(q.a_display)}</div></div>
          <div class="vs-orb">${orb}</div>
          <div class="pick ${bCls}">${bMark}<div class="who">${esc(q.b_name)}</div>
            <div class="what">${esc(q.b_display)}</div></div>
        </div>
        <div class="rx-row">
          <div class="rx-got-wrap" data-idx="${q.index}">${rxReceived(q.index)}</div>
          <div class="spacer"></div>
          ${rxButtons(q.index)}
        </div>
      </div>`;
  }).join('');
}

function buildResults() {
  const R = G.results;
  const panel = $('#results-panel');
  if (!R) { panel.innerHTML = ''; return; }

  panel.classList.add('animate');
  panel.innerHTML = heroHTML(R) + statsHTML(R) + resultsRowsHTML(R);
  // let the staggered entrance finish, then drop the class so later
  // rebuilds (new reactions) don't replay it
  setTimeout(() => panel.classList.remove('animate'), R.questions.length * 50 + 600);

  // animate the match ring to its final value
  if (R.kind === 'match') {
    const fill = panel.querySelector('#ring-fill');
    const target = RING_C * (1 - R.summary.compatibility / 100);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (fill) fill.style.strokeDashoffset = target.toFixed(1);
    }));
  }

  // reaction buttons (duo only)
  panel.querySelectorAll('[data-react]').forEach(btn => {
    btn.onclick = () => api('POST', `/api/game/${sessionId}/reaction`, {
      player_name: myName,
      question_index: Number(btn.dataset.idx),
      reaction: btn.dataset.react,
    }).catch(e => toast(e.message, 'error'));
  });

  $('#chat-box').style.display = G.opponent ? '' : 'none';
  renderChat();
}

const reactionEmoji = r => ({ clap: '👏', haha: '😂', bruh: '😑' }[r] || '👍');

/* light-weight updates while already on the results screen */
function updateResults() {
  renderChat();
  // refresh received-reaction chips without rebuilding the panel
  document.querySelectorAll('.rx-got-wrap').forEach(wrap => {
    const html = rxReceived(Number(wrap.dataset.idx));
    if (wrap.innerHTML !== html) wrap.innerHTML = html;
  });
}

function renderChat() {
  const box = $('#chat-messages');
  if (!G.chat.length) {
    box.innerHTML = '<div style="color:#999;font-size:.85rem;text-align:center;margin:.4rem 0">No messages yet</div>';
    return;
  }
  box.innerHTML = G.chat.map(m => `
    <div class="chat-line ${m.from === myName ? 'mine' : ''}">
      <div class="who">${esc(m.from)}</div>
      <div class="bubble">${esc(m.message)}</div>
    </div>`).join('');
  box.scrollTop = box.scrollHeight;
}

window.sendChat = async () => {
  const input = $('#chat-input');
  const message = input.value.trim();
  if (!message) return;
  input.value = '';
  try { await api('POST', `/api/game/${sessionId}/chat`, { player_name: myName, message }); }
  catch (e) { toast(e.message, 'error'); }
  await refresh();
};
$('#chat-input')?.addEventListener('keydown', e => { if (e.key === 'Enter') window.sendChat(); });

window.rematch = async () => {
  try {
    const r = await api('POST', `/api/game/${sessionId}/rematch`, { player_name: myName });
    location.href = `/game/${r.session_id}?player=${encodeURIComponent(myName)}`;
  } catch (e) { toast(e.message, 'error'); }
};

window.shareResultsImage = async () => {
  const node = $('#results-panel');
  if (!node) return;
  const btn = $('#share-results-btn');
  btn.disabled = true;
  try {
    const canvas = await html2canvas(node, { backgroundColor: '#fff', scale: 2 });
    const blob = await new Promise(res => canvas.toBlob(res, 'image/png'));
    const file = new File([blob], `quiz_results_${sessionId.slice(0, 6)}.png`, { type: 'image/png' });
    if (navigator.canShare?.({ files: [file] })) {
      await navigator.share({ title: `Results – ${quizTitle}`, files: [file] });
    } else {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = file.name;
      a.click();
      URL.revokeObjectURL(a.href);
    }
  } catch { toast('Could not create image', 'error'); }
  finally { btn.disabled = false; }
};

/* ── websocket: notification bus ──────────────────────────────── */
let ws = null, wsDelay = 500, pingTimer = null;

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/${sessionId}/${encodeURIComponent(myName)}`);

  ws.onopen = () => {
    wsDelay = 500;
    pingTimer = setInterval(() => ws.send(JSON.stringify({ type: 'ping' })), 15000);
    refresh();
  };
  ws.onmessage = ev => {
    let msg; try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.type === 'state') refresh();
    else if (msg.type === 'rematch' && msg.data?.session_id) {
      location.href = `/game/${msg.data.session_id}?player=${encodeURIComponent(myName)}`;
    }
  };
  ws.onclose = () => {
    clearInterval(pingTimer);
    wsDelay = Math.min(wsDelay * 2, 15000);
    setTimeout(connectWS, wsDelay + Math.random() * 500);
  };
}

window.addEventListener('online', () => { flushRetries(); refresh(); });
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && ws?.readyState !== WebSocket.OPEN) { flushRetries(); refresh(); }
});

/* ── small helpers ────────────────────────────────────────────── */
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function toast(msg, type = 'info', ms = 3000) {
  let wrap = $('#toast-wrap');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.id = 'toast-wrap';
    wrap.style.cssText = 'position:fixed;top:16px;right:16px;z-index:9999';
    document.body.appendChild(wrap);
  }
  const n = document.createElement('div');
  n.textContent = msg;
  n.style.cssText = `margin-bottom:8px;padding:10px 16px;border-radius:8px;color:#fff;
    background:${{ success: '#4caf50', error: '#f44336', info: '#2196f3' }[type] || '#2196f3'};
    box-shadow:0 2px 8px rgba(0,0,0,.2);cursor:pointer`;
  n.onclick = () => n.remove();
  wrap.appendChild(n);
  setTimeout(() => { n.style.opacity = '0'; setTimeout(() => n.remove(), 300); }, ms);
}
function copyText(text) {
  navigator.clipboard?.writeText(text)
    .then(() => toast('Link copied!', 'success'))
    .catch(() => toast('Could not copy', 'error'));
}

/* ── boot ─────────────────────────────────────────────────────── */
function recordPlayedQuestionIds() {
  const ids = (G?.questions || []).map(q => q?.id).filter(Boolean);
  if (!ids.length) return;
  try {
    const prev = JSON.parse(localStorage.getItem('tot_recent_question_ids') || '[]');
    const merged = [...new Set([...ids, ...prev])].slice(0, 400);
    localStorage.setItem('tot_recent_question_ids', JSON.stringify(merged));
  } catch {}
}

(async () => {
  G = window.__GAME__;
  if (!G) await refresh();
  localIndex = G?.me ? Number(Object.keys(G.my_answers).length) : 0;
  recordPlayedQuestionIds();
  render();
  connectWS();
  setInterval(refresh, 60000);   // safety net: full resync every minute
})();

// small debug handle for tests / console forensics
window.__gameDebug = {
  get stack() { return stack; },
  get localIndex() { return localIndex; },
  get state() { return G; },
  get screen() { return currentScreen; },
  get retries() { return [...retryQueue.entries()]; },
  get engineLog() { return stack ? stack._log : null; },
};
