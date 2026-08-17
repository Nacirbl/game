"""Quiz file helpers: load/save/list the JSON files in quizzes/."""
import json
import logging
import os
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

QUIZ_DIR = os.environ.get('QUIZ_DIR', 'quizzes')


def quiz_path(quiz_id: str) -> str:
    return os.path.join(QUIZ_DIR, f'{quiz_id}.json')


def load_quiz(quiz_id: str) -> Optional[dict]:
    """Return the quiz as a plain dict {id, title, type, questions} or None."""
    try:
        with open(quiz_path(quiz_id), 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.error('Error loading quiz %s: %s', quiz_id, e)
        return None
    data.setdefault('id', quiz_id)
    data.setdefault('type', 'thisorthat')
    return data


def save_quiz(title: str, quiz_type: str, questions: list,
              description: str = '') -> str:
    quiz_id = uuid.uuid4().hex[:8]
    os.makedirs(QUIZ_DIR, exist_ok=True)
    quiz = {
        'id': quiz_id,
        'title': title,
        'description': description,
        'type': quiz_type,
        'questions': questions,
        'created_at': __import__('time').strftime('%Y-%m-%dT%H:%M:%S'),
    }
    with open(quiz_path(quiz_id), 'w', encoding='utf-8') as f:
        json.dump(quiz, f, indent=2, ensure_ascii=False)
    return quiz_id


def list_quizzes() -> list:
    """Summaries of all saved quizzes, genuinely newest first."""
    out = []
    try:
        names = os.listdir(QUIZ_DIR)
    except FileNotFoundError:
        return out
    for name in names:
        if not name.endswith('.json'):
            continue
        quiz = load_quiz(name[:-5])
        if quiz and quiz.get('questions'):
            out.append({
                'id': quiz['id'],
                'title': quiz.get('title', 'Untitled'),
                'description': quiz.get('description') or '',
                'type': quiz.get('type', 'thisorthat'),
                'question_count': len(quiz['questions']),
                'created_at': quiz.get('created_at', ''),
            })
    # created_at is an ISO string; missing/old formats sort oldest
    out.sort(key=lambda q: q['created_at'] or '', reverse=True)
    return out
