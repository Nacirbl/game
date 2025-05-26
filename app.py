from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import uuid
import os
import time
import threading
import atexit
from datetime import datetime, timedelta
import base64
from PIL import Image
import io
import pytesseract
import re
import requests
from concurrent.futures import ThreadPoolExecutor
import logging

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# LLM Configuration
DEEPINFRA_API_KEY = "wtKCca7JOYrwt9EiOe7sKIzmNXa9kJWm"
DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai/"
LLM_MODEL_NAME = "google/gemma-3-27b-it"

# Ensure directories exist
os.makedirs('quizzes', exist_ok=True)
os.makedirs('uploads', exist_ok=True)
os.makedirs('play_sessions', exist_ok=True)

# ===== IN-MEMORY SESSION MANAGEMENT =====

# Session manager heartbeat and disconnect detection
player_heartbeats = {}  # session_id -> last_ping_time
HEARTBEAT_TIMEOUT = 30  # seconds

class SessionManager:
    """Thread-safe in-memory session manager with disk persistence"""
    
    def __init__(self):
        self.sessions = {}  # session_id -> session_data
        self.session_lock = threading.RLock()  # Reentrant lock for nested operations
        self.last_access = {}  # session_id -> last_access_time
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="session-bg")
        self.shutdown_requested = False
        
        # Session configuration
        self.SESSION_TIMEOUT = 3600  # 1 hour in seconds
        self.CLEANUP_INTERVAL = 300   # 5 minutes
        self.SAVE_INTERVAL = 60      # 1 minute
        
        # Load existing sessions from disk
        self._load_sessions_from_disk()
        
        # Start background tasks
        self._start_background_tasks()
        
    def _load_sessions_from_disk(self):
        """Load existing sessions from JSON files on startup"""
        if not os.path.exists('play_sessions'):
            return
            
        loaded_count = 0
        try:
            for filename in os.listdir('play_sessions'):
                if filename.endswith('.json') and not filename.startswith('group_'):
                    session_id = filename[:-5]  # Remove .json
                    try:
                        with open(f'play_sessions/{filename}', 'r') as f:
                            session_data = json.load(f)
                            
                        # Check if session is not too old
                        started_at = datetime.fromisoformat(session_data['started_at'])
                        if datetime.now() - started_at < timedelta(seconds=self.SESSION_TIMEOUT):
                            self.sessions[session_id] = session_data
                            self.last_access[session_id] = time.time()
                            loaded_count += 1
                        else:
                            # Session is too old, move to results if completed
                            if session_data.get('current_question', 0) >= len(session_data.get('questions', [])):
                                self._save_completed_session_to_results(session_data)
                                
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"Failed to load session {filename}: {e}")
                        
        except Exception as e:
            logger.error(f"Error loading sessions from disk: {e}")
            
        logger.info(f"Loaded {loaded_count} sessions from disk")
        
    def _start_background_tasks(self):
        """Start background cleanup and persistence tasks"""
        def cleanup_worker():
            while not self.shutdown_requested:
                try:
                    self._cleanup_expired_sessions()
                    self.check_disconnected_players()
                    time.sleep(self.CLEANUP_INTERVAL)
                except Exception as e:
                    logger.error(f"Session cleanup error: {e}")
                    
        def persistence_worker():
            while not self.shutdown_requested:
                try:
                    self._persist_sessions_to_disk()
                    time.sleep(self.SAVE_INTERVAL)
                except Exception as e:
                    logger.error(f"Session persistence error: {e}")
                    
        self.executor.submit(cleanup_worker)
        self.executor.submit(persistence_worker)
        
    def create_session(self, quiz_id, shared_session_id=None, player_name=None):
        """Create a new session"""
        quiz_data = load_quiz(quiz_id)
        if not quiz_data:
            return None
            
        session_id = str(uuid.uuid4())[:8]
        current_time = time.time()
        
        session_data = {
            'session_id': session_id,
            'quiz_id': quiz_id,
            'quiz_title': quiz_data['title'],
            'questions': quiz_data['questions'],
            'current_question': 0,
            'answers': [],
            'started_at': datetime.now().isoformat(),
            'shared_session_group': shared_session_id or session_id,
            'player_name': player_name or f'Player {session_id[:4]}'
        }
        
        with self.session_lock:
            self.sessions[session_id] = session_data
            self.last_access[session_id] = current_time
            
        logger.info(f"Created session {session_id} for quiz {quiz_id}")
        return session_id
        
    def get_session(self, session_id):
        """Get session data and update last access time"""
        with self.session_lock:
            if session_id in self.sessions:
                self.last_access[session_id] = time.time()
                return self.sessions[session_id].copy()  # Return copy to prevent external modification
            return None
            
    def update_session(self, session_id, session_data):
        """Update session data"""
        with self.session_lock:
            if session_id in self.sessions:
                self.sessions[session_id] = session_data.copy()
                self.last_access[session_id] = time.time()
                return True
            return False
            
    def submit_answer(self, session_id, answer):
        """Submit an answer and update session"""
        with self.session_lock:
            if session_id not in self.sessions:
                return None
                
            session_data = self.sessions[session_id]
            
            # Record the answer
            session_data['answers'].append({
                'question_index': session_data['current_question'],
                'answer': answer,
                'timestamp': datetime.now().isoformat()
            })
            
            # Move to next question
            session_data['current_question'] += 1
            self.last_access[session_id] = time.time()
            
            # Check if quiz is complete
            is_complete = session_data['current_question'] >= len(session_data['questions'])
            
            # If complete, save results and remove from active sessions
            if is_complete:
                self._save_completed_session_to_results(session_data)
                
            return {
                'success': True,
                'is_complete': is_complete,
                'current_question': session_data['current_question'],
                'total_questions': len(session_data['questions'])
            }
            
    def submit_player_answer(self, session_id, answer, player_choice):
        """Submit an answer for player mode with proper mapping"""
        with self.session_lock:
            if session_id not in self.sessions:
                return None
                
            session_data = self.sessions[session_id]
            
            # Record the answer with player choice mapping
            session_data['answers'].append({
                'question_index': session_data['current_question'],
                'answer': answer,  # 'left' or 'right' (relative to their screen)
                'player_choice': player_choice,  # Which actual player they chose
                'timestamp': datetime.now().isoformat()
            })
            
            # Move to next question
            session_data['current_question'] += 1
            self.last_access[session_id] = time.time()
            
            # Check if quiz is complete
            is_complete = session_data['current_question'] >= len(session_data['questions'])
            
            # If complete, save results and remove from active sessions
            if is_complete:
                self._save_completed_session_to_results(session_data)
                
            return {
                'success': True,
                'is_complete': is_complete,
                'current_question': session_data['current_question'],
                'total_questions': len(session_data['questions']),
                'player_choice': player_choice
            }
            
    def get_sessions_by_group(self, shared_group_id, quiz_id=None):
        """Get all sessions in a shared group"""
        with self.session_lock:
            group_sessions = []
            for session_id, session_data in self.sessions.items():
                if (session_data.get('shared_session_group') == shared_group_id and
                    (quiz_id is None or session_data.get('quiz_id') == quiz_id)):
                    self.last_access[session_id] = time.time()
                    group_sessions.append(session_data.copy())
            return group_sessions
            
    def delete_session(self, session_id):
        """Delete a session"""
        with self.session_lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                if session_id in self.last_access:
                    del self.last_access[session_id]
                return True
            return False
            
    def get_session_count(self):
        """Get total number of active sessions"""
        with self.session_lock:
            return len(self.sessions)
            
    def _cleanup_expired_sessions(self):
        """Remove expired sessions"""
        current_time = time.time()
        expired_sessions = []
        
        with self.session_lock:
            for session_id, last_access in self.last_access.items():
                if current_time - last_access > self.SESSION_TIMEOUT:
                    expired_sessions.append(session_id)
                    
        for session_id in expired_sessions:
            with self.session_lock:
                if session_id in self.sessions:
                    session_data = self.sessions[session_id]
                    # If session was completed, save to results
                    if session_data.get('current_question', 0) >= len(session_data.get('questions', [])):
                        self._save_completed_session_to_results(session_data)
                    del self.sessions[session_id]
                    del self.last_access[session_id]
                    
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
            
    def _persist_sessions_to_disk(self):
        """Save active sessions to disk for persistence"""
        with self.session_lock:
            sessions_to_save = self.sessions.copy()
            
        saved_count = 0
        for session_id, session_data in sessions_to_save.items():
            try:
                with open(f'play_sessions/{session_id}.json', 'w') as f:
                    json.dump(session_data, f, indent=2)
                saved_count += 1
            except Exception as e:
                logger.error(f"Failed to persist session {session_id}: {e}")
                
        if saved_count > 0:
            logger.debug(f"Persisted {saved_count} sessions to disk")
            
    def _save_completed_session_to_results(self, session_data):
        """Save completed session to results directory"""
        try:
            save_quiz_results(session_data)
            logger.info(f"Saved completed session {session_data['session_id']} to results")
        except Exception as e:
            logger.error(f"Failed to save results for session {session_data['session_id']}: {e}")
            
    def shutdown(self):
        """Graceful shutdown - save all sessions and stop background tasks"""
        logger.info("Shutting down session manager...")
        self.shutdown_requested = True
        
        # Save all sessions one final time
        self._persist_sessions_to_disk()
        
        # Shutdown thread pool
        self.executor.shutdown(wait=True, timeout=10)
        
        logger.info("Session manager shutdown complete")

    def update_player_heartbeat(self, session_id):
        """Update the last heartbeat time for a player"""
        player_heartbeats[session_id] = time.time()
        
    def check_disconnected_players(self):
        """Check for disconnected players and notify their partners"""
        current_time = time.time()
        disconnected_sessions = []
        
        with self.session_lock:
            for session_id, last_ping in player_heartbeats.items():
                if current_time - last_ping > HEARTBEAT_TIMEOUT:
                    disconnected_sessions.append(session_id)
            
            # Remove disconnected players
            for session_id in disconnected_sessions:
                if session_id in player_heartbeats:
                    del player_heartbeats[session_id]
                    
                # Notify partners about disconnection
                session = self.sessions.get(session_id)
                if session and session.get('shared_session_group'):
                    partner_sessions = self.get_sessions_by_group(session['shared_session_group'])
                    for partner_session in partner_sessions:
                        if partner_session['session_id'] != session_id:
                            # Mark partner disconnection
                            partner_session['partner_disconnected'] = True
                            partner_session['partner_disconnect_time'] = current_time
                            
        return disconnected_sessions

# Global session manager instance
session_manager = SessionManager()

# Register cleanup function for graceful shutdown
atexit.register(session_manager.shutdown)

def load_quiz(quiz_id):
    """Load quiz data from JSON file"""
    try:
        with open(f'quizzes/{quiz_id}.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def save_quiz(quiz_data):
    """Save quiz data to JSON file"""
    quiz_id = str(uuid.uuid4())[:8]
    quiz_data['id'] = quiz_id
    quiz_data['created_at'] = datetime.now().isoformat()
    
    with open(f'quizzes/{quiz_id}.json', 'w') as f:
        json.dump(quiz_data, f, indent=2)
    
    return quiz_id

def create_play_session(quiz_id, shared_session_id=None, player_name=None):
    """Create a new play session for a quiz"""
    return session_manager.create_session(quiz_id, shared_session_id, player_name)

def save_quiz_results(session_data):
    """Save completed quiz results for analytics"""
    results_dir = 'results'
    os.makedirs(results_dir, exist_ok=True)
    
    result_data = {
        'session_id': session_data['session_id'],
        'quiz_id': session_data['quiz_id'],
        'quiz_title': session_data['quiz_title'],
        'completed_at': datetime.now().isoformat(),
        'started_at': session_data['started_at'],
        'total_questions': len(session_data['questions']),
        'answers': session_data['answers'],
        'choices_summary': {},
        'shared_session_group': session_data.get('shared_session_group', session_data['session_id']),
        'player_name': session_data.get('player_name', f"Player {session_data['session_id'][:4]}")
    }
    
    # Analyze choices
    for i, question in enumerate(session_data['questions']):
        answer_data = next((a for a in session_data['answers'] if a['question_index'] == i), None)
        if answer_data:
            choice = question['option1'] if answer_data['answer'] == 'left' else question['option2']
            result_data['choices_summary'][f'question_{i}'] = {
                'options': [question['option1'], question['option2']],
                'choice': choice,
                'choice_side': answer_data['answer']
            }
    
    # Save to results file
    with open(f'{results_dir}/{session_data["session_id"]}.json', 'w') as f:
        json.dump(result_data, f, indent=2)

def call_llm(messages, max_tokens=1000, temperature=0.7):
    """Call the DeepInfra LLM API"""
    try:
        headers = {
            "Authorization": f"Bearer {DEEPINFRA_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": LLM_MODEL_NAME,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        response = requests.post(
            f"{DEEPINFRA_BASE_URL}chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            print(f"LLM API Error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"LLM Error: {e}")
        return None

def generate_question_with_llm(topic, quiz_type="thisorthat", existing_questions=None, count=1):
    """Generate one or more questions using LLM based on topic and quiz type"""
    try:
        if count == 1:
            # Single question generation (existing logic)
            if quiz_type == "competition":
                prompt = f"""Generate a knowledge-based competition question about {topic}. 
Return ONLY a JSON object with this exact format:
{{
    "prompt": "Your question here?",
    "option1": "First answer option",
    "option2": "Second answer option", 
    "correct_answer": "option1" or "option2"
}}

Make it challenging but fair. Ensure one option is clearly correct and the other is a plausible but wrong answer. The question prompt should be 5-8 words max. Answer options should be short (1-3 words).

IMPORTANT: Randomly choose which option (option1 or option2) is correct. Mix it up - sometimes option1 should be correct, sometimes option2. Don't always make the same option correct."""

            elif quiz_type == "player":
                prompt = f"""Generate a "Player 1 vs Player 2" comparison question about {topic}.
Return ONLY a JSON object with this exact format:
{{
    "prompt": "Your question here?",
    "option1": "Player 1",
    "option2": "Player 2"
}}

The question should be about who is more likely to do something or who would be better at something related to {topic}. Question prompt should be 5-8 words max.
Examples: "Who wakes up earlier?", "Who is more adventurous?", "Who cooks better food?"""

            else:  # thisorthat mode
                prompt = f"""Generate a "this or that" preference question about {topic}.
Return ONLY a JSON object with this exact format:
{{
    "prompt": "Your question here?", 
    "option1": "First preference option",
    "option2": "Second preference option"
}}

Make it fun and engaging. These are personal preference questions with no right or wrong answers. Question prompt should be 5-8 words max. Answer options should be short (1-3 words)."""

            # Add context about existing questions to avoid duplicates
            if existing_questions and len(existing_questions) > 0:
                existing_prompts = [q.get('prompt', '') for q in existing_questions]
                prompt += f"\n\nAvoid creating questions similar to these existing ones: {existing_prompts[:3]}"

            messages = [{"role": "user", "content": prompt}]
            response = call_llm(messages, max_tokens=300, temperature=0.8)
            
            if response:
                question_data = parse_single_question_response(response, quiz_type)
                return question_data if question_data else None
                
        else:
            # Batch question generation (10 questions)
            if quiz_type == "competition":
                prompt = f"""Generate {count} knowledge-based competition questions about {topic}. 
Return ONLY a JSON array with this exact format:
[
    {{
        "prompt": "Question 1?",
        "option1": "Answer option",
        "option2": "Answer option", 
        "correct_answer": "option1" or "option2"
    }},
    {{
        "prompt": "Question 2?",
        "option1": "Answer option",
        "option2": "Answer option", 
        "correct_answer": "option1" or "option2"
    }}
    // ... continue for {count} questions
]

Make each question challenging but fair. Ensure one option is clearly correct and the other is plausible but wrong. Question prompts should be 5-8 words max. Answer options should be short (1-3 words).

IMPORTANT: Randomly vary which option is correct across all questions. For some questions make option1 correct, for others make option2 correct. Aim for roughly 50/50 distribution. Don't make the same option correct for all questions."""

            elif quiz_type == "player":
                prompt = f"""Generate {count} "Player 1 vs Player 2" comparison questions about {topic}.
Return ONLY a JSON array with this exact format:
[
    {{
        "prompt": "Question 1?",
        "option1": "Player 1",
        "option2": "Player 2"
    }},
    {{
        "prompt": "Question 2?",
        "option1": "Player 1",
        "option2": "Player 2"
    }}
    // ... continue for {count} questions
]

Each question should be about who is more likely to do something or who would be better at something related to {topic}. Question prompts should be 5-8 words max.
Examples: "Who wakes up earlier?", "Who is more adventurous?", "Who cooks better?"""

            else:  # thisorthat mode
                prompt = f"""Generate {count} "this or that" preference questions about {topic}.
Return ONLY a JSON array with this exact format:
[
    {{
        "prompt": "Question 1?", 
        "option1": "Option A",
        "option2": "Option B"
    }},
    {{
        "prompt": "Question 2?", 
        "option1": "Option A",
        "option2": "Option B"
    }}
    // ... continue for {count} questions
]

Make them fun and engaging. These are personal preference questions with no right or wrong answers. Question prompts should be 5-8 words max. Answer options should be short (1-3 words)."""

            # Add context about existing questions
            if existing_questions and len(existing_questions) > 0:
                existing_prompts = [q.get('prompt', '') for q in existing_questions]
                prompt += f"\n\nAvoid creating questions similar to these existing ones: {existing_prompts[:5]}"

            messages = [{"role": "user", "content": prompt}]
            response = call_llm(messages, max_tokens=1500, temperature=0.8)
            
            if response:
                questions_data = parse_batch_questions_response(response, quiz_type)
                return questions_data if questions_data and len(questions_data) > 0 else None
        
        return None
        
    except Exception as e:
        print(f"Question generation error: {e}")
        return None

def parse_single_question_response(response, quiz_type):
    """Parse a single question response from LLM"""
    try:
        import json
        import random
        
        # Find JSON in the response (it might have extra text)
        start = response.find('{')
        end = response.rfind('}') + 1
        
        if start != -1 and end != 0:
            json_str = response[start:end]
            question_data = json.loads(json_str)
            
            # Validate the response format
            required_fields = ['prompt', 'option1', 'option2']
            if quiz_type == "competition":
                required_fields.append('correct_answer')
            
            if all(field in question_data for field in required_fields):
                # For competition mode, add some randomization if AI didn't mix it up
                if quiz_type == "competition" and random.random() < 0.5:
                    # 50% chance to swap the options to ensure randomization
                    option1 = question_data['option1']
                    option2 = question_data['option2']
                    correct = question_data['correct_answer']
                    
                    # Swap options
                    question_data['option1'] = option2
                    question_data['option2'] = option1
                    
                    # Update correct answer accordingly
                    if correct == 'option1':
                        question_data['correct_answer'] = 'option2'
                    else:
                        question_data['correct_answer'] = 'option1'
                
                return question_data
                
    except json.JSONDecodeError:
        pass
    return None

def parse_batch_questions_response(response, quiz_type):
    """Parse batch questions response from LLM"""
    try:
        import json
        import random
        
        # Find JSON array in the response
        start = response.find('[')
        end = response.rfind(']') + 1
        
        if start != -1 and end != 0:
            json_str = response[start:end]
            questions_array = json.loads(json_str)
            
            if isinstance(questions_array, list):
                valid_questions = []
                required_fields = ['prompt', 'option1', 'option2']
                if quiz_type == "competition":
                    required_fields.append('correct_answer')
                
                for question_data in questions_array:
                    if isinstance(question_data, dict) and all(field in question_data for field in required_fields):
                        # For competition mode, add randomization
                        if quiz_type == "competition" and random.random() < 0.5:
                            # 50% chance to swap the options to ensure good mix
                            option1 = question_data['option1']
                            option2 = question_data['option2']
                            correct = question_data['correct_answer']
                            
                            # Swap options
                            question_data['option1'] = option2
                            question_data['option2'] = option1
                            
                            # Update correct answer accordingly
                            if correct == 'option1':
                                question_data['correct_answer'] = 'option2'
                            else:
                                question_data['correct_answer'] = 'option1'
                        
                        valid_questions.append(question_data)
                
                # For competition mode, ensure we have a good mix of correct answers
                if quiz_type == "competition" and len(valid_questions) > 1:
                    option1_count = sum(1 for q in valid_questions if q['correct_answer'] == 'option1')
                    option2_count = len(valid_questions) - option1_count
                    
                    # If too imbalanced (more than 70% one way), rebalance some
                    if option1_count > 0.7 * len(valid_questions):
                        # Too many option1 correct, flip some to option2
                        need_to_flip = option1_count - len(valid_questions) // 2
                        flipped = 0
                        for question in valid_questions:
                            if question['correct_answer'] == 'option1' and flipped < need_to_flip:
                                # Swap options
                                option1 = question['option1']
                                option2 = question['option2']
                                question['option1'] = option2
                                question['option2'] = option1
                                question['correct_answer'] = 'option2'
                                flipped += 1
                    
                    elif option2_count > 0.7 * len(valid_questions):
                        # Too many option2 correct, flip some to option1
                        need_to_flip = option2_count - len(valid_questions) // 2
                        flipped = 0
                        for question in valid_questions:
                            if question['correct_answer'] == 'option2' and flipped < need_to_flip:
                                # Swap options
                                option1 = question['option1']
                                option2 = question['option2']
                                question['option1'] = option2
                                question['option2'] = option1
                                question['correct_answer'] = 'option1'
                                flipped += 1
                
                return valid_questions[:10]  # Limit to 10 questions max
                
    except json.JSONDecodeError:
        pass
    return None

def extract_questions_from_image_with_llm(image_path):
    """Extract questions from image using LLM vision capabilities"""
    try:
        # Convert image to base64
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
        
        text_prompt = """Analyze this image and extract any "this or that" questions you can find. 
Return a JSON array of questions in this format:
[
    {
        "prompt": "Question text?",
        "option1": "First option", 
        "option2": "Second option"
    }
]

Look for any comparison questions, either/or choices, preference questions, or any content that could be turned into "this or that" format. If the image has general content, create relevant questions based on what you see.

Return ONLY the JSON array, no other text."""
        
        # Create message with image
        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": text_prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_data}"
                    }
                }
            ]
        }]
        
        response = call_llm(messages, max_tokens=800, temperature=0.7)
        
        if response:
            try:
                # Find JSON in the response
                start = response.find('[')
                end = response.rfind(']') + 1
                
                if start != -1 and end != 0:
                    json_str = response[start:end]
                    questions = json.loads(json_str)
                    
                    # Validate and clean the questions
                    valid_questions = []
                    for q in questions:
                        if isinstance(q, dict) and 'option1' in q and 'option2' in q:
                            question_data = {
                                'prompt': q.get('prompt', ''),
                                'option1': q['option1'],
                                'option2': q['option2']
                            }
                            valid_questions.append(question_data)
                    
                    return valid_questions[:10]  # Limit to 10 questions
                    
            except json.JSONDecodeError:
                pass
        
        # Fallback to OCR if LLM fails
        return extract_questions_from_image_ocr(image_path)
        
    except Exception as e:
        print(f"LLM Image processing error: {e}")
        return extract_questions_from_image_ocr(image_path)

def extract_questions_from_image_ocr(image_path):
    """Extract 'this or that' questions from uploaded image using OCR (fallback method)"""
    try:
        # Extract text from image
        text = pytesseract.image_to_string(Image.open(image_path))
        
        # Look for patterns like "X or Y", "X vs Y", etc.
        patterns = [
            r'([^?\n]+?)\s+(?:or|vs|versus)\s+([^?\n]+?)(?:\?|$|\n)',
            r'([^?\n]+?)\s+or\s+([^?\n]+?)(?:\?|$|\n)',
        ]
        
        questions = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                option1 = match[0].strip()
                option2 = match[1].strip()
                if len(option1) > 2 and len(option2) > 2:
                    questions.append({
                        'option1': option1,
                        'option2': option2
                    })
        
        return questions[:10]  # Limit to 10 questions
    except Exception as e:
        print(f"OCR Error: {e}")
        return []

# Maintain backward compatibility
def extract_questions_from_image(image_path):
    """Extract questions from image - tries LLM first, falls back to OCR"""
    return extract_questions_from_image_with_llm(image_path)

@app.route('/')
def index():
    """Landing page with options to create or play"""
    return render_template('index.html')

@app.route('/admin')
def admin():
    """Admin interface for creating quizzes"""
    return render_template('admin.html')

@app.route('/results')
def results():
    """Results viewer page"""
    return render_template('results.html')

@app.route('/multiplayer-results/<session_id>')
def multiplayer_results(session_id):
    """Multiplayer results comparison page"""
    try:
        # Get the session data to find quiz info
        session_data = session_manager.get_session(session_id)
        
        if not session_data:
            # If not in active sessions, try results
            try:
                with open(f'results/{session_id}.json', 'r') as f:
                    result_data = json.load(f)
                    session_data = {
                        'session_id': session_id,
                        'quiz_title': result_data['quiz_title'],
                        'shared_session_group': result_data.get('shared_session_group', session_id)
                    }
            except FileNotFoundError:
                return "Session not found", 404
        
        return render_template('multiplayer-results.html', 
                             session_id=session_id,
                             quiz_title=session_data['quiz_title'])
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/play/<quiz_id>')
def play_quiz(quiz_id):
    """Start playing a quiz or join a shared session"""
    # Check if this is a join request via URL parameter
    shared_session = request.args.get('join')
    if shared_session:
        # This is a join request - redirect to join page
        return redirect(url_for('join_session', session_id=shared_session))
    
    # Check if player name is provided via URL parameter
    player_name = request.args.get('player_name')
    
    # Normal play - create new session
    session_id = create_play_session(quiz_id, None, player_name)
    if not session_id:
        return "Quiz not found", 404
    
    return redirect(url_for('play_session', session_id=session_id))

@app.route('/join/<session_id>')
def join_session(session_id):
    """Join an existing session"""
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return "Session not found", 404
    
    # Check if session exists and is valid for joining
    quiz_id = session_data['quiz_id']
    
    # Render a join page where user can enter their name
    return render_template('join.html', session_id=session_id, quiz_title=session_data['quiz_title'])

@app.route('/new-session/<quiz_id>')
def new_session(quiz_id):
    """Create a new session for an existing quiz"""
    session_id = create_play_session(quiz_id)
    if not session_id:
        return "Quiz not found", 404
    
    return redirect(url_for('play_session', session_id=session_id))

@app.route('/session/<session_id>')
def play_session(session_id):
    """Play a specific session - show completion screen if finished"""
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return "Session not found", 404
    
    # Always show the play template - it will handle completed state
    return render_template('play.html', session=session_data)

@app.route('/api/create_quiz', methods=['POST'])
def api_create_quiz():
    """API endpoint to create a new quiz"""
    data = request.get_json()
    
    quiz_data = {
        'title': data.get('title', 'Untitled Quiz'),
        'description': data.get('description', ''),
        'type': data.get('type', 'thisorthat'),
        'questions': data.get('questions', [])
    }
    
    quiz_id = save_quiz(quiz_data)
    return jsonify({'success': True, 'quiz_id': quiz_id})

@app.route('/api/create-session', methods=['POST'])
def api_create_session():
    """API endpoint to create a new session"""
    data = request.get_json()
    quiz_id = data.get('quiz_id')
    shared_group_id = data.get('shared_session_group')
    player_name = data.get('player_name')
    
    if not quiz_id:
        return jsonify({'success': False, 'error': 'Quiz ID required'})
    
    session_id = create_play_session(quiz_id, shared_group_id, player_name)
    if session_id:
        return jsonify({'success': True, 'session_id': session_id})
    else:
        return jsonify({'success': False, 'error': 'Quiz not found'})

@app.route('/api/upload_image', methods=['POST'])
def api_upload_image():
    """API endpoint to upload and process image"""
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'No image uploaded'})
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No image selected'})
    
    # Save uploaded file
    filename = str(uuid.uuid4()) + '_' + file.filename
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # Extract questions from image
    questions = extract_questions_from_image(filepath)
    
    # Clean up uploaded file
    os.remove(filepath)
    
    return jsonify({'success': True, 'questions': questions})

@app.route('/api/generate_question', methods=['POST'])
def api_generate_question():
    """API endpoint to generate one or more questions using LLM"""
    try:
        data = request.get_json()
        topic = data.get('topic', '').strip()
        quiz_type = data.get('quiz_type', 'thisorthat')
        existing_questions = data.get('existing_questions', [])
        count = data.get('count', 1)  # Default to single question
        
        if not topic:
            return jsonify({'success': False, 'error': 'Topic is required'})
        
        # Determine actual quiz type for player mode
        is_player_mode = data.get('is_player_mode', False)
        if is_player_mode and quiz_type == 'thisorthat':
            actual_quiz_type = 'player'
        else:
            actual_quiz_type = quiz_type
        
        # Generate question(s) using LLM
        result = generate_question_with_llm(topic, actual_quiz_type, existing_questions, count)
        
        if result:
            if count == 1:
                return jsonify({'success': True, 'question': result})
            else:
                return jsonify({'success': True, 'questions': result, 'count': len(result)})
        else:
            return jsonify({'success': False, 'error': 'Failed to generate questions. Please try a different topic or try again.'})
            
    except Exception as e:
        print(f"Generate question API error: {e}")
        return jsonify({'success': False, 'error': 'An error occurred while generating questions'})

@app.route('/api/session/<session_id>/answer', methods=['POST'])
def api_submit_answer(session_id):
    """API endpoint to submit an answer"""
    data = request.get_json()
    answer = data.get('answer')  # 'left' or 'right'
    
    # Check if this is a player mode quiz with player choice mapping
    player_choice = data.get('player_choice')  # Which actual player they chose
    
    if player_choice:
        # Use the player mode submission method
        result = session_manager.submit_player_answer(session_id, answer, player_choice)
    else:
        # Use regular submission method
        result = session_manager.submit_answer(session_id, answer)
    
    if result is None:
        return jsonify({'success': False, 'error': 'Session not found'})
    
    return jsonify(result)

@app.route('/api/session/<session_id>')
def api_get_session(session_id):
    """API endpoint to get session data"""
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'error': 'Session not found'}), 404
    return jsonify(session_data)

@app.route('/api/session/<session_id>', methods=['PATCH'])
def api_update_session(session_id):
    """API endpoint to update session data"""
    data = request.get_json()
    
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'error': 'Session not found'}), 404
    
    # Update player name if provided
    if 'player_name' in data:
        session_data['player_name'] = data['player_name']
        success = session_manager.update_session(session_id, session_data)
        if not success:
            return jsonify({'error': 'Failed to update session'}), 500
    
    return jsonify({'success': True})

@app.route('/api/quizzes')
def api_list_quizzes():
    """API endpoint to list all available quizzes"""
    quizzes = []
    for filename in os.listdir('quizzes'):
        if filename.endswith('.json'):
            quiz_id = filename[:-5]  # Remove .json extension
            quiz_data = load_quiz(quiz_id)
            if quiz_data:
                quizzes.append({
                    'id': quiz_id,
                    'title': quiz_data['title'],
                    'description': quiz_data.get('description', ''),
                    'question_count': len(quiz_data['questions']),
                    'type': quiz_data.get('type', 'thisorthat')  # Default to this or that
                })
    return jsonify(quizzes)

@app.route('/api/results/<session_id>')
def api_get_results(session_id):
    """API endpoint to get quiz results"""
    try:
        results_dir = 'results'
        with open(f'{results_dir}/{session_id}.json', 'r') as f:
            results = json.load(f)
        return jsonify(results)
    except FileNotFoundError:
        return jsonify({'error': 'Results not found'}), 404

@app.route('/api/quiz/<quiz_id>/results')
def api_get_quiz_results(quiz_id):
    """API endpoint to get all results for a specific quiz"""
    try:
        results_dir = 'results'
        quiz_results = []
        
        if os.path.exists(results_dir):
            for filename in os.listdir(results_dir):
                if filename.endswith('.json'):
                    with open(f'{results_dir}/{filename}', 'r') as f:
                        result_data = json.load(f)
                        if result_data.get('quiz_id') == quiz_id:
                            quiz_results.append(result_data)
        
        return jsonify(quiz_results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/multiplayer-results/<session_id>')
def api_get_multiplayer_results(session_id):
    """API endpoint to get multiplayer results for a session with timeout handling"""
    try:
        # Get the main session data
        main_session = session_manager.get_session(session_id)
        if not main_session:
            return jsonify({'error': 'Session not found'}), 404
        
        quiz_id = main_session['quiz_id']
        shared_group_id = main_session.get('shared_session_group', session_id)
        
        # Check if main session is complete
        main_session_complete = main_session['current_question'] >= len(main_session['questions'])
        
        # Find all sessions in the same group (completed and in-progress)
        completed_players = []
        in_progress_players = []
        results_dir = 'results'
        
        # Check completed sessions
        if os.path.exists(results_dir):
            for filename in os.listdir(results_dir):
                if filename.endswith('.json'):
                    with open(f'{results_dir}/{filename}', 'r') as f:
                        result_data = json.load(f)
                        if (result_data.get('shared_session_group') == shared_group_id and 
                            result_data.get('quiz_id') == quiz_id):
                            completed_players.append(result_data)
        
        # Check in-progress sessions using session manager
        group_sessions = session_manager.get_sessions_by_group(shared_group_id, quiz_id)
        for session_data in group_sessions:
            if session_data['session_id'] != session_id:  # Don't include self
                # Check if this session is still in progress
                is_in_progress = session_data['current_question'] < len(session_data['questions'])
                
                if is_in_progress:
                    # Calculate how long they've been playing
                    started_at = datetime.fromisoformat(session_data['started_at'])
                    time_elapsed = (datetime.now() - started_at).total_seconds()
                    
                    in_progress_players.append({
                        'session_id': session_data['session_id'],
                        'player_name': session_data.get('player_name', f"Player {session_data['session_id'][:4]}"),
                        'current_question': session_data['current_question'],
                        'total_questions': len(session_data['questions']),
                        'time_elapsed': time_elapsed
                    })
        
        # Sort completed players by completion time
        completed_players.sort(key=lambda x: x['completed_at'])
        
        # Get quiz questions for comparison
        quiz_data = load_quiz(quiz_id)
        
        # Create player mapping for better name handling
        friend_data = None
        if completed_players:
            friend_data = next((p for p in completed_players if p['session_id'] != session_id), None)
        
        # If no friend in completed players, check in-progress players for mapping
        if not friend_data and in_progress_players:
            for player in in_progress_players:
                # Find the corresponding session data for this in-progress player
                try:
                    with open(f'play_sessions/{player["session_id"]}.json', 'r') as f:
                        friend_session_data = json.load(f)
                        friend_data = friend_session_data
                        break
                except:
                    continue
        
        player_mapping = get_player_mapping(main_session, friend_data)
        
        # Determine waiting status
        waiting_for_friends = len(in_progress_players) > 0 and main_session_complete
        
        return jsonify({
            'session_id': session_id,
            'quiz_id': quiz_id,
            'quiz_title': main_session['quiz_title'],
            'quiz_type': quiz_data.get('type', 'thisorthat') if quiz_data else 'thisorthat',
            'total_questions': len(main_session['questions']),
            'questions': quiz_data['questions'] if quiz_data else main_session['questions'],
            'players': completed_players,
            'in_progress_players': in_progress_players,
            'shared_group_id': shared_group_id,
            'waiting_for_friends': waiting_for_friends,
            'main_player_name': main_session.get('player_name', f"Player {session_id[:4]}"),
            'player_mapping': player_mapping,
            'debug_info': {
                'looking_for_group': shared_group_id,
                'completed_found': len(completed_players),
                'in_progress_found': len(in_progress_players),
                'main_complete': main_session_complete
            }
        })
        
    except FileNotFoundError:
        return jsonify({'error': 'Session not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/next-group-quiz', methods=['POST'])
def api_next_group_quiz():
    """API endpoint to get the next quiz for a shared group (coordinated)"""
    data = request.get_json()
    current_session_id = data.get('current_session_id')
    current_quiz_id = data.get('current_quiz_id')
    player_name = data.get('player_name', 'Anonymous')
    
    # Get current session data
    current_session = session_manager.get_session(current_session_id)
    if not current_session:
        return jsonify({'success': False, 'error': 'Session not found'})
    
    shared_group_id = current_session.get('shared_session_group', current_session_id)
    
    # Check if there's already a "next quiz" chosen for this group
    group_state_file = f'play_sessions/group_{shared_group_id}_next.json'
    
    if os.path.exists(group_state_file):
        # Use the already chosen quiz
        with open(group_state_file, 'r') as f:
            group_state = json.load(f)
        
        next_quiz_id = group_state['next_quiz_id']
        
    else:
        # Choose a new quiz for the group
        quizzes_response = list_all_quizzes()
        available_quizzes = [q for q in quizzes_response if q['id'] != current_quiz_id]
        
        if not available_quizzes:
            return jsonify({'success': False, 'error': 'No other quizzes available'})
        
        # Pick a random quiz
        next_quiz = available_quizzes[int(time.time()) % len(available_quizzes)]  # Deterministic but appears random
        next_quiz_id = next_quiz['id']
        
        # Save the choice for the group
        group_state = {
            'shared_group_id': shared_group_id,
            'next_quiz_id': next_quiz_id,
            'chosen_at': datetime.now().isoformat(),
            'chosen_by': current_session_id
        }
        
        with open(group_state_file, 'w') as f:
            json.dump(group_state, f, indent=2)
    
    # Create new session for this player
    new_session_id = create_play_session(next_quiz_id, shared_group_id, player_name)
    
    if new_session_id:
        # Get quiz title
        quiz_data = load_quiz(next_quiz_id)
        quiz_title = quiz_data['title'] if quiz_data else 'Unknown Quiz'
        
        return jsonify({
            'success': True,
            'session_id': new_session_id,
            'quiz_id': next_quiz_id,
            'quiz_title': quiz_title
        })
    else:
        return jsonify({'success': False, 'error': 'Failed to create session'})

def list_all_quizzes():
    """Helper function to list all quizzes"""
    quizzes = []
    for filename in os.listdir('quizzes'):
        if filename.endswith('.json'):
            quiz_id = filename[:-5]
            quiz_data = load_quiz(quiz_id)
            if quiz_data:
                quizzes.append({
                    'id': quiz_id,
                    'title': quiz_data['title'],
                    'description': quiz_data.get('description', ''),
                    'question_count': len(quiz_data['questions']),
                    'type': quiz_data.get('type', 'thisorthat')  # Default to this or that
                })
    return quizzes

@app.route('/api/session-status/<session_id>')
def api_session_status(session_id):
    """API endpoint to get session status and check for friends"""
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'success': False, 'error': 'Session not found'}), 404
    
    quiz_id = session_data['quiz_id']
    shared_group_id = session_data.get('shared_session_group', session_id)
    
    # Find all sessions in the same group using session manager
    group_sessions = []
    all_group_sessions = session_manager.get_sessions_by_group(shared_group_id, quiz_id)
    
    for other_session in all_group_sessions:
        group_sessions.append({
            'session_id': other_session['session_id'],
            'player_name': other_session.get('player_name', f"Player {other_session['session_id'][:4]}"),
            'current_question': other_session['current_question'],
            'total_questions': len(other_session['questions']),
            'is_complete': other_session['current_question'] >= len(other_session['questions'])
        })
    
    # Separate current session from others
    current_session = next((s for s in group_sessions if s['session_id'] == session_id), None)
    friend_sessions = [s for s in group_sessions if s['session_id'] != session_id]
    
    return jsonify({
        'success': True,
        'current_session': current_session,
        'friend_sessions': friend_sessions,
        'has_friends': len(friend_sessions) > 0,
        'friends_playing': len([s for s in friend_sessions if not s['is_complete']]) > 0
    })

def get_player_mapping(session_data, friend_data=None):
    """
    Create a mapping for player mode quizzes where Player 1/Player 2 need to be mapped to actual names
    """
    my_name = session_data.get('player_name', f"Player {session_data['session_id'][:4]}")
    
    if friend_data:
        friend_name = friend_data.get('player_name', f"Player {friend_data['session_id'][:4]}")
        
        # Determine who is Player 1 and who is Player 2 based on session creation time
        # This creates a CONSISTENT mapping regardless of who is viewing
        my_time = session_data.get('started_at', '')
        friend_time = friend_data.get('started_at', '')
        
        if my_time < friend_time:  # I started first, so I'm Player 1
            return {
                'Player 1': my_name,
                'Player 2': friend_name,
                'my_player_number': 1,
                'friend_player_number': 2,
                'my_name': my_name,
                'friend_name': friend_name,
                'my_session_id': session_data['session_id'],
                'friend_session_id': friend_data['session_id']
            }
        else:  # Friend started first, so they're Player 1
            return {
                'Player 1': friend_name,
                'Player 2': my_name,
                'my_player_number': 2,
                'friend_player_number': 1,
                'my_name': my_name,
                'friend_name': friend_name,
                'my_session_id': session_data['session_id'],
                'friend_session_id': friend_data['session_id']
            }
    else:
        # Solo play or friend not available
        return {
            'Player 1': my_name,
            'Player 2': 'Your Friend',
            'my_player_number': 1,
            'friend_player_number': 2,
            'my_name': my_name,
            'friend_name': 'Your Friend',
            'my_session_id': session_data['session_id'],
            'friend_session_id': None
        }

# Global state for quiz coordination (persistent for longer sessions)
quiz_requests = {}  # session_id -> {requester_name, timestamp, response}
player_ready_state = {}  # session_id -> {ready_players: set, timestamp}

def cleanup_old_states():
    """Clean up old states to prevent memory leaks"""
    current_time = time.time()
    
    # Clean up quiz requests older than 5 minutes
    to_remove = []
    for key, data in quiz_requests.items():
        try:
            timestamp = datetime.fromisoformat(data['timestamp']).timestamp()
            if current_time - timestamp > 300:  # 5 minutes
                to_remove.append(key)
        except:
            to_remove.append(key)
    
    for key in to_remove:
        del quiz_requests[key]
    
    # Clean up ready states older than 10 minutes
    to_remove = []
    for key, data in player_ready_state.items():
        try:
            if 'timestamp' in data:
                timestamp = data['timestamp']
                if current_time - timestamp > 600:  # 10 minutes
                    to_remove.append(key)
        except:
            pass
    
    for key in to_remove:
        del player_ready_state[key]

@app.route('/api/game-state/<session_id>')
def api_get_game_state(session_id):
    """API endpoint to check if both players are connected and ready"""
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'success': False, 'error': 'Session not found'}), 404
    
    quiz_id = session_data['quiz_id']
    shared_group_id = session_data.get('shared_session_group', session_id)
    
    # Find all sessions in the same group using session manager
    group_sessions = session_manager.get_sessions_by_group(shared_group_id, quiz_id)
    
    # Check readiness state
    ready_players = player_ready_state.get(shared_group_id, {}).get('ready_players', set())
    
    return jsonify({
        'success': True,
        'has_friend': len(group_sessions) > 1,
        'both_ready': len(ready_players) >= 2,
        'player_names': [s.get('player_name', f"Player {s['session_id'][:4]}") for s in group_sessions],
        'ready_count': len(ready_players)
    })

@app.route('/api/player-ready', methods=['POST'])
def api_player_ready():
    """API endpoint to signal that a player is ready to start"""
    # Clean up old states periodically
    cleanup_old_states()
    
    data = request.get_json()
    session_id = data.get('session_id')
    
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'success': False, 'error': 'Session not found'}), 404
    
    shared_group_id = session_data.get('shared_session_group', session_id)
    
    # Initialize ready state if not exists
    if shared_group_id not in player_ready_state:
        player_ready_state[shared_group_id] = {
            'ready_players': set(),
            'timestamp': time.time()
        }
    
    # Add this player to ready set and update timestamp
    player_ready_state[shared_group_id]['ready_players'].add(session_id)
    player_ready_state[shared_group_id]['timestamp'] = time.time()
    
    # Check if both players are ready
    both_ready = len(player_ready_state[shared_group_id]['ready_players']) >= 2
    
    return jsonify({
        'success': True,
        'both_ready': both_ready,
        'ready_count': len(player_ready_state[shared_group_id]['ready_players'])
    })

@app.route('/api/request-new-quiz', methods=['POST'])
def api_request_new_quiz():
    """API endpoint to request permission for a new quiz"""
    data = request.get_json()
    session_id = data.get('session_id')
    requester_name = data.get('requester_name', 'Anonymous')
    
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'success': False, 'error': 'Session not found'}), 404
    
    shared_group_id = session_data.get('shared_session_group', session_id)
    
    # Store the request
    quiz_requests[shared_group_id] = {
        'requester_name': requester_name,
        'timestamp': datetime.now().isoformat(),
        'response': None
    }
    
    return jsonify({'success': True})

@app.route('/api/pending-quiz-request/<session_id>')
def api_get_pending_quiz_request(session_id):
    """API endpoint to check for pending quiz requests"""
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'has_request': False})
    
    shared_group_id = session_data.get('shared_session_group', session_id)
    
    if shared_group_id in quiz_requests:
        request_data = quiz_requests[shared_group_id]
        # Only show if response is still pending
        if request_data['response'] is None:
            return jsonify({
                'has_request': True,
                'requester_name': request_data['requester_name']
            })
    
    return jsonify({'has_request': False})

@app.route('/api/respond-quiz-request', methods=['POST'])
def api_respond_quiz_request():
    """API endpoint to respond to a quiz request"""
    data = request.get_json()
    session_id = data.get('session_id')
    accepted = data.get('accepted', False)
    
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'success': False, 'error': 'Session not found'}), 404
    
    shared_group_id = session_data.get('shared_session_group', session_id)
    
    # Update the request with response
    if shared_group_id in quiz_requests:
        quiz_requests[shared_group_id]['response'] = accepted
    
    return jsonify({'success': True})

@app.route('/api/quiz-request-status/<session_id>')
def api_get_quiz_request_status(session_id):
    """API endpoint to get the status of a quiz request"""
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'response': None})
    
    shared_group_id = session_data.get('shared_session_group', session_id)
    
    if shared_group_id in quiz_requests:
        return jsonify({
            'response': quiz_requests[shared_group_id]['response']
        })
    
    return jsonify({'response': None})

@app.route('/api/health')
def api_health():
    """API endpoint for health check and session statistics"""
    try:
        return jsonify({
            'status': 'healthy',
            'active_sessions': session_manager.get_session_count(),
            'timestamp': datetime.now().isoformat(),
            'session_timeout': session_manager.SESSION_TIMEOUT,
            'cleanup_interval': session_manager.CLEANUP_INTERVAL,
            'save_interval': session_manager.SAVE_INTERVAL
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/player-name', methods=['GET', 'POST'])
def api_player_name():
    """API endpoint for player name management"""
    if request.method == 'GET':
        # Get stored player name
        return jsonify({
            'success': True,
            'player_name': ''  # Frontend will handle localStorage
        })
    else:
        # Store player name (could be used for server-side tracking if needed)
        data = request.get_json()
        player_name = data.get('player_name', '')
        return jsonify({
            'success': True,
            'player_name': player_name
        })

@app.route('/api/player-mapping/<session_id>')
def api_get_player_mapping(session_id):
    """API endpoint to get player mapping for a session"""
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'success': False, 'error': 'Session not found'}), 404
    
    quiz_id = session_data['quiz_id']
    shared_group_id = session_data.get('shared_session_group', session_id)
    
    # Find all sessions in the same group
    group_sessions = session_manager.get_sessions_by_group(shared_group_id, quiz_id)
    
    friend_data = None
    for session in group_sessions:
        if session['session_id'] != session_id:
            friend_data = session
            break
    
    # Get player mapping
    player_mapping = get_player_mapping(session_data, friend_data)
    
    return jsonify({
        'success': True,
        'player_mapping': player_mapping,
        'has_friend': friend_data is not None,
        'my_name': player_mapping['my_name'],
        'friend_name': player_mapping['friend_name'],
        'my_player_number': player_mapping['my_player_number']
    })

@app.route('/api/heartbeat/<session_id>', methods=['POST'])
def api_heartbeat(session_id):
    """API endpoint to update player heartbeat"""
    session_manager.update_player_heartbeat(session_id)
    return jsonify({'success': True})

@app.route('/api/check-partner-status/<session_id>')
def api_check_partner_status(session_id):
    """API endpoint to check if partner has disconnected"""
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'success': False, 'error': 'Session not found'})
    
    partner_disconnected = session_data.get('partner_disconnected', False)
    
    return jsonify({
        'success': True,
        'partner_disconnected': partner_disconnected,
        'disconnect_time': session_data.get('partner_disconnect_time'),
        'message': 'Your partner has left the game' if partner_disconnected else None
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # fallback to 5000 locally
    app.run(host='0.0.0.0', port=port)