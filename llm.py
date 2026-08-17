"""LLM helpers: question generation, name suggestion, image extraction.

One shared httpx client, one JSON-extraction helper, no business logic
beyond prompt building and defensive parsing.
"""
import base64
import json
import logging
import random
import re
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

API_KEY = None      # set by app.py from config
BASE_URL = 'https://api.deepinfra.com/v1/openai/'
MODEL = 'google/gemma-3-27b-it'

_client: Optional[httpx.AsyncClient] = None


def configure(api_key: str, base_url: str = None, model: str = None):
    global API_KEY, BASE_URL, MODEL, _client
    API_KEY = api_key
    if base_url:
        BASE_URL = base_url
    if model:
        MODEL = model


async def chat(messages: List[dict], max_tokens: int = 1000,
               temperature: float = 0.7) -> Optional[str]:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    try:
        response = await _client.post(
            f'{BASE_URL}chat/completions',
            headers={'Authorization': f'Bearer {API_KEY}',
                     'Content-Type': 'application/json'},
            json={'model': MODEL, 'messages': messages,
                  'max_tokens': max_tokens, 'temperature': temperature},
        )
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        logger.error('LLM API error: %s', response.status_code)
        return None
    except Exception as e:
        logger.error('LLM error: %s', e)
        return None


async def close():
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def extract_json(text: str):
    """Pull the first JSON object/array out of an LLM reply (handles
    markdown fences and surrounding prose). Returns None if absent."""
    if not text:
        return None
    match = re.search(r'```json\s*([\[\{].*?[\]\]])\s*```', text, re.DOTALL)
    candidate = match.group(1) if match else None
    if candidate is None:
        for opener, closer in (('[', ']'), ('{', '}')):
            start = text.find(opener)
            end = text.rfind(closer)
            if start != -1 and end > start:
                candidate = text[start:end + 1]
                break
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


# ── question generation ─────────────────────────────────────────────

_FORMATS = {
    'competition': '{"prompt": "Question?", "option1": "Answer 1", "option2": "Answer 2", "correct_answer": "option1"}',
    'player': '{"prompt": "Who is more likely to...?", "option1": "Player 1", "option2": "Player 2"}',
    'thisorthat': '{"prompt": "Question?", "option1": "Option A", "option2": "Option B"}',
}


def _prompt(topic: str, quiz_type: str, count: int, avoid: List[str]) -> str:
    fmt = _FORMATS.get(quiz_type, _FORMATS['thisorthat'])
    if quiz_type == 'competition':
        body = (f'Generate {count} knowledge-based competition questions about {topic}. '
                f'Return ONLY a JSON array where each object follows: {fmt}. '
                'Mix up which option is correct for each question.')
    elif quiz_type == 'player':
        body = (f'Generate {count} "who is more likely to" comparison questions about {topic}. '
                f'Return ONLY a JSON array where each object follows: {fmt}.')
    else:
        body = (f'Generate {count} "this or that" preference questions about {topic}. '
                f'Return ONLY a JSON array where each object follows: {fmt}. '
                'Options should be short (1-3 words).')
    if avoid:
        body += f'\n\nAvoid questions similar to: {avoid[:5]}'
    return body


async def generate_questions(topic: str, quiz_type: str, count: int,
                             avoid: List[str] = None) -> List[dict]:
    """Returns a list of valid question dicts (may be shorter than count)."""
    response = await chat(
        [{'role': 'user', 'content': _prompt(topic, quiz_type, count, avoid or [])}],
        max_tokens=200 if count == 1 else 1500,
        temperature=0.8,
    )
    parsed = extract_json(response or '')
    if parsed is None:
        parsed = []
    elif isinstance(parsed, dict):
        parsed = [parsed]

    valid = []
    for q in parsed:
        if not isinstance(q, dict):
            continue
        if not all(q.get(k) for k in ('prompt', 'option1', 'option2')):
            continue
        if quiz_type == 'competition':
            # randomly swap sides so the correct answer isn't positional
            if q.get('correct_answer') in ('option1', 'option2') and random.random() < 0.5:
                q['option1'], q['option2'] = q['option2'], q['option1']
                q['correct_answer'] = ('option2' if q['correct_answer'] == 'option1'
                                       else 'option1')
        else:
            q.pop('correct_answer', None)
        valid.append({'prompt': q['prompt'].strip(),
                      'option1': q['option1'].strip(),
                      'option2': q['option2'].strip(),
                      **({'correct_answer': q['correct_answer']}
                         if quiz_type == 'competition' and q.get('correct_answer') in
                         ('option1', 'option2') else {})})
    return valid[:count]


async def suggest_name(context: str) -> Optional[str]:
    result = await chat(
        [{'role': 'user',
          'content': (f'Suggest a catchy, short quiz name for a quiz about: {context}\n'
                      'Return ONLY the quiz name as a string, no extra text.')}],
        max_tokens=20, temperature=0.8,
    )
    if not result:
        return None
    name = result.strip().strip('"').strip('`').strip()
    if ':' in name:
        name = name.split(':', 1)[-1].strip()
    return name or None


async def questions_from_image(image_bytes: bytes) -> List[dict]:
    """Extract this-or-that pairs from an image: LLM vision, OCR fallback."""
    image_data = base64.b64encode(image_bytes).decode('utf-8')
    response = await chat(
        [{'role': 'user', 'content': [
            {'type': 'text', 'text': ('Analyze this image and extract any "this or that" '
                                      'questions. Return ONLY a JSON array in this format: '
                                      '[{"prompt": "Question?", "option1": "Option 1", '
                                      '"option2": "Option 2"}]')},
            {'type': 'image_url',
             'image_url': {'url': f'data:image/jpeg;base64,{image_data}'}},
        ]}],
        max_tokens=800,
    )
    parsed = extract_json(response or '')
    if isinstance(parsed, list):
        valid = [q for q in parsed if isinstance(q, dict) and q.get('option1') and q.get('option2')]
        if valid:
            return [{'prompt': q.get('prompt') or 'Choose one:',
                     'option1': q['option1'], 'option2': q['option2']}
                    for q in valid[:10]]

    # OCR fallback
    try:
        import io
        import pytesseract
        from PIL import Image
        text = pytesseract.image_to_string(Image.open(io.BytesIO(image_bytes)))
        pairs = re.findall(
            r'([^?\n]+?)\s+(?:or|vs|versus)\s+([^?\n]+?)(?:\?|$|\n)',
            text, re.IGNORECASE)
        return [{'prompt': 'Choose one:',
                 'option1': a.strip(), 'option2': b.strip()}
                for a, b in pairs if len(a.strip()) > 2 and len(b.strip()) > 2][:10]
    except Exception as e:
        logger.error('OCR fallback failed: %s', e)
        return []
