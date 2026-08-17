/* home.js — the landing page.
 *
 * Pick a source (daily / category / saved quiz), make sure we know the
 * player's name, start a game, redirect. Join by link or code.
 * No quiz-selection state lives here longer than one click.
 */

/* ── player name ──────────────────────────────────────────────── */
const nameInput = document.getElementById('player-name');
const nameOk = document.getElementById('name-ok');

function storedName() {
  try {
    const d = JSON.parse(localStorage.getItem('playerData') || 'null');
    if (d && d.expires > Date.now()) return d.name;
  } catch {}
  return '';
}
function saveName(name) {
  try {
    localStorage.setItem('playerData', JSON.stringify(
      { name, expires: Date.now() + 86400000 * 30 }));
  } catch {}
}
nameInput.value = storedName();
nameInput.addEventListener('input', () => {
  saveName(nameInput.value.trim());
  nameOk.style.display = nameInput.value.trim() ? '' : 'none';
});
if (nameInput.value.trim()) nameOk.style.display = '';

function requireName() {
  let name = nameInput.value.trim();
  if (!name) {
    name = prompt("What's your name?")?.trim() || '';
    if (name) { nameInput.value = name; saveName(name); nameOk.style.display = ''; }
  }
  return name || null;
}

/* ── game start ───────────────────────────────────────────────── */
async function api(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

async function startQuiz(quizId) {
  const name = requireName();
  if (!name) { toast('Enter your name first'); return; }
  try {
    const g = await api('POST', '/api/game/start', { quiz_id: quizId, player_name: name });
    location.href = `${g.url}?player=${encodeURIComponent(name)}`;
  } catch (e) { toast(e.message, 'error'); }
}

window.startDaily = () => startQuiz('__daily__');

window.joinGame = async () => {
  const raw = document.getElementById('join-input').value.trim();
  if (!raw) { toast('Paste a game link or code'); return; }
  let sid = raw;
  const m = raw.match(/\/(?:join|game)\/([a-z0-9]+)/i);
  if (m) sid = m[1];
  try {
    // probe the game first so a bad link gives a friendly error
    await api('GET', `/api/game/${sid}`);
    location.href = `/join/${sid}`;
  } catch { toast('Game not found — check the link', 'error'); }
};

/* ── content loading ──────────────────────────────────────────── */
async function loadCategories() {
  const grid = document.getElementById('category-grid');
  try {
    const data = await api('GET', '/api/categories');
    grid.innerHTML = data.categories
      .filter(c => c.question_count > 0)
      .map(c => `
        <div class="home-tile" style="background:linear-gradient(135deg,#667eea,#764ba2)"
             onclick="window.startCategory('${c.id}')">
          <div class="tile-emoji">${c.emoji}</div>
          <div class="tile-title" style="font-size:.98rem">${esc(c.name)}</div>
          <div class="tile-sub">${c.question_count} questions</div>
        </div>`).join('');
  } catch {
    grid.innerHTML = '<p style="color:#f44336">Could not load categories</p>';
  }
}

window.startCategory = async (category) => {
  const name = requireName();
  if (!name) { toast('Enter your name first'); return; }
  let recentIds = [];
  try { recentIds = JSON.parse(localStorage.getItem('tot_recent_question_ids') || '[]'); } catch {}
  try {
    const r = await api('POST', '/api/create-dynamic-quiz', {
      category, question_count: 10, player_name: name, exclude_ids: recentIds,
    });
    await startQuiz(r.quiz_id);
  } catch (e) { toast(e.message, 'error'); }
};

async function loadQuizzes() {
  const list = document.getElementById('quiz-list');
  try {
    const quizzes = await api('GET', '/api/quizzes');
    if (!quizzes.length) {
      list.innerHTML = '<p style="color:#999;font-size:.9rem">No saved quizzes yet — create one from the admin page.</p>';
      return;
    }
    list.innerHTML = quizzes.slice(0, 20).map(q => `
      <div class="quiz-item" onclick="window.startSaved('${q.id}')">
        <div>
          <div class="qi-title">${esc(q.title)}</div>
          <div class="qi-meta">${q.type}</div>
        </div>
        <div class="qi-meta">${q.question_count} questions →</div>
      </div>`).join('');
  } catch {
    list.innerHTML = '<p style="color:#f44336">Could not load quizzes</p>';
  }
}
window.startSaved = startQuiz;

/* ── daily challenge needs a quiz id: create it server-side ───── */
// startDaily uses a sentinel; swap it for a real dynamic quiz
const _origStartQuiz = startQuiz;
startQuiz = async function (quizId) {
  if (quizId === '__daily__') {
    try {
      const r = await api('POST', '/api/create-dynamic-quiz', { category: 'daily' });
      quizId = r.quiz_id;
    } catch (e) { toast(e.message, 'error'); return; }
  }
  return _origStartQuiz(quizId);
};
window.startDaily = () => startQuiz('__daily__');
window.startSaved = startQuiz;

/* ── preselect (?quiz=ID deep link) ───────────────────────────── */
const preselect = window.__PRESELECT_QUIZ__;
if (preselect && /^[a-z0-9_-]+$/i.test(preselect)) startQuiz(preselect);

/* ── helpers ──────────────────────────────────────────────────── */
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function toast(msg, type = 'info') {
  let wrap = document.getElementById('toast-wrap');
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
  setTimeout(() => { n.style.opacity = '0'; setTimeout(() => n.remove(), 300); }, 3500);
}

loadCategories();
loadQuizzes();
