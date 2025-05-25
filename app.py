from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import uuid
import os
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

def create_play_session(quiz_id):
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
        'started_at': datetime.now().isoformat()
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
        'choices_summary': {}
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

@app.route('/play/<quiz_id>')
def play_quiz(quiz_id):
    """Start playing a quiz"""
    session_id = create_play_session(quiz_id)
    if not session_id:
        return "Quiz not found", 404
    
    return redirect(url_for('play_session', session_id=session_id))

@app.route('/session/<session_id>')
def play_session(session_id):
    """Play a specific session"""
    try:
        with open(f'play_sessions/{session_id}.json', 'r') as f:
            session_data = json.load(f)
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

if __name__ == '__main__':
    app.run(debug=True) 