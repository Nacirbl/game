"""Game logic: an explicit phase machine over plain session dicts.

Phases:  lobby -> playing -> results
Modes:   solo | duo (duo is implicit once a second player joins)

Every mutation goes through a function here; routes never touch session
internals. Answers are a map {question_index(str): {choice, player_choice?,
ts}} - one format, no holes, dedup for free.

public_state() is the single render contract consumed by the client.
"""
import time
import uuid
from typing import Optional

MAX_PLAYERS = 2
MAX_CHAT = 100
MAX_REACTIONS_PER_QUESTION = 50


class GameError(Exception):
    """Raised for any invalid transition; routes map it to a 4xx."""
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ── helpers ──────────────────────────────────────────────────────────

def _player(state: dict, name: str) -> Optional[dict]:
    return next((p for p in state['players'] if p['name'] == name), None)


def _require_player(state: dict, name: str) -> dict:
    player = _player(state, name)
    if player is None:
        raise GameError(f"Player '{name}' is not in this game", 403)
    return player


def _all_ready(state: dict) -> bool:
    return bool(state['players']) and all(p['ready'] for p in state['players'])


def _total(state: dict) -> int:
    return len(state['questions'])


def _progress(player: dict) -> int:
    return len(player['answers'])


def _completed(state: dict, player: dict) -> bool:
    return _progress(player) >= _total(state)


# ── creation & lobby ────────────────────────────────────────────────

def create_session(quiz: dict, host_name: str) -> dict:
    questions = [
        {
            'id': q.get('id'),
            'prompt': q['prompt'],
            'option1': q['option1'],
            'option2': q['option2'],
            # correct_answer is server-only (used to score competition)
            'correct_answer': q.get('correct_answer'),
        }
        for q in quiz['questions']
    ]
    if not questions:
        raise GameError('Quiz has no questions')

    session_id = uuid.uuid4().hex[:10]
    return {
        'id': session_id,
        'quiz_id': quiz['id'],
        'title': quiz['title'],
        'quiz_type': quiz.get('type', 'thisorthat'),
        'questions': questions,
        'phase': 'lobby',
        'mode': 'solo',          # becomes 'duo' when a second player joins
        'host': host_name,
        'players': [_new_player(host_name)],
        'reactions': {},          # {question_index(str): [{reaction, from, ts}]}
        'chat': [],               # [{message, from, ts}]
        'created_at': time.time(),
        'updated_at': time.time(),
    }


def _new_player(name: str) -> dict:
    return {'name': name, 'answers': {}, 'ready': False, 'connected': False}


def join(state: dict, name: str) -> dict:
    if _player(state, name):
        return state  # rejoining (refresh) is always fine
    if state['phase'] != 'lobby':
        raise GameError('This game has already started', 409)
    if len(state['players']) >= MAX_PLAYERS:
        raise GameError('This game is full', 409)
    state['players'].append(_new_player(name))
    state['mode'] = 'duo'
    state['updated_at'] = time.time()
    return state


def start_solo(state: dict, name: str) -> dict:
    player = _require_player(state, name)
    if state['phase'] != 'lobby':
        raise GameError('Game already started', 409)
    if len(state['players']) > 1:
        raise GameError('A friend already joined - play together instead', 409)
    state['mode'] = 'solo'
    player['ready'] = True
    state['phase'] = 'playing'
    state['updated_at'] = time.time()
    return state


def set_ready(state: dict, name: str) -> dict:
    player = _require_player(state, name)
    if state['phase'] != 'lobby':
        raise GameError('Game already started', 409)
    if state['mode'] == 'solo':
        raise GameError('This is a solo game - use start instead', 409)
    player['ready'] = True
    if len(state['players']) >= 2 and _all_ready(state):
        state['phase'] = 'playing'
    state['updated_at'] = time.time()
    return state


# ── playing ─────────────────────────────────────────────────────────

def apply_answer(state: dict, name: str, question_index: int,
                 choice: str, player_choice: str = None) -> dict:
    player = _require_player(state, name)
    if state['phase'] != 'playing':
        raise GameError('Game is not in progress', 409)
    if not (0 <= question_index < _total(state)):
        raise GameError('Question index out of range', 400)
    if choice not in ('left', 'right'):
        raise GameError('Choice must be left or right', 400)

    entry = {'choice': choice, 'ts': time.time()}
    if player_choice:
        entry['player_choice'] = player_choice
    player['answers'][str(question_index)] = entry

    _maybe_finish(state)
    state['updated_at'] = time.time()
    return state


def undo_answer(state: dict, name: str, question_index: int) -> dict:
    player = _require_player(state, name)
    if state['phase'] == 'results':
        raise GameError('Game already finished', 409)
    if str(question_index) not in player['answers']:
        raise GameError('No answer to undo for that question', 404)
    del player['answers'][str(question_index)]
    state['updated_at'] = time.time()
    return state


def _maybe_finish(state: dict) -> None:
    if all(_completed(state, p) for p in state['players']):
        state['phase'] = 'results'


def apply_reaction(state: dict, name: str, question_index: int, reaction: str) -> dict:
    _require_player(state, name)
    if not (0 <= question_index < _total(state)):
        raise GameError('Question index out of range', 400)
    bucket = state['reactions'].setdefault(str(question_index), [])
    bucket.append({'reaction': reaction, 'from': name, 'ts': time.time()})
    if len(bucket) > MAX_REACTIONS_PER_QUESTION:
        del bucket[:-MAX_REACTIONS_PER_QUESTION]
    state['updated_at'] = time.time()
    return state


def apply_chat(state: dict, name: str, message: str) -> dict:
    _require_player(state, name)
    message = (message or '').strip()[:100]
    if not message:
        raise GameError('Empty message')
    state['chat'].append({'message': message, 'from': name, 'ts': time.time()})
    if len(state['chat']) > MAX_CHAT:
        del state['chat'][:-MAX_CHAT]
    state['updated_at'] = time.time()
    return state


def set_connected(state: dict, name: str, connected: bool) -> dict:
    player = _player(state, name)
    if player is None:
        return state
    player['connected'] = connected
    state['updated_at'] = time.time()
    return state


def rematch(state: dict, requester: str) -> dict:
    """Fresh session with the same quiz and players, back in the lobby."""
    _require_player(state, requester)
    if state['phase'] != 'results':
        raise GameError('Can only rematch after the game ends', 409)

    new = create_session(
        {'id': state['quiz_id'], 'title': state['title'],
         'type': state['quiz_type'], 'questions': state['questions']},
        state['host'],
    )
    # carry over the players (fresh answers), keep duo if it was duo
    new['players'] = [_new_player(p['name']) for p in state['players']]
    new['mode'] = state['mode']
    return new


# ── results ─────────────────────────────────────────────────────────

def _display(state: dict, q: dict, entry: dict) -> str:
    """The human-readable choice, honouring player-mode picks."""
    if entry.get('player_choice'):
        return entry['player_choice']
    return q['option1'] if entry['choice'] == 'left' else q['option2']


def compute_results(state: dict) -> dict:
    players = state['players']
    me = players[0]
    rows = []

    if len(players) == 1 or state['mode'] == 'solo':
        for i, q in enumerate(state['questions']):
            entry = me['answers'].get(str(i))
            rows.append({
                'index': i,
                'prompt': q['prompt'],
                'option1': q['option1'],
                'option2': q['option2'],
                'my_display': _display(state, q, entry) if entry else '—',
            })
        return {'kind': 'solo', 'questions': rows, 'summary': {
            'answered': len(me['answers']), 'total': _total(state)}}

    other = players[1]
    matches = 0
    scores = {me['name']: 0, other['name']: 0}
    competition = state['quiz_type'] == 'competition'

    for i, q in enumerate(state['questions']):
        a = me['answers'].get(str(i))
        b = other['answers'].get(str(i))
        row = {
            'index': i,
            'prompt': q['prompt'],
            'option1': q['option1'],
            'option2': q['option2'],
            'a_name': me['name'], 'b_name': other['name'],
            'a_display': _display(state, q, a) if a else '—',
            'b_display': _display(state, q, b) if b else '—',
        }
        if competition:
            correct = q.get('correct_answer')
            a_ok = bool(a) and ((a['choice'] == 'left' and correct == 'option1') or
                                (a['choice'] == 'right' and correct == 'option2'))
            b_ok = bool(b) and ((b['choice'] == 'left' and correct == 'option1') or
                                (b['choice'] == 'right' and correct == 'option2'))
            if a_ok:
                scores[me['name']] += 1
            if b_ok:
                scores[other['name']] += 1
            row['status'] = ('both_correct' if a_ok and b_ok else
                             'a_correct' if a_ok else
                             'b_correct' if b_ok else 'both_wrong')
        else:
            is_match = bool(a and b and a['choice'] == b['choice'])
            if is_match:
                matches += 1
            row['status'] = 'match' if is_match else 'mismatch'
        rows.append(row)

    if competition:
        summary = {'scores': scores}
    else:
        total = max(_total(state), 1)
        summary = {'matches': matches, 'total': _total(state),
                   'compatibility': round(matches / total * 100)}
    return {'kind': 'competition' if competition else 'match',
            'questions': rows, 'summary': summary}


# ── render contract ─────────────────────────────────────────────────

def _player_public(state: dict, player: dict) -> dict:
    return {
        'name': player['name'],
        'ready': player['ready'],
        'connected': player['connected'],
        'progress': _progress(player),
        'total': _total(state),
        'completed': _completed(state, player),
    }


def public_state(state: dict, viewer: str = None) -> dict:
    me = _player(state, viewer)
    opponent = None
    if me and len(state['players']) > 1:
        other = next(p for p in state['players'] if p['name'] != viewer)
        opponent = _player_public(state, other)

    questions = [
        {'id': q.get('id'), 'prompt': q['prompt'],
         'option1': q['option1'], 'option2': q['option2']}
        for q in state['questions']
    ]

    return {
        'session_id': state['id'],
        'phase': state['phase'],
        'mode': state['mode'],
        'quiz': {'title': state['title'], 'type': state['quiz_type']},
        'invite_path': f"/join/{state['id']}",
        'me': _player_public(state, me) if me else None,
        'opponent': opponent,
        'players': [_player_public(state, p) for p in state['players']],
        'questions': questions,
        'my_answers': dict(me['answers']) if me else {},
        'reactions': state['reactions'],
        'chat': state['chat'][-30:],
        'results': compute_results(state) if state['phase'] == 'results' else None,
    }
