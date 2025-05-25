from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import uuid
import os
import time
from datetime import datetime
import base64
from PIL import Image
import io
import pytesseract
import re

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure directories exist
os.makedirs('quizzes', exist_ok=True)
os.makedirs('uploads', exist_ok=True)
os.makedirs('play_sessions', exist_ok=True)

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
    session_id = str(uuid.uuid4())[:8]
    quiz_data = load_quiz(quiz_id)
    
    if not quiz_data:
        return None
    
    session_data = {
        'session_id': session_id,
        'quiz_id': quiz_id,
        'quiz_title': quiz_data['title'],
        'questions': quiz_data['questions'],
        'current_question': 0,
        'answers': [],
        'started_at': datetime.now().isoformat(),
        'shared_session_group': shared_session_id or session_id,  # Group sessions together
        'player_name': player_name or f'Player {session_id[:4]}'
    }
    
    with open(f'play_sessions/{session_id}.json', 'w') as f:
        json.dump(session_data, f, indent=2)
    
    return session_id

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

def extract_questions_from_image(image_path):
    """Extract 'this or that' questions from uploaded image using OCR"""
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
        session_data = None
        
        # Try to get from active sessions first
        try:
            with open(f'play_sessions/{session_id}.json', 'r') as f:
                session_data = json.load(f)
        except FileNotFoundError:
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
    try:
        with open(f'play_sessions/{session_id}.json', 'r') as f:
            session_data = json.load(f)
        
        # Check if session exists and is valid for joining
        quiz_id = session_data['quiz_id']
        
        # Render a join page where user can enter their name
        return render_template('join.html', session_id=session_id, quiz_title=session_data['quiz_title'])
    except FileNotFoundError:
        return "Session not found", 404

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
    try:
        with open(f'play_sessions/{session_id}.json', 'r') as f:
            session_data = json.load(f)
        
        # Always show the play template - it will handle completed state
        return render_template('play.html', session=session_data)
    except FileNotFoundError:
        return "Session not found", 404

@app.route('/api/create_quiz', methods=['POST'])
def api_create_quiz():
    """API endpoint to create a new quiz"""
    data = request.get_json()
    
    quiz_data = {
        'title': data.get('title', 'Untitled Quiz'),
        'description': data.get('description', ''),
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

@app.route('/api/session/<session_id>/answer', methods=['POST'])
def api_submit_answer(session_id):
    """API endpoint to submit an answer"""
    try:
        data = request.get_json()
        answer = data.get('answer')  # 'left' or 'right'
        
        with open(f'play_sessions/{session_id}.json', 'r') as f:
            session_data = json.load(f)
        
        # Record the answer
        session_data['answers'].append({
            'question_index': session_data['current_question'],
            'answer': answer,
            'timestamp': datetime.now().isoformat()
        })
        
        # Move to next question
        session_data['current_question'] += 1
        
        # Save updated session
        with open(f'play_sessions/{session_id}.json', 'w') as f:
            json.dump(session_data, f, indent=2)
        
        # Check if quiz is complete
        is_complete = session_data['current_question'] >= len(session_data['questions'])
        
        # If complete, save results
        if is_complete:
            save_quiz_results(session_data)
        
        return jsonify({
            'success': True,
            'is_complete': is_complete,
            'current_question': session_data['current_question'],
            'total_questions': len(session_data['questions'])
        })
        
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'Session not found'})

@app.route('/api/session/<session_id>')
def api_get_session(session_id):
    """API endpoint to get session data"""
    try:
        with open(f'play_sessions/{session_id}.json', 'r') as f:
            session_data = json.load(f)
        return jsonify(session_data)
    except FileNotFoundError:
        return jsonify({'error': 'Session not found'}), 404

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
                    'question_count': len(quiz_data['questions'])
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
        with open(f'play_sessions/{session_id}.json', 'r') as f:
            main_session = json.load(f)
        
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
        
        # Check in-progress sessions
        if os.path.exists('play_sessions'):
            for filename in os.listdir('play_sessions'):
                if filename.endswith('.json'):
                    try:
                        with open(f'play_sessions/{filename}', 'r') as f:
                            session_data = json.load(f)
                            if (session_data.get('shared_session_group') == shared_group_id and 
                                session_data.get('quiz_id') == quiz_id and
                                session_data['session_id'] != session_id):  # Don't include self
                                
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
                                elif session_data['session_id'] not in [p['session_id'] for p in completed_players]:
                                    # Session is complete but not in results yet - they might have just finished
                                    pass
                    except Exception as e:
                        continue
        
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
    try:
        data = request.get_json()
        current_session_id = data.get('current_session_id')
        current_quiz_id = data.get('current_quiz_id')
        player_name = data.get('player_name', 'Anonymous')
        
        # Get current session data
        with open(f'play_sessions/{current_session_id}.json', 'r') as f:
            current_session = json.load(f)
        
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
            
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'Session not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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
                    'question_count': len(quiz_data['questions'])
                })
    return quizzes

@app.route('/api/session-status/<session_id>')
def api_session_status(session_id):
    """API endpoint to get session status and check for friends"""
    try:
        with open(f'play_sessions/{session_id}.json', 'r') as f:
            session_data = json.load(f)
        
        quiz_id = session_data['quiz_id']
        shared_group_id = session_data.get('shared_session_group', session_id)
        
        # Find all sessions in the same group
        group_sessions = []
        if os.path.exists('play_sessions'):
            for filename in os.listdir('play_sessions'):
                if filename.endswith('.json'):
                    try:
                        with open(f'play_sessions/{filename}', 'r') as f:
                            other_session = json.load(f)
                            if (other_session.get('shared_session_group') == shared_group_id and 
                                other_session.get('quiz_id') == quiz_id):
                                group_sessions.append({
                                    'session_id': other_session['session_id'],
                                    'player_name': other_session.get('player_name', f"Player {other_session['session_id'][:4]}"),
                                    'current_question': other_session['current_question'],
                                    'total_questions': len(other_session['questions']),
                                    'is_complete': other_session['current_question'] >= len(other_session['questions'])
                                })
                    except:
                        continue
        
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
        
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'Session not found'}), 404

def get_player_mapping(session_data, friend_data=None):
    """
    Create a mapping for player mode quizzes where Player 1/Player 2 need to be mapped to actual names
    """
    my_name = session_data.get('player_name', f"Player {session_data['session_id'][:4]}")
    
    if friend_data:
        friend_name = friend_data.get('player_name', f"Player {friend_data['session_id'][:4]}")
        
        # Determine who is Player 1 and who is Player 2 based on session creation time
        my_time = session_data.get('started_at', '')
        friend_time = friend_data.get('started_at', '')
        
        if my_time < friend_time:  # I started first, so I'm Player 1
            return {
                'Player 1': my_name,
                'Player 2': friend_name,
                'my_player_number': 1,
                'friend_player_number': 2
            }
        else:  # Friend started first, so they're Player 1
            return {
                'Player 1': friend_name,
                'Player 2': my_name,
                'my_player_number': 2,
                'friend_player_number': 1
            }
    else:
        # Solo play or friend not available
        return {
            'Player 1': my_name,
            'Player 2': 'Your Friend',
            'my_player_number': 1,
            'friend_player_number': 2
        }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # fallback to 5000 locally
    app.run(host='0.0.0.0', port=port)