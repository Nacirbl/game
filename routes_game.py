"""Game routes + the WebSocket notification bus.

Design rules:
- All game mutations go through game.py functions under a per-session lock.
- The WebSocket carries NO business logic: connections register themselves,
  every mutation broadcasts {"type": "state"}, clients refetch and render.
- Disconnects get a grace period before the player is marked away.
"""
import asyncio
import logging
import time
from collections import defaultdict
from typing import Dict, Optional, Set

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

import game
from quizlib import load_quiz

logger = logging.getLogger(__name__)
router = APIRouter()

# injected by app.py so the whole process shares one store instance
store = None

# per-session locks: serialize every read-modify-write
session_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

DISCONNECT_GRACE_SECONDS = 20


class StartGameRequest(BaseModel):
    quiz_id: str
    player_name: str = Field(min_length=1, max_length=50)


class JoinRequest(BaseModel):
    player_name: str = Field(min_length=1, max_length=50)


class ReadyRequest(BaseModel):
    player_name: str


class AnswerRequest(BaseModel):
    player_name: str
    question_index: int = Field(ge=0)
    answer: str  # 'left' | 'right'
    player_choice: Optional[str] = None


class ReactionRequest(BaseModel):
    player_name: str
    question_index: int = Field(ge=0)
    reaction: str = Field(min_length=1, max_length=20)


class ChatRequest(BaseModel):
    player_name: str
    message: str = Field(min_length=1, max_length=100)


class RematchRequest(BaseModel):
    player_name: str


# ── connection registry (notification bus) ──────────────────────────

class Connections:
    """WebSockets grouped by session; one player may hold several sockets."""
    def __init__(self):
        self.by_session: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.names: Dict[WebSocket, tuple] = {}   # ws -> (session_id, player)
        self.pending_removals: Dict[str, asyncio.Task] = {}

    def add(self, ws: WebSocket, session_id: str, player: str):
        self.by_session[session_id].add(ws)
        self.names[ws] = (session_id, player)
        key = f'{session_id}:{player}'
        task = self.pending_removals.pop(key, None)
        if task:
            task.cancel()

    def drop(self, ws: WebSocket):
        entry = self.names.pop(ws, None)
        if not entry:
            return None
        session_id, player = entry
        socks = self.by_session.get(session_id)
        if socks:
            socks.discard(ws)
            if not socks:
                self.by_session.pop(session_id, None)
        return entry

    def sockets_for(self, session_id: str):
        return list(self.by_session.get(session_id, ()))

    def count_for_player(self, session_id: str, player: str) -> int:
        return sum(1 for sid, name in self.names.values()
                   if sid == session_id and name == player)


connections = Connections()


async def notify(session_id: str, message: dict = None):
    """Push a lightweight notification; clients respond by refetching state."""
    payload = message or {'type': 'state'}
    dead = []
    for ws in connections.sockets_for(session_id):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connections.drop(ws)


async def _mutate(session_id: str, fn):
    """Lock, load, apply, persist, notify. Returns the resulting session."""
    async with session_locks[session_id]:
        state = store.get(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail='Game not found')
        try:
            state = fn(state)
        except game.GameError as e:
            raise HTTPException(status_code=e.status, detail=str(e))
        store.put(session_id, state)
    await notify(session_id)
    return state


# ── REST endpoints ──────────────────────────────────────────────────

@router.post('/api/game/start')
async def start_game(req: StartGameRequest):
    quiz = load_quiz(req.quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail='Quiz not found')
    state = game.create_session(quiz, req.player_name.strip())
    store.put(state['id'], state)
    return {'session_id': state['id'], 'url': f"/game/{state['id']}"}


@router.post('/api/game/{session_id}/join')
async def join_game(session_id: str, req: JoinRequest):
    state = await _mutate(session_id, lambda s: game.join(s, req.player_name.strip()))
    return {'session_id': session_id, 'url': f"/game/{session_id}",
            'player_name': req.player_name.strip()}


@router.post('/api/game/{session_id}/solo')
async def start_solo(session_id: str, req: ReadyRequest):
    await _mutate(session_id, lambda s: game.start_solo(s, req.player_name))
    return {'success': True}


@router.post('/api/game/{session_id}/ready')
async def set_ready(session_id: str, req: ReadyRequest):
    state = await _mutate(session_id, lambda s: game.set_ready(s, req.player_name))
    return {'success': True, 'phase': state['phase']}


@router.post('/api/game/{session_id}/answer')
async def submit_answer(session_id: str, req: AnswerRequest):
    state = await _mutate(session_id, lambda s: game.apply_answer(
        s, req.player_name, req.question_index, req.answer, req.player_choice))
    me = next((p for p in state['players'] if p['name'] == req.player_name), None)
    return {'success': True, 'phase': state['phase'],
            'progress': len(me['answers']) if me else 0}


@router.delete('/api/game/{session_id}/answer')
async def delete_answer(session_id: str, player_name: str, question_index: int):
    await _mutate(session_id, lambda s: game.undo_answer(s, player_name, question_index))
    return {'success': True}


@router.post('/api/game/{session_id}/reaction')
async def add_reaction(session_id: str, req: ReactionRequest):
    await _mutate(session_id, lambda s: game.apply_reaction(
        s, req.player_name, req.question_index, req.reaction))
    return {'success': True}


@router.post('/api/game/{session_id}/chat')
async def send_chat(session_id: str, req: ChatRequest):
    await _mutate(session_id, lambda s: game.apply_chat(
        s, req.player_name, req.message))
    return {'success': True}


@router.post('/api/game/{session_id}/rematch')
async def request_rematch(session_id: str, req: RematchRequest):
    async with session_locks[session_id]:
        state = store.get(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail='Game not found')
        try:
            new_state = game.rematch(state, req.player_name)
        except game.GameError as e:
            raise HTTPException(status_code=e.status, detail=str(e))
        store.put(new_state['id'], new_state)

    # tell everyone in the old game to hop over
    await notify(session_id, {'type': 'rematch', 'data': {
        'session_id': new_state['id'], 'by': req.player_name}})
    return {'session_id': new_state['id'], 'url': f"/game/{new_state['id']}"}


@router.get('/api/game/{session_id}')
async def get_state(session_id: str, player: str = None):
    state = store.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail='Game not found')
    return game.public_state(state, player)


@router.get('/api/game/{session_id}/results')
async def get_results(session_id: str, player: str = None):
    state = store.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail='Game not found')
    if state['phase'] != 'results':
        raise HTTPException(status_code=409, detail='Game not finished yet')
    return {'results': game.compute_results(state), 'quiz': state['title'],
            'players': [p['name'] for p in state['players']]}


# ── WebSocket: notification bus ─────────────────────────────────────

async def _mark_away_later(session_id: str, player: str):
    try:
        await asyncio.sleep(DISCONNECT_GRACE_SECONDS)
    except asyncio.CancelledError:
        return
    connections.pending_removals.pop(f'{session_id}:{player}', None)
    if connections.count_for_player(session_id, player) > 0:
        return  # they came back
    await _mutate(session_id, lambda s: game.set_connected(s, player, False))


@router.websocket('/ws/{session_id}/{player_name}')
async def game_socket(websocket: WebSocket, session_id: str, player_name: str):
    await websocket.accept()
    state = store.get(session_id)
    if state is None:
        await websocket.send_json({'type': 'error', 'data': {'detail': 'Game not found'}})
        await websocket.close()
        return

    connections.add(websocket, session_id, player_name)
    await _mutate(session_id, lambda s: game.set_connected(s, player_name, True))

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get('type')
            if msg_type == 'ping':
                await websocket.send_json({'type': 'pong', 'data': {'t': time.time()}})
            elif msg_type == 'refresh':
                state = store.get(session_id)
                if state:
                    await websocket.send_json({'type': 'state'})
            # anything else is ignored: the bus carries no business logic
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug('socket error %s: %s', session_id, e)
    finally:
        connections.drop(websocket)
        if connections.count_for_player(session_id, player_name) == 0:
            key = f'{session_id}:{player_name}'
            existing = connections.pending_removals.get(key)
            if existing:
                existing.cancel()
            connections.pending_removals[key] = asyncio.create_task(
                _mark_away_later(session_id, player_name))
