"""This or That — FastAPI app assembly.

Server-authoritative game state (game.py + store.py), thin routers,
templates for the three pages, static assets. Business logic lives in
game.py / llm.py / question_database.py — not here.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import llm
import config
import routes_game
import routes_quiz
from store import SessionStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory='templates')
store = SessionStore(ttl=config.SESSION_TTL)
routes_game.store = store   # share one store instance


@asynccontextmanager
async def lifespan(app: FastAPI):
    for d in ('quizzes', 'uploads', 'results'):
        os.makedirs(d, exist_ok=True)
    logger.info('This or That started')
    yield
    store.close()
    await llm.close()
    logger.info('This or That stopped')


app = FastAPI(title='This or That', version='3.0.0', lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'], allow_methods=['*'], allow_headers=['*'],
)

app.mount('/static', StaticFiles(directory='static'), name='static')

llm.configure(config.DEEPINFRA_API_KEY, config.DEEPINFRA_BASE_URL, config.LLM_MODEL)

app.include_router(routes_quiz.router)
app.include_router(routes_game.router)


# ── pages ───────────────────────────────────────────────────────────

@app.get('/', response_class=HTMLResponse)
async def home(request: Request, quiz: str = None):
    return templates.TemplateResponse('index.html', {
        'request': request,
        # str|None only — rendering Python None here once showed "None"
        # in JS and broke the home page
        'preselect_quiz_id': quiz or '',
    })


@app.get('/admin', response_class=HTMLResponse)
async def admin(request: Request):
    return templates.TemplateResponse('admin.html', {'request': request})


@app.get('/join/{session_id}', response_class=HTMLResponse)
async def join(request: Request, session_id: str):
    state = store.get(session_id)
    if state is None:
        return templates.TemplateResponse('join.html', {
            'request': request, 'session_id': session_id,
            'quiz_title': None, 'exists': False})
    return templates.TemplateResponse('join.html', {
        'request': request, 'session_id': session_id,
        'quiz_title': state['title'], 'exists': True})


@app.get('/game/{session_id}', response_class=HTMLResponse)
async def game_page(request: Request, session_id: str, player: str = None):
    state = store.get(session_id)
    if state is None:
        return templates.TemplateResponse('game.html', {
            'request': request, 'session_id': session_id,
            'game_json': 'null', 'player_name': player or ''})
    from game import public_state
    import json
    return templates.TemplateResponse('game.html', {
        'request': request, 'session_id': session_id,
        'game_json': json.dumps(public_state(state, player), default=str),
        'player_name': player or ''})


@app.get('/api/health')
async def health():
    return {'status': 'healthy'}
