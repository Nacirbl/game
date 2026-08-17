"""Quiz routes: question bank, dynamic quiz creation, saved quizzes,
and the admin/LLM authoring endpoints."""
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator

import llm
import quizlib
from config import ADMIN_TOKEN
from question_database import QuestionDatabase

logger = logging.getLogger(__name__)
router = APIRouter()

question_db = QuestionDatabase(os.environ.get('QUESTIONS_DB', 'questions_db.json'))


# ── models ──────────────────────────────────────────────────────────

class QuestionIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    option1: str = Field(min_length=1, max_length=200)
    option2: str = Field(min_length=1, max_length=200)
    correct_answer: Optional[str] = None

    @field_validator('correct_answer')
    @classmethod
    def check_correct(cls, v):
        if v is not None and v not in ('option1', 'option2'):
            raise ValueError('correct_answer must be "option1" or "option2"')
        return v


class CreateQuizRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ''
    type: str = 'thisorthat'
    questions: List[QuestionIn] = Field(min_length=1, max_length=100)

    @field_validator('type')
    @classmethod
    def check_type(cls, v):
        if v not in ('thisorthat', 'competition', 'player'):
            raise ValueError('type must be thisorthat, competition or player')
        return v


class GenerateQuestionsRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    quiz_type: str = 'thisorthat'
    count: int = Field(ge=1, le=10)
    avoid: List[str] = []


class DynamicQuizRequest(BaseModel):
    category: str = 'mixed'
    question_count: int = Field(default=10, ge=1, le=30)
    player_name: Optional[str] = None
    exclude_ids: List[str] = []


# ── question bank (home page categories) ────────────────────────────

@router.get('/api/categories')
async def categories():
    return {'categories': question_db.get_categories_with_counts(),
            'total_questions': len(question_db.questions)}


@router.post('/api/create-dynamic-quiz')
async def create_dynamic_quiz(req: DynamicQuizRequest):
    if req.category == 'daily':
        quiz_data = question_db.get_daily_challenge()
    elif req.category == 'trending':
        quiz_data = question_db.get_trending_quiz(req.question_count)
    else:
        exclude = set(req.exclude_ids[:500])
        quiz_data = question_db.get_random_quiz(
            category=None if req.category == 'mixed' else req.category,
            count=req.question_count,
            exclude_ids=exclude,
        )
    if not quiz_data:
        raise HTTPException(status_code=400, detail='Not enough questions available')

    quiz_id = quizlib.save_quiz(
        title=quiz_data['title'],
        quiz_type='thisorthat',
        questions=[{'id': q.get('id'), 'prompt': q['prompt'],
                    'option1': q['option1'], 'option2': q['option2']}
                   for q in quiz_data['questions']],
    )
    return {'quiz_id': quiz_id}


@router.get('/api/quizzes')
async def list_saved_quizzes():
    return quizlib.list_quizzes()


# ── quiz authoring (admin) ──────────────────────────────────────────

@router.post('/api/create_quiz')
async def create_quiz(req: CreateQuizRequest):
    quiz_id = quizlib.save_quiz(
        title=req.title.strip(),
        quiz_type=req.type,
        description=req.description,
        questions=[q.model_dump() for q in req.questions],
    )
    return {'success': True, 'quiz_id': quiz_id,
            'test_url': f'/game-preview/{quiz_id}',
            'share_url': f'/?quiz={quiz_id}'}


@router.post('/api/generate_question')
async def generate_question(req: GenerateQuestionsRequest):
    questions = await llm.generate_questions(
        topic=req.topic, quiz_type=req.quiz_type,
        count=req.count, avoid=req.avoid,
    )
    if not questions:
        raise HTTPException(status_code=502, detail='Question generation failed')
    return {'success': True, 'questions': questions, 'count': len(questions)}


@router.post('/api/suggest_quiz_name')
async def suggest_quiz_name(context: str, quiz_type: str = 'thisorthat'):
    context = (context or '').strip()
    if not context:
        raise HTTPException(status_code=400, detail='No context provided')
    name = await llm.suggest_name(context)
    if not name:
        raise HTTPException(status_code=502, detail='No name generated')
    return {'success': True, 'suggested_name': name}


@router.post('/api/upload_image')
async def upload_image(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail='No file selected')
    content = await file.read()
    if len(content) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='Image too large (16MB max)')
    questions = await llm.questions_from_image(content)
    if not questions:
        raise HTTPException(status_code=422, detail='No questions found in image')
    return {'success': True, 'questions': questions}


@router.post('/api/validate-admin-token')
async def validate_admin_token(token: str):
    return {'success': token == ADMIN_TOKEN}
