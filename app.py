from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_caching import Cache
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import uuid
import os
import time
import logging
from datetime import datetime, timedelta
import base64
from PIL import Image
import io
import pytesseract
import re
import requests
from concurrent.futures import ThreadPoolExecutor, wait
import atexit
from functools import lru_cache
import diskcache
import gevent # Add gevent import
from gevent.timeout import Timeout # For timeouts with gevent
import random

from config import config
from session_manager import OptimizedSessionManager

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(config[os.environ.get('FLASK_ENV', 'default')])

# Enable CORS for better API access
CORS(app)

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent' if os.environ.get('FLASK_ENV') == 'production' else None)

# Initialize caching
cache = Cache(app, config={
    'CACHE_TYPE': 'FileSystemCache',
    'CACHE_DIR': 'cache',
    'CACHE_DEFAULT_TIMEOUT': 300,
    'CACHE_THRESHOLD': 1000
})

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize session manager
session_manager = OptimizedSessionManager(
    cache_dir=app.config['SESSION_STORAGE_DIR'],
    timeout=app.config['SESSION_TIMEOUT']
)

# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=app.config['MAX_WORKERS'])

# LLM connection pooling
class LLMClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {app.config['DEEPINFRA_API_KEY']}",
            "Content-Type": "application/json"
        })
        
    def call(self, messages, max_tokens=1000, temperature=0.7):
        """Call LLM with connection pooling"""
        try:
            data = {
                "model": app.config['LLM_MODEL_NAME'],
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            response = self.session.post(
                f"{app.config['DEEPINFRA_BASE_URL']}chat/completions",
                json=data,
                timeout=app.config['REQUEST_TIMEOUT']
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                logger.error(f"LLM API Error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return None

# Global LLM client instance
llm_client = LLMClient()

# Ensure directories exist
for dir_name in ['quizzes', 'uploads', 'results', 'cache', 'session_storage']:
    os.makedirs(dir_name, exist_ok=True)

# Cleanup on exit
def cleanup():
    """Cleanup resources on exit"""
    session_manager.close()
    executor.shutdown(wait=True)
    
atexit.register(cleanup)

# Helper functions
@lru_cache(maxsize=100)
def load_quiz(quiz_id):
    """Load quiz data with caching"""
    try:
        with open(f'quizzes/{quiz_id}.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def save_quiz(quiz_data):
    """Save quiz data"""
    quiz_id = str(uuid.uuid4())[:8]
    quiz_data['id'] = quiz_id
    quiz_data['created_at'] = datetime.now().isoformat()
    
    with open(f'quizzes/{quiz_id}.json', 'w') as f:
        json.dump(quiz_data, f, indent=2)
    
    # Clear quiz cache
    load_quiz.cache_clear()
    
    return quiz_id

def generate_question_with_llm(topic, quiz_type="thisorthat", existing_questions=None, count=1):
    """Generate questions using LLM"""
    try:
        # Build appropriate prompt based on quiz type
        if count == 1:
            prompt = _build_single_question_prompt(topic, quiz_type, existing_questions)
            response = llm_client.call([{"role": "user", "content": prompt}], 
                                     max_tokens=300, temperature=0.8)
            if response:
                return _parse_single_question(response, quiz_type)
        else:
            prompt = _build_batch_question_prompt(topic, quiz_type, existing_questions, count)
            response = llm_client.call([{"role": "user", "content": prompt}], 
                                     max_tokens=1500, temperature=0.8)
            if response:
                return _parse_batch_questions(response, quiz_type)
                
    except Exception as e:
        logger.error(f"Question generation error: {e}")
        
    return None

def _build_single_question_prompt(topic, quiz_type, existing_questions):
    """Build prompt for single question generation"""
    base_prompts = {
        "competition": f"""Generate a knowledge-based competition question about {topic}. 
Return ONLY a JSON object with this exact format:
{{
    "prompt": "Your question here?",
    "option1": "First answer option",
    "option2": "Second answer option", 
    "correct_answer": "option1" or "option2"
}}

Make it challenging but fair. Question prompt should be 5-8 words max. Answer options should be short (1-3 words).
IMPORTANT: Randomly choose which option is correct.""",

        "player": f"""Generate a "Player 1 vs Player 2" comparison question about {topic}.
Return ONLY a JSON object with this exact format:
{{
    "prompt": "Your question here?",
    "option1": "Player 1",
    "option2": "Player 2"
}}

The question should be about who is more likely to do something. Question prompt should be 5-8 words max.""",

        "thisorthat": f"""Generate a "this or that" preference question about {topic}.
Return ONLY a JSON object with this exact format:
{{
    "prompt": "Your question here?", 
    "option1": "First preference option",
    "option2": "Second preference option"
}}

Make it fun and engaging. Question prompt should be 5-8 words max. Options should be short (1-3 words)."""
    }
    
    prompt = base_prompts.get(quiz_type, base_prompts["thisorthat"])
    
    if existing_questions:
        existing_prompts = [q.get('prompt', '') for q in existing_questions[:3]]
        prompt += f"\n\nAvoid creating questions similar to: {existing_prompts}"
        
    return prompt

def _build_batch_question_prompt(topic, quiz_type, existing_questions, count):
    """Build prompt for batch question generation"""
    # Define the base structure for each question type
    this_or_that_format = '{"prompt": "Question text?", "option1": "Option A", "option2": "Option B"}'
    player_format = '{"prompt": "Player comparison?", "option1": "Player 1", "option2": "Player 2"}'
    competition_format = '{"prompt": "Knowledge question?", "option1": "Answer 1", "option2": "Answer 2", "correct_answer": "option1"}'

    base_prompts = {
        "competition": f"""Generate {count} knowledge-based competition questions about {topic}. 
Return ONLY a JSON array of questions. Each object in the array must follow this exact format: {competition_format}. 
Mix up which option is correct for each question.""",

        "player": f"""Generate {count} "Player 1 vs Player 2" comparison questions about {topic}.
Return ONLY a JSON array of questions. Each object in the array must follow this exact format: {player_format}.""",

        "thisorthat": f"""Generate {count} "this or that" preference questions about {topic}.
Return ONLY a JSON array of questions. Each object in the array must follow this exact format: {this_or_that_format}."""
    }
    
    prompt = base_prompts.get(quiz_type, base_prompts["thisorthat"])
    
    if existing_questions:
        existing_prompts = [q.get('prompt', '') for q in existing_questions[:5]]
        prompt += f"\n\nAvoid creating questions similar to: {existing_prompts}"
        
    return prompt

def _parse_single_question(response, quiz_type):
    """Parse single question response"""
    try:
        import json
        import random
        
        start = response.find('{')
        end = response.rfind('}') + 1
        
        if start != -1 and end != 0:
            json_str = response[start:end]
            question_data = json.loads(json_str)
            
            # Add randomization for competition questions
            if quiz_type == "competition" and random.random() < 0.5:
                # Swap options
                question_data['option1'], question_data['option2'] = \
                    question_data['option2'], question_data['option1']
                question_data['correct_answer'] = \
                    'option2' if question_data['correct_answer'] == 'option1' else 'option1'
                    
            return question_data
            
    except json.JSONDecodeError:
        pass
    return None

def _parse_batch_questions(response, quiz_type):
    """Parse batch questions response"""
    try:
        import json # Already imported at top level, but fine here for clarity
        import random

        if not response:
            logger.warning("Empty response received for batch question parsing.")
            return None

        logger.info(f"LLM Batch API response: {response[:500]}...") # Log first 500 chars

        # Attempt to find JSON array, potentially wrapped in markdown
        match = re.search(r'```json\n(\s*[\[\{].*[\}\]]\s*)\n```', response, re.DOTALL)
        json_str = ""
        if match:
            json_str = match.group(1).strip()
        else:
            # Fallback to finding the first '[' and last ']'
            start = response.find('[')
            end = response.rfind(']') + 1
            if start != -1 and end > start:
                json_str = response[start:end]
        
        if json_str:
            questions = json.loads(json_str)
            
            valid_questions = []
            if isinstance(questions, list): # Ensure we have a list
                for q in questions:
                    if isinstance(q, dict) and 'prompt' in q and 'option1' in q and 'option2' in q:
                        # Add randomization for competition
                        if quiz_type == "competition" and 'correct_answer' in q and random.random() < 0.5:
                            q['option1'], q['option2'] = q['option2'], q['option1']
                            q['correct_answer'] = \
                                'option2' if q['correct_answer'] == 'option1' else 'option1'
                        valid_questions.append(q)
                logger.info(f"Successfully parsed {len(valid_questions)} batch questions from LLM response.")
                return valid_questions[:10]  # Limit to 10
            else:
                logger.warning(f"Parsed JSON is not a list for batch questions. Type: {type(questions)}")
                return None
        else:
            logger.warning("No JSON array found in LLM batch response.")
            return None
            
    except json.JSONDecodeError as e:
        logger.error(f"JSONDecodeError parsing LLM batch response: {e}. Response was: {response[:500]}...")
        return None
    except Exception as e:
        logger.error(f"Generic error parsing LLM batch response: {e}")
        return None

def extract_questions_from_image(image_path):
    """Extract questions from image using LLM vision or OCR fallback"""
    try:
        # Try LLM vision first
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
        
        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": """Analyze this image and extract any "this or that" questions. 
Return a JSON array of questions in this format:
[{"prompt": "Question?", "option1": "Option 1", "option2": "Option 2"}]
Return ONLY the JSON array."""
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                }
            ]
        }]
        
        response = llm_client.call(messages, max_tokens=800, temperature=0.7)
        
        if response:
            logger.info(f"LLM Vision API response for image extraction: {response[:500]}...") # Log first 500 chars
            try:
                # Attempt to find JSON array, potentially wrapped in markdown
                match = re.search(r'```json\n(\s*[\[\{].*[\}\]]\s*)\n```', response, re.DOTALL)
                json_str = ""
                if match:
                    json_str = match.group(1).strip()
                else:
                    # Fallback to finding the first '[' and last ']'
                    start = response.find('[')
                    end = response.rfind(']') + 1
                    if start != -1 and end > start:
                        json_str = response[start:end]
                
                if json_str:
                    questions = json.loads(json_str)
                    valid_questions = [q for q in questions if isinstance(q, dict) and 'option1' in q and 'option2' in q]
                    logger.info(f"Successfully parsed {len(valid_questions)} questions from LLM vision response.")
                    return valid_questions[:10] # Limit to 10
                else:
                    logger.warning("No JSON array found in LLM vision response.")
            except json.JSONDecodeError as e:
                logger.error(f"JSONDecodeError parsing LLM vision response: {e}. Response was: {response[:500]}...")
            except Exception as e:
                logger.error(f"Generic error parsing LLM vision response: {e}")
                pass # Fall through to OCR
                
    except Exception as e:
        logger.error(f"LLM image processing error: {e}")
        
    # Fallback to OCR
    try:
        text = pytesseract.image_to_string(Image.open(image_path))
        patterns = [
            r'([^?\n]+?)\s+(?:or|vs|versus)\s+([^?\n]+?)(?:\?|$|\n)',
        ]
        
        questions = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                if len(match[0]) > 2 and len(match[1]) > 2:
                    questions.append({
                        'prompt': 'Choose one:',
                        'option1': match[0].strip(),
                        'option2': match[1].strip()
                    })
                    
        return questions[:10]
        
    except Exception as e:
        logger.error(f"OCR Error: {e}")
        return []

# Routes
@app.route('/')
def index():
    """Landing page"""
    preselect_quiz_id = request.args.get('preselect_quiz_id')
    return render_template('index.html', preselect_quiz_id=preselect_quiz_id)

@app.route('/admin')
def admin():
    """Admin interface for creating quizzes"""
    return render_template('admin.html')

@app.route('/results')
def results():
    """Results viewer page"""
    return render_template('results.html')

@app.route('/play/<quiz_id>')
def play_quiz(quiz_id):
    """Start playing a quiz"""
    # Check for test mode
    test_mode = request.args.get('test', 'false').lower() == 'true'
    
    # Check for join request
    shared_session = request.args.get('join')
    if shared_session and not test_mode:
        return redirect(url_for('join_session', session_id=shared_session))
    
    # Load quiz
    quiz_data = load_quiz(quiz_id)
    if not quiz_data:
        return "Quiz not found", 404
    
    # Create session
    player_name = request.args.get('player_name')
    session_id = session_manager.create_session(quiz_id, quiz_data, None, player_name)
    
    # For test mode, mark the session
    if test_mode:
        session_data = session_manager.get_session(session_id)
        session_data['test_mode'] = True
        session_manager.update_session(session_id, session_data)
    
    return redirect(url_for('play_session', session_id=session_id))

@app.route('/join/<session_id>')
def join_session(session_id):
    """Join an existing session"""
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return "Session not found", 404
    
    return render_template('join.html', 
                         session_id=session_id, 
                         quiz_title=session_data['quiz_title'])

@app.route('/session/<session_id>')
def play_session(session_id):
    """Play a specific session"""
    session_data_from_store = session_manager.get_session(session_id)
    if not session_data_from_store:
        return "Session not found", 404

    # Determine the name of the player this page is being rendered for
    player_name_for_this_page = request.args.get('pn') 

    # If 'pn' is not in args, it might be Player 1 (creator) loading the page initially.
    # Player 1's name is stored in session_data_from_store['player_name'] (creator's name).
    if not player_name_for_this_page:
        player_name_for_this_page = session_data_from_store.get('player_name')
        # If still no name (e.g. direct access by a non-player after session setup),
        # it's harder to determine. Defaulting to the primary session player_name.
        # This assumes the first player to hit /play/<quiz_id> without 'join' or 'pn' is the creator.

    # Create a copy of session_data to pass to template, and inject the specific player's name
    template_display_session = session_data_from_store.copy()
    template_display_session['this_player_name'] = player_name_for_this_page # Critical for client-side identity

    # Multiplayer enforcement: only allow quiz to start if two players are present, unless test_mode
    test_mode = template_display_session.get('test_mode', False)
    players_in_session = template_display_session.get('players', [])
    # The waiting_for_friend flag is more about initial state before JS and sockets take over.
    # The actual UI (waiting/ready/quiz) will be controlled by JS based on socket events.
    waiting_for_friend_flag_initial = not test_mode and len(players_in_session) < 2 and not player_name_for_this_page # Crude initial check

    return render_template('play.html', session=template_display_session, waiting_for_friend=waiting_for_friend_flag_initial)

@app.route('/multiplayer-results/<session_id>')
def multiplayer_results(session_id):
    """Multiplayer results comparison page"""
    session_data = session_manager.get_session(session_id)
    
    if not session_data:
        # Try loading from results
        try:
            with open(f'results/{session_id}.json', 'r') as f:
                result_data = json.load(f)
                session_data = {'session_id': session_id}
        except FileNotFoundError:
            return "Session not found", 404
    
    return render_template('multiplayer-results.html', 
                         session_id=session_id,
                         quiz_title=session_data.get('quiz_title', 'Quiz Results'))

# API Routes
@app.route('/api/create_quiz', methods=['POST'])
def api_create_quiz():
    """Create a new quiz"""
    data = request.get_json()
    
    quiz_data = {
        'title': data.get('title', 'Untitled Quiz'),
        'description': data.get('description', ''),
        'type': data.get('type', 'thisorthat'),
        'questions': data.get('questions', [])
    }
    
    quiz_id = save_quiz(quiz_data)
    
    return jsonify({
        'success': True, 
        'quiz_id': quiz_id,
        'test_url': url_for('play_quiz', quiz_id=quiz_id, test='true', _external=True),
        'share_url': url_for('play_quiz', quiz_id=quiz_id, _external=True)
    })

@app.route('/api/session/<session_id>')
@cache.memoize(timeout=5)  # Cache for 5 seconds
def api_get_session(session_id):
    """Get session data"""
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'error': 'Session not found'}), 404
    return jsonify(session_data)

@app.route('/api/session/<session_id>/answer', methods=['POST'])
def api_submit_answer(session_id):
    """Submit an answer"""
    try:
        data = request.get_json()
        answer = data.get('answer')
        player_choice = data.get('player_choice')
        player_name = data.get('player_name', 'Unknown Player')
        question_index = data.get('question_index') # Get question_index from request

        if question_index is None: # Validate question_index
            return jsonify({'success': False, 'error': 'question_index is required'}), 400
        
        # Pass question_index to session_manager
        result = session_manager.submit_answer(session_id, answer, question_index, player_choice, player_name)
        
        if result is None:
            return jsonify({'success': False, 'error': 'Session not found'}), 404
        
        # Clear session cache
        cache.delete_memoized(api_get_session, session_id)
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error submitting answer for session {session_id}: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to submit answer: {str(e)}'}), 500

@app.route('/api/upload_image', methods=['POST'])
def api_upload_image():
    """Upload and process image using gevent.spawn"""
    logger.info(f"[api_upload_image] Received request. Files in request: {list(request.files.keys())}")

    if 'image' not in request.files:
        logger.error("[api_upload_image] 'image' not in request.files")
        return jsonify({'success': False, 'error': 'No image file found in the request.'}), 400
    
    file = request.files['image']
    if file.filename == '':
        logger.error("[api_upload_image] Filename is empty.")
        return jsonify({'success': False, 'error': 'No image selected (empty filename).'}), 400
    
    logger.info(f"[api_upload_image] Processing file: {file.filename}")
    filepath = None
    try:
        filename = str(uuid.uuid4()) + '_' + file.filename
        upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder, exist_ok=True)
            logger.info(f"Created upload folder: {upload_folder}")

        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        logger.info(f"[api_upload_image] File saved to: {filepath}")
        
        logger.info(f"[api_upload_image] Spawning extract_questions_from_image with gevent.")
        # Spawn the task. extract_questions_from_image itself is a blocking function.
        greenlet = gevent.spawn(extract_questions_from_image, filepath)
        
        timeout_seconds = app.config.get('LLM_REQUEST_TIMEOUT', 60)
        
        try:
            logger.info(f"[api_upload_image] Waiting for greenlet to complete (timeout: {timeout_seconds}s).")
            questions = greenlet.join(timeout=timeout_seconds) # Wait for the greenlet to finish
            
            if greenlet.successful(): # Check if the greenlet completed without an unhandled exception
                questions = greenlet.value # Get the return value
                logger.info(f"[api_upload_image] Gevent task completed. Found {len(questions) if questions else 0} questions.")
                return jsonify({'success': True, 'questions': questions if questions else []})
            else:
                # If greenlet.successful() is false, it might be due to an exception within the greenlet or timeout not being hit (e.g. killed)
                # greenlet.exception might contain the exception
                if greenlet.exception:
                    logger.error(f"[api_upload_image] Gevent task failed with exception: {greenlet.exception}", exc_info=greenlet.exception)
                    raise greenlet.exception # Re-raise to be caught by the outer try-except
                else:
                    # This case is less likely if join timed out, as join would return None then.
                    logger.error("[api_upload_image] Gevent task did not complete successfully but no exception found. TIMEOUT likely occurred.")
                    return jsonify({'success': False, 'error': 'Image processing timed out (gevent).'}), 504

        except Timeout: # This is gevent.timeout.Timeout, if greenlet.join itself is timed out by an outer gevent.Timeout
            logger.error(f"[api_upload_image] Gevent join timed out after {timeout_seconds}s.")
            greenlet.kill() # Ensure the greenlet is killed if it's still running
            return jsonify({'success': False, 'error': 'Image processing timed out (gevent join).'}), 504
        except gevent.timeout.Timeout: # Explicitly catch gevent.timeout.Timeout
            logger.error(f"[api_upload_image] Gevent task explicitly timed out after {timeout_seconds}s.")
            greenlet.kill()
            return jsonify({'success': False, 'error': 'Image processing timed out (gevent task).'}), 504

    except Exception as e:
        logger.error(f"[api_upload_image] An unexpected error occurred: {str(e)}", exc_info=True)
        # Ensure filepath is defined before trying to use it in an error message if error occurred before its assignment
        f_path_msg = f" for {filepath}" if filepath else ""
        return jsonify({'success': False, 'error': f'An unexpected server error occurred{f_path_msg}: {str(e)}'}), 500
    finally:
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
                logger.info(f"[api_upload_image] Cleaned up file: {filepath}")
            except Exception as e_remove:
                logger.error(f"[api_upload_image] Error cleaning up file {filepath}: {str(e_remove)}")

@app.route('/api/generate_question', methods=['POST'])
def api_generate_question():
    """Generate questions using LLM"""
    data = request.get_json()
    topic = data.get('topic', '').strip()
    quiz_type = data.get('quiz_type', 'thisorthat')
    existing_questions = data.get('existing_questions', [])
    count = data.get('count', 1)
    is_player_mode = data.get('is_player_mode', False)
        
    if not topic:
        return jsonify({'success': False, 'error': 'Topic is required'})
        
    if is_player_mode and quiz_type == 'thisorthat':
        quiz_type = 'player'
    
    logger.info(f"[api_generate_question] DIAGNOSTIC (SYNC): Request: topic='{topic}', type='{quiz_type}', count={count}")

    try:
        # --- TEMPORARY DIAGNOSTIC: Call synchronously --- 
        logger.info("[api_generate_question] DIAGNOSTIC: Calling generate_question_with_llm SYNCHRONOUSLY.")
        result = generate_question_with_llm(topic, quiz_type, existing_questions, count)
        logger.info(f"[api_generate_question] DIAGNOSTIC: Synchronous call returned. Result type: {type(result)}")
        # --- END TEMPORARY DIAGNOSTIC ---

        # Process result from synchronous call
        if result:
            if count == 1 and isinstance(result, dict):
                logger.info("[api_generate_question] DIAGNOSTIC: Successfully generated single question (sync).")
                return jsonify({'success': True, 'question': result})
            elif count > 1 and isinstance(result, list):
                logger.info(f"[api_generate_question] DIAGNOSTIC: Successfully generated batch of {len(result)} questions (sync).")
                return jsonify({'success': True, 'questions': result, 'count': len(result)})
            else:
                logger.warning(f"[api_generate_question] DIAGNOSTIC: Unexpected result type/structure (sync). Count: {count}, Type: {type(result)}")
                return jsonify({'success': False, 'error': 'AI generated an unexpected data structure (sync).'}), 500
        else:
            logger.warning("[api_generate_question] DIAGNOSTIC: Task returned None or empty (sync).")
            return jsonify({'success': False, 'error': 'AI failed to generate questions (empty result, sync).'})

    except Exception as e:
        logger.error(f"[api_generate_question] DIAGNOSTIC (SYNC) Error: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': f'Failed to generate questions (sync): {str(e)}'}), 500

@app.route('/api/quizzes')
@cache.cached(timeout=60)  # Cache for 1 minute
def api_list_quizzes():
    """List all available quizzes"""
    quizzes = []
    
    for filename in sorted(os.listdir('quizzes'), reverse=True):
        if filename.endswith('.json'):
            quiz_id = filename[:-5]
            quiz_data = load_quiz(quiz_id)
            if quiz_data:
                quizzes.append({
                    'id': quiz_id,
                    'title': quiz_data['title'],
                    'description': quiz_data.get('description', ''),
                    'question_count': len(quiz_data['questions']),
                    'type': quiz_data.get('type', 'thisorthat'),
                    'created_at': quiz_data.get('created_at', '')
                })
    
    return jsonify(quizzes)

@app.route('/api/results/<session_id>')
def api_get_results(session_id):
    """Get quiz results"""
    try:
        with open(f'results/{session_id}.json', 'r') as f:
            results = json.load(f)
        return jsonify(results)
    except FileNotFoundError:
        return jsonify({'error': 'Results not found'}), 404

@app.route('/api/multiplayer-results/<session_id>')
def api_get_multiplayer_results(session_id):
    """Get multiplayer results for comparison"""
    try:
        # Get main session
        main_session = session_manager.get_session(session_id)
        if not main_session:
            # Try loading from results
            with open(f'results/{session_id}.json', 'r') as f:
                main_result = json.load(f)
                main_session = {
                    'session_id': session_id,
                    'quiz_id': main_result['quiz_id'],
                    'quiz_title': main_result['quiz_title'],
                    'players': main_result.get('players', []),
                    'player_answers': main_result.get('player_answers', {}),
                    'current_question': main_result['total_questions']
                }
        
        # Load quiz data
        quiz_id = main_session['quiz_id']
        quiz_data = load_quiz(quiz_id)
        
        player_answers_data = main_session.get('player_answers', {})
        logger.info(f"[api_get_multiplayer_results] For session {session_id}, player_answers being sent: {json.dumps(player_answers_data, indent=2)}") # Detailed log
        logger.info(f"[api_get_multiplayer_results] For session {session_id}, quiz questions count: {len(quiz_data['questions'] if quiz_data else [])}")

        player_completion_status = main_session.get('player_completion_status', {})
        session_players = main_session.get('players', [])
        
        all_players_completed = False
        if not session_players: # No players in session, so not all completed
            all_players_completed = False
        elif len(session_players) == 1: # Single player mode
            # Considered complete if the single player is in completion_status and is True
            all_players_completed = player_completion_status.get(session_players[0], False)
        else: # Multiplayer mode (2 or more players)
            # All listed players must be in completion_status and be True
            all_players_completed = all(player_completion_status.get(p_name, False) for p_name in session_players)

        logger.info(f"[api_get_multiplayer_results] Session {session_id}: Players: {session_players}, Completion Status: {player_completion_status}, All Completed: {all_players_completed}")

        return jsonify({
            'session_id': session_id,
            'quiz_id': quiz_id,
            'quiz_title': main_session.get('quiz_title', 'Quiz'),
            'quiz_type': quiz_data.get('type', 'thisorthat') if quiz_data else 'thisorthat',
            'questions': quiz_data['questions'] if quiz_data else [],
            'players': session_players, # Use the retrieved list
            'player_answers': player_answers_data, # Use the logged variable
            'player_completion_status': player_completion_status,
            'all_players_completed': all_players_completed
        })
        
    except Exception as e:
        logger.error(f"Multiplayer results error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/join-session', methods=['POST'])
def api_join_session():
    """Join an existing multiplayer session"""
    data = request.get_json()
    session_id = data.get('session_id')
    player_name = data.get('player_name')
    
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'success': False, 'error': 'Session not found'}), 404
    
    if 'players' not in session_data:
        session_data['players'] = [session_data.get('player_name', 'Player 1')] # Creator is P1
    
    current_players_in_session = session_data['players']
    actual_player_key_in_session = player_name # Default to the name provided

    if player_name and player_name not in current_players_in_session:
        if len(current_players_in_session) < 2:
            current_players_in_session.append(player_name)
            # actual_player_key_in_session is already player_name
        else:
            # Session full, or player_name already exists but is not the one being added.
            # This case should ideally be handled by client not allowing join or server returning error.
            # For now, if they are not in the list and list is full, they can't "become" a player.
            # If the goal is to replace 'Your Friend' or similar, logic would be different.
            # For now, we assume the first two unique names fill the slots.
            pass 
    elif player_name and player_name == current_players_in_session[0] and len(current_players_in_session) == 1:
        # This handles if P1 (e.g. "Lena") tries to join again with the same name "Lena"
        # They should become "Lena 2" if "Lena" is already P1.
        actual_player_key_in_session = player_name + ' 2'
        if len(current_players_in_session) < 2:
            current_players_in_session.append(actual_player_key_in_session)
    # If player_name is already in current_players_in_session and is not the P1-rejoin case,
    # actual_player_key_in_session remains player_name, which is fine (they are rejoining as themselves).

    session_data['players'] = current_players_in_session

    if 'player_answers' not in session_data:
        session_data['player_answers'] = {}
    # Ensure all listed players have an entry, especially the new actual_player_key_in_session
    for p_name_init in session_data['players']:
        if p_name_init not in session_data['player_answers']:
            session_data['player_answers'][p_name_init] = []
            
    if 'players_ready' not in session_data:
        session_data['players_ready'] = {}
    
    session_manager.update_session(session_id, session_data)
    
    cache.delete_memoized(api_get_session, session_id=session_id)
    try: cache.delete_memoized(api_game_state, session_id=session_id)
    except KeyError: pass
    try: cache.delete_memoized(api_player_mapping, session_id=session_id)
    except KeyError: pass

    updated_game_state = get_game_state_data(session_id)
    if updated_game_state:
        socketio.emit('game_state_updated', updated_game_state, room=session_id)
        socketio.emit('player_mapping_updated', get_player_mapping_data(session_id), room=session_id)

    join_url = url_for('play_session', session_id=session_id, pn=actual_player_key_in_session, _external=True)
    return jsonify({'success': True, 
                    'session_id': session_id, 
                    'join_url': join_url,
                    'actual_player_name_in_session': actual_player_key_in_session
                   })

# Helper function to get game state (to avoid duplicating logic from api_game_state)
def get_game_state_data(session_id):
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return None
    
    is_test_mode = session_data.get('test_mode', False)
    players = session_data.get('players', [])
    players_ready_status = session_data.get('players_ready', {})
    
    # 'has_friend' means more than one player is listed in the session.
    # In test mode, this might remain false if only the tester is present.
    has_friend = len(players) > 1
    
    ready_count = sum(1 for p_name in players if players_ready_status.get(p_name, False))
    
    # 'both_ready_for_ui' determines if the UI should indicate that the quiz is ready to start.
    # This is what the 'both_ready' field in the emitted game state will represent.
    both_ready_for_ui = False
    if is_test_mode:
        # In test mode, if there's at least one player (the tester) and they are ready.
        if players and players_ready_status.get(players[0], False): # Assuming tester is players[0]
            both_ready_for_ui = True
    else:
        # Standard multiplayer: all listed players (>=2) must be ready
        if len(players) >= 2 and ready_count == len(players):
            both_ready_for_ui = True
            
    return {
        'has_friend': has_friend,
        'both_ready': both_ready_for_ui, # For UI logic
        'player_names': players,
        'players_ready_status': players_ready_status,
        'is_test_mode': is_test_mode # Send this to client
    }

# Helper function to get player mapping
def get_player_mapping_data(session_id):
    session_data = session_manager.get_session(session_id)
    logger.info(f"[get_player_mapping_data] For session_id: {session_id}") # Log entry
    if not session_data:
        logger.warning(f"[get_player_mapping_data] No session_data found for {session_id}. Returning default mapping.")
        return {'player_mapping': {'Player 1': 'Player 1', 'Player 2': 'Your Friend'}, 'has_friend': False}
    
    # Log the critical parts of session_data used for mapping
    logger.info(f"[get_player_mapping_data] session_data['player_name'] (creator): {session_data.get('player_name')}")
    logger.info(f"[get_player_mapping_data] session_data['players'] list: {session_data.get('players')}")

    players = session_data.get('players', [])
    mapping = {}
    if len(players) > 0:
        mapping['Player 1'] = players[0]
    else:
        # This case means the 'players' list was empty. Fallback to session's original player_name if it exists.
        mapping['Player 1'] = session_data.get('player_name', 'Player 1') 
    
    if len(players) > 1:
        mapping['Player 2'] = players[1]
    else:
        mapping['Player 2'] = 'Your Friend'
    
    has_friend_status = len(players) > 1
    logger.info(f"[get_player_mapping_data] Generated mapping: {mapping}, has_friend: {has_friend_status}")
    return {'player_mapping': mapping, 'has_friend': has_friend_status}

@app.route('/api/player-ready', methods=['POST'])
def api_player_ready():
    data = request.get_json()
    session_id = data.get('session_id')
    player_name = data.get('player_name') # Player signaling readiness

    if not session_id or not player_name:
        return jsonify({'success': False, 'error': 'Session ID and Player Name are required'}), 400

    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'success': False, 'error': 'Session not found'}), 404

    if 'players_ready' not in session_data:
        session_data['players_ready'] = {}
    
    is_test_mode = session_data.get('test_mode', False)
    all_players_list = session_data.get('players', [])
    player_actual_name_in_session = None

    if player_name in all_players_list:
        player_actual_name_in_session = player_name
    else:
        logger.warning(f"[api_player_ready] Player '{player_name}' from request not directly in session players list: {all_players_list}. Session: {session_id}")
        if session_data.get('player_name') == player_name and player_name in all_players_list: # Check original creator name
             player_actual_name_in_session = player_name
        else:
            return jsonify({'success': False, 'error': f'Player {player_name} not recognized in this session. Current players: {all_players_list}'}), 403
            
    session_data['players_ready'][player_actual_name_in_session] = True
    session_manager.update_session(session_id, session_data)

    try:
        cache.delete_memoized(api_game_state, session_id=session_id)
    except KeyError:
        pass
    
    # Determine if the quiz should start
    should_start_quiz = False
    if is_test_mode:
        # In test mode, if the current player (who just signaled ready and is assumed to be players[0]) is ready.
        if all_players_list and player_actual_name_in_session == all_players_list[0] and session_data['players_ready'].get(player_actual_name_in_session, False):
            should_start_quiz = True
            logger.info(f"[api_player_ready] Test mode: Player {player_actual_name_in_session} is ready. Starting quiz for session {session_id}.")
    else:
        # Standard multiplayer logic
        ready_count = sum(1 for p_name in all_players_list if session_data['players_ready'].get(p_name, False))
        if len(all_players_list) >= 2 and ready_count == len(all_players_list):
            should_start_quiz = True
            logger.info(f"[api_player_ready] Multiplayer mode: All {len(all_players_list)} players ready. Starting quiz for session {session_id}.")

    # Emit events
    updated_game_state = get_game_state_data(session_id) # This will now include 'is_test_mode'
    if updated_game_state:
        socketio.emit('game_state_updated', updated_game_state, room=session_id)
        if should_start_quiz:
             socketio.emit('quiz_starting', {'message': 'Quiz starting...'}, room=session_id)

    return jsonify({
        'success': True, 
        'message': f'Player {player_actual_name_in_session} is ready.', 
        'player_ready_status': session_data['players_ready'], 
        'both_ready_now': updated_game_state.get('both_ready') if updated_game_state else False # Reflect UI-centric both_ready
    })

@app.route('/api/game-state/<session_id>')
@cache.memoize(timeout=5)  # Add cache memoization
def api_game_state(session_id):
    """Return multiplayer game state for waiting/ready logic"""
    state_data = get_game_state_data(session_id)
    if not state_data:
        return jsonify({'success': False, 'error': 'Session not found'}), 404
    
    return jsonify({'success': True, **state_data})

@app.route('/api/player-mapping/<session_id>')
@cache.memoize(timeout=5)  # Add cache memoization
def api_player_mapping(session_id):
    """Return player name mapping for Player 1/2"""
    mapping_data = get_player_mapping_data(session_id)
    return jsonify({'success': True, **mapping_data})

@app.route('/api/session-status/<session_id>')
def api_session_status(session_id):
    """Return status of other players in the same session group."""
    current_session_data = session_manager.get_session(session_id)
    if not current_session_data:
        return jsonify({'success': False, 'error': 'Session not found'}), 404

    quiz_id = current_session_data.get('quiz_id')
    group_id = current_session_data.get('shared_session_group', session_id)
    
    friend_sessions_data = []
    
    # Iterate through all sessions in the disk cache
    for key in session_manager.cache.iterkeys():
        # key is typically a bytes object from diskcache, decode if necessary
        # Depending on how keys are stored, direct string comparison might work or decoding might be needed.
        # For simplicity, assuming key can be compared or converted to string easily.
        other_sid = key.decode('utf-8') if isinstance(key, bytes) else str(key)

        if other_sid == session_id:
            continue # Skip current session
        
        other_data = session_manager.get_session(other_sid) # Use get_session to leverage memory cache & update last_accessed
        
        if other_data and \
           other_data.get('quiz_id') == quiz_id and \
           other_data.get('shared_session_group', other_sid) == group_id:
            
            friend_sessions_data.append({
                'session_id': other_sid,
                'player_name': other_data.get('player_name', 'Friend'),
                'current_question': other_data.get('current_question', 0),
                'total_questions': len(other_data.get('questions', [])),
                'is_complete': other_data.get('is_complete', False),
                'players': other_data.get('players', []) 
            })
            
    return jsonify({
        'success': True,
        'current_player_name': current_session_data.get('player_name', 'You'),
        'friend_sessions': friend_sessions_data
    })

# --- Multiplayer Play Another Quiz Request State ---
# Store pending quiz requests in memory (keyed by session_id)
pending_quiz_requests = {}

@app.route('/api/request-new-quiz', methods=['POST'])
def api_request_new_quiz():
    """Create a new session for a random quiz for 'Play Another Quiz'."""
    data = request.get_json()
    quiz_id = data.get('quiz_id')
    requester_player_name = data.get('player_name') # Renamed for clarity
    original_session_id_group = data.get('shared_session_group') # Client should send this

    # Get all available quiz ids
    quiz_files = [f for f in os.listdir('quizzes') if f.endswith('.json')]
    all_quiz_ids = [f[:-5] for f in quiz_files]
    # Remove current quiz_id from the list
    other_quiz_ids = [qid for qid in all_quiz_ids if qid != quiz_id]

    # Pick a random quiz id different from the current one, if possible
    if other_quiz_ids:
        chosen_quiz_id = random.choice(other_quiz_ids)
    else:
        chosen_quiz_id = quiz_id

    quiz_data = load_quiz(chosen_quiz_id)
    if not quiz_data:
        return jsonify({'success': False, 'error': 'Quiz not found'}), 404

    # Create a new session for the requester
    new_session_id = session_manager.create_session(chosen_quiz_id, quiz_data, original_session_id_group, requester_player_name)
    join_url = url_for('play_session', session_id=new_session_id, _external=True)
    
    # Store a pending request. Keyed by the original session group ID for easier lookup by other players.
    if original_session_id_group:
        pending_quiz_requests[original_session_id_group] = {
            'quiz_id': chosen_quiz_id,
            'quiz_title': quiz_data.get('title', 'New Quiz'),
            'requester_name': requester_player_name,
            'new_session_id_for_requester': new_session_id, # The session the requester is now in
            'timestamp': time.time()
        }
        # Notify other players in the original session group's room about the new quiz offer
        socketio.emit('play_again_invite', {
            'requester_name': requester_player_name,
            'new_session_id_to_join': new_session_id, # This is the session others should join
            'quiz_title': quiz_data.get('title', 'New Quiz')
        }, room=original_session_id_group) # Emit to the old session room
    
    return jsonify({'success': True, 'session_id': new_session_id, 'join_url': join_url})

@app.route('/api/pending-quiz-request/<session_id>')
def api_pending_quiz_request(session_id):
    """Return info about any pending quiz request for the group. (Kept for fallback or initial load)"""
    session_data = session_manager.get_session(session_id)
    if not session_data:
        return jsonify({'has_request': False})

    group_id = session_data.get('shared_session_group', session_id)
    
    request_details = pending_quiz_requests.get(group_id)
    if request_details and time.time() - request_details['timestamp'] < 120: # 2 min expiry
         # Don't show to the requester if they somehow poll this for their new session
        if request_details['new_session_id_for_requester'] != session_id :
            return jsonify({
                'has_request': True, 
                'quiz_id': request_details['quiz_id'], 
                'quiz_title': request_details['quiz_title'],
                'requester_name': request_details['requester_name'], 
                'new_session_id': request_details['new_session_id_for_requester'] # This is the session ID to join
            })
    return jsonify({'has_request': False})

@app.route('/api/accept-quiz-request', methods=['POST'])
def api_accept_quiz_request():
    """Accept a pending quiz request and join the requester's session."""
    data = request.get_json()
    # current_session_id = data.get('current_session_id') # Less relevant now
    new_session_id_to_join = data.get('new_session_id') # This is the session created by the requester
    player_name_accepting = data.get('player_name')
    original_session_id_group = data.get('shared_session_group') # Client should send this
    
    new_session_data = session_manager.get_session(new_session_id_to_join)
    if not new_session_data:
        return jsonify({'success': False, 'error': 'New session not found or expired'}), 404
    
    original_requester_name = new_session_data.get('player_name') # Player who started this new_session_id

    current_players_list = new_session_data.get('players')
    if not isinstance(current_players_list, list):
        logger.warning(f"[api_accept_quiz_request] new_session_data['players'] was not a list (was {type(current_players_list)}). Initializing for session {new_session_id_to_join}.")
        current_players_list = []

    # Ensure original requester is player 0 (idempotent)
    if original_requester_name:
        if original_requester_name in current_players_list:
            if current_players_list[0] != original_requester_name:
                current_players_list.pop(current_players_list.index(original_requester_name))
                current_players_list.insert(0, original_requester_name)
        else:
            current_players_list.insert(0, original_requester_name)
    
    # Remove any potential duplicates beyond the first occurrence of original_requester_name or others
    # This simplified version just ensures requester is at pos 0 if present, then appends acceptor if distinct and space allows.
    # A more robust deduplication might be needed if names can be non-unique beyond P1/P2 logic.
    
    # Add the accepting player if they are distinct from original_requester and there's space
    if player_name_accepting and player_name_accepting != original_requester_name:
        if player_name_accepting not in current_players_list:
            if len(current_players_list) < 2:
                current_players_list.append(player_name_accepting)
            else:
                logger.info(f"[api_accept_quiz_request] Session {new_session_id_to_join} is full. {player_name_accepting} cannot join.")
                return jsonify({'success': False, 'error': 'New quiz session is already full.'}), 400
        # If player_name_accepting is already in current_players_list (and not original_requester_name), they are already P2.
    
    # Ensure list does not exceed 2 players after manipulations
    new_session_data['players'] = current_players_list[:2] 

    if 'player_answers' not in new_session_data:
        new_session_data['player_answers'] = {}
    if player_name_accepting not in new_session_data['player_answers']:
        new_session_data['player_answers'][player_name_accepting] = []
    
    # Mark both players as not ready yet in the new session
    if 'players_ready' not in new_session_data: new_session_data['players_ready'] = {}
    for p in new_session_data['players']:
        new_session_data['players_ready'][p] = False

    session_manager.update_session(new_session_id_to_join, new_session_data)
    
    # Clear the pending request after acceptance from this group
    if original_session_id_group and original_session_id_group in pending_quiz_requests:
        # Verify it's the same quiz being accepted, though group_id is primary key here
        if pending_quiz_requests[original_session_id_group]['new_session_id_for_requester'] == new_session_id_to_join:
            del pending_quiz_requests[original_session_id_group]
            socketio.emit('play_again_invite_closed', {'message': 'Play again invite has been accepted or expired.'}, room=original_session_id_group)


    join_url = url_for('play_session', session_id=new_session_id_to_join, pn=player_name_accepting, _external=True)
    
    # Notify the new session (specifically the requester) that someone joined
    updated_game_state = get_game_state_data(new_session_id_to_join)
    if updated_game_state:
        socketio.emit('game_state_updated', updated_game_state, room=new_session_id_to_join)
        socketio.emit('player_mapping_updated', get_player_mapping_data(new_session_id_to_join), room=new_session_id_to_join)

    return jsonify({'success': True, 'session_id': new_session_id_to_join, 'join_url': join_url})

@app.route('/api/health')
def api_health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'active_sessions': len(session_manager.memory_cache)
    })

# --- SocketIO Event Handlers ---
@socketio.on('connect')
def handle_connect():
    # Session ID might not be available immediately on connect without client sending it.
    # Client should send session_id to join a room.
    logger.info(f"Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    # Here, you could implement logic to remove a player from a session if they disconnect
    # and notify other players. This requires tracking which session a request.sid belongs to.
    # For simplicity, we'll rely on heartbeats or session timeouts for now.
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('join_session_room')
def handle_join_session_room(data):
    session_id = data.get('session_id')
    player_name = data.get('player_name', 'Anonymous') # Ensure this matches how client sends it
    sid = request.sid # Capture socket ID for clarity
    logger.info(f"Client {sid} attempting to join session room with data: {data}")

    if session_id:
        join_room(session_id) # Client joins the specific session_id room
        logger.info(f"Client {sid} (Player: {player_name}) joined room {session_id}")
        
        current_session_data = session_manager.get_session(session_id)
        if current_session_data:
            shared_group_id = current_session_data.get('shared_session_group')
            if shared_group_id and shared_group_id != session_id: # Also join shared group if different
                join_room(shared_group_id)
                logger.info(f"Client {sid} (Player: {player_name}) also joined shared_group_room {shared_group_id}")
            
            # Upon joining a room, immediately send them the current state for that session.
            # This is crucial for re-connections or late joins.
            updated_game_state = get_game_state_data(session_id)
            if updated_game_state:
                logger.info(f"Emitting initial game_state_updated to {sid} for session {session_id}: {updated_game_state}")
                emit('game_state_updated', updated_game_state, room=sid) # Send to joining client only
                
                player_mapping = get_player_mapping_data(session_id)
                logger.info(f"Emitting initial player_mapping_updated to {sid} for session {session_id}: {player_mapping}")
                emit('player_mapping_updated', player_mapping, room=sid) # Send to joining client only
            
            # Notify others in the specific session room (not the shared group) that a user connected.
            # Avoid emitting if the player_name is generic like 'Anonymous' or if it's a reconnect without full player context yet.
            # The client sends player_name derived from sessionData.player_name which should be specific.
            if player_name and player_name != 'Anonymous':
                 socketio.emit('user_activity', {'message': f"{player_name} connected."}, room=session_id, include_self=False)
        else:
            logger.warning(f"Session data not found for session {session_id} when client {sid} tried to join its room.")
    else:
        logger.warning(f"Client {sid} tried to join room without session_id")

@socketio.on('leave_session_room')
def handle_leave_session_room(data):
    session_id = data.get('session_id')
    player_name = data.get('player_name', 'A player')
    if session_id:
        leave_room(session_id)
        logger.info(f"Client {request.sid} (Player: {player_name}) left room {session_id}")
        # Optionally, notify other players
        socketio.emit('user_activity', {'message': f"{player_name} left the session."}, room=session_id, include_self=False)

if __name__ == '__main__':
    # Use gevent for better performance in production
    if os.environ.get('FLASK_ENV') == 'production':
        # from gevent.pywsgi import WSGIServer # gevent is used by SocketIO directly
        # http_server = WSGIServer(('0.0.0.0', 5000), app)
        logger.info("Starting production server with Flask-SocketIO and gevent...")
        socketio.run(app, host='0.0.0.0', port=5000) # Use socketio.run
    else:
        # Development server
        logger.info("Starting development server with Flask-SocketIO...")
        socketio.run(app, debug=True, host='0.0.0.0', port=5000) # Use socketio.run