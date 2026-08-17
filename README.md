# This or That 💑

A swipe-based quiz game for couples and friends. Solo play or two-player
match-up with live progress, results comparison, reactions and chat.

## Run it

```bash
pip install -r requirements.txt
python run.py            # http://localhost:2000
```

Or with Docker: `docker compose up --build`

## Architecture (v3, clean rebuild)

The server owns the truth; the client renders state.

```
app.py            FastAPI assembly: pages, routers, static, lifespan
store.py          Session storage (diskcache, sliding TTL, deep copies)
game.py           The game: phase machine (lobby → playing → results),
                  answer maps, server-computed results, public_state()
routes_game.py    /api/game/* endpoints + WebSocket notification bus
routes_quiz.py    Question bank, dynamic quizzes, admin/LLM authoring
llm.py            AI question generation, name suggestions, image import
quizlib.py        Quiz file loading/saving (quizzes/*.json)
question_database.py + question_seed_*.py + populate_question_db.py
                  The 1,669-question bank (16 categories, couples-heavy)

static/game.js    The play page: fetch state → render(state). One render
                  function, four screens. WS messages just trigger refetch.
static/home.js    Landing page: daily / categories / saved quizzes / join
static/admin.js   Quiz builder: manual editing, AI generation, image import
static/card_stack_system.js
                  Swipe engine: pointer events, relative thresholds,
                  flick detection, tap-to-answer, undo support
```

### Key design rules

- **One state contract.** `GET /api/game/{sid}?player=NAME` returns
  everything the client renders. The WebSocket is a *notification bus*
  (`{"type": "state"}`) — no business logic in WS handlers.
- **One answer format.** `players[name].answers = {question_index: entry}`
  — a map, not an array. No holes, no dual formats, dedup for free.
- **Results are computed server-side** (solo list / match % / competition
  scores) — the client never re-derives game outcomes.
- **Sessions survive** refreshes, reconnects and server restarts (disk
  persistence + sliding TTL + 20s disconnect grace).

## Configuration (environment)

| Variable | Default | Purpose |
|---|---|---|
| `DEEPINFRA_API_KEY` | – | AI question generation (admin page) |
| `DEEPINFRA_BASE_URL` | DeepInfra | OpenAI-compatible endpoint |
| `LLM_MODEL` | `google/gemma-3-27b-it` | Model for generation |
| `ADMIN_TOKEN` | `malenanacir` | Unlocks the quiz builder |
| `SESSION_TTL` | `21600` | Session lifetime (seconds, sliding) |
| `SESSION_STORAGE_DIR` | `session_storage` | Where sessions live |

## Question bank

`python3 populate_question_db.py` rebuilds/extends `questions_db.json`
from the seed files. Questions carry ids; the browser remembers recently
played ones and the server avoids repeating them (with graceful overlap
when a category runs low).
