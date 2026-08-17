/* admin.js — the quiz builder.
 *
 * A plain list of question objects; AI/image generation appends to it;
 * save posts the whole thing to /api/create_quiz.
 */

let token = localStorage.getItem('tot_admin_token') || '';
let questions = [];

const $ = sel => document.querySelector(sel);

async function api(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`);
  return data;
}

/* ── token gate ───────────────────────────────────────────────── */
async function tryUnlock(tok) {
  const d = await api('POST', `/api/validate-admin-token?token=${encodeURIComponent(tok)}`);
  if (!d.success) throw new Error('Wrong token');
  token = tok;
  localStorage.setItem('tot_admin_token', tok);
  $('#token-card').style.display = 'none';
  $('#builder').style.display = '';
}
$('#token-btn').onclick = async () => {
  const tok = $('#token-input').value.trim();
  if (!tok) return;
  try { await tryUnlock(tok); }
  catch (e) { $('#token-error').textContent = e.message; }
};
$('#token-input').addEventListener('keydown', e => { if (e.key === 'Enter') $('#token-btn').click(); });
if (token) tryUnlock(token).catch(() => { localStorage.removeItem('tot_admin_token'); token = ''; });

/* ── question list rendering ───────────────────────────────────── */
function renderQuestions() {
  const list = $('#question-list');
  $('#q-count').textContent = questions.length;
  if (!questions.length) {
    list.innerHTML = '<p style="color:#999;text-align:center;padding:1rem">No questions yet — generate some with AI or add your own.</p>';
    return;
  }
  const type = $('#quiz-type').value;
  list.innerHTML = questions.map((q, i) => `
    <div class="q-card" data-i="${i}">
      <div class="q-row">
        <span style="color:#999;font-size:.8rem;width:1.4rem">${i + 1}.</span>
        <input class="fld" data-f="prompt" value="${escAttr(q.prompt)}" placeholder="Question prompt">
      </div>
      <div class="q-row">
        <input class="fld" data-f="option1" value="${escAttr(q.option1)}" placeholder="Option 1 (left)">
        <input class="fld" data-f="option2" value="${escAttr(q.option2)}" placeholder="Option 2 (right)">
        ${type === 'competition' ? `
          <select class="fld" data-f="correct_answer" style="width:130px">
            <option value="">Correct…</option>
            <option value="option1" ${q.correct_answer === 'option1' ? 'selected' : ''}>Option 1</option>
            <option value="option2" ${q.correct_answer === 'option2' ? 'selected' : ''}>Option 2</option>
          </select>` : ''}
      </div>
      <div class="q-actions">
        <button title="Move up" onclick="window.moveQ(${i}, -1)">⬆️</button>
        <button title="Move down" onclick="window.moveQ(${i}, 1)">⬇️</button>
        <button title="Remove" onclick="window.removeQ(${i})">🗑️</button>
      </div>
    </div>`).join('');

  // live-edit the model from the inputs
  list.querySelectorAll('.q-card').forEach(card => {
    const i = Number(card.dataset.i);
    card.querySelectorAll('[data-f]').forEach(inp => {
      inp.addEventListener('input', () => {
        questions[i][inp.dataset.f] = inp.dataset.f === 'correct_answer'
          ? (inp.value || undefined) : inp.value;
      });
      if (inp.tagName === 'SELECT') inp.addEventListener('change', () => {
        questions[i][inp.dataset.f] = inp.value || undefined;
      });
    });
  });
}

window.addQuestion = () => {
  questions.push({ prompt: '', option1: '', option2: '',
                   ...(quizType() === 'competition' ? { correct_answer: 'option1' } : {}) });
  renderQuestions();
  const cards = document.querySelectorAll('.q-card');
  cards[cards.length - 1]?.querySelector('[data-f="prompt"]')?.focus();
};
window.removeQ = (i) => { questions.splice(i, 1); renderQuestions(); };
window.moveQ = (i, dir) => {
  const j = i + dir;
  if (j < 0 || j >= questions.length) return;
  [questions[i], questions[j]] = [questions[j], questions[i]];
  renderQuestions();
};
$('#quiz-type').addEventListener('change', renderQuestions);
const quizType = () => $('#quiz-type').value;

/* ── AI helpers ────────────────────────────────────────────────── */
const status = (msg, ok = true) => {
  $('#gen-status').textContent = msg;
  $('#gen-status').style.color = ok ? '#888' : '#f44336';
};

window.generate = async () => {
  const topic = $('#gen-topic').value.trim();
  if (!topic) { status('Enter a topic first', false); return; }
  const count = Number($('#gen-count').value);
  status(`Generating ${count} question${count > 1 ? 's' : ''}…`);
  try {
    const d = await api('POST', '/api/generate_question', {
      topic, quiz_type: quizType(), count,
      avoid: questions.slice(-5).map(q => q.prompt).filter(Boolean),
    });
    questions.push(...d.questions);
    renderQuestions();
    status(`Added ${d.count} question${d.count > 1 ? 's' : ''} ✨`);
  } catch (e) { status(e.message, false); }
};

window.uploadImage = async (input) => {
  const file = input.files?.[0];
  if (!file) return;
  status('Reading image…');
  const form = new FormData();
  form.append('file', file);
  try {
    const r = await fetch('/api/upload_image', { method: 'POST', body: form });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Upload failed');
    questions.push(...d.questions);
    renderQuestions();
    status(`Imported ${d.questions.length} questions from image 🖼️`);
  } catch (e) { status(e.message, false); }
  input.value = '';
};

window.suggestName = async () => {
  const ctx = questions.map(q => q.prompt).slice(0, 3).join(', ')
    || $('#gen-topic').value.trim();
  if (!ctx) { status('Add a question or topic first', false); return; }
  status('Thinking of a name…');
  try {
    const d = await api('POST',
      `/api/suggest_quiz_name?context=${encodeURIComponent(ctx)}&quiz_type=${quizType()}`);
    $('#quiz-title').value = d.suggested_name;
    status('');
  } catch (e) { status(e.message, false); }
};

/* ── save ──────────────────────────────────────────────────────── */
window.saveQuiz = async () => {
  const title = $('#quiz-title').value.trim();
  if (!title) { status('Give the quiz a title first', false); return; }
  const valid = questions.filter(q => q.prompt.trim() && q.option1.trim() && q.option2.trim());
  if (!valid.length) { status('Add at least one complete question', false); return; }

  try {
    const d = await api('POST', '/api/create_quiz', {
      title, type: quizType(), questions: valid,
    });
    $('#save-result').innerHTML =
      `Saved! <a href="/?quiz=${d.quiz_id}" style="color:#42a5f5">Play it now →</a>`;
    status('');
  } catch (e) { status(e.message, false); }
};

/* ── helpers ───────────────────────────────────────────────────── */
function escAttr(s) {
  return String(s ?? '').replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

renderQuestions();
