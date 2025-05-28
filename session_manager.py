"""
Optimized Session Manager using DiskCache for improved performance
"""
import json
import uuid
import time
import os
import logging
from datetime import datetime, timedelta
from threading import Lock
import diskcache
from collections import defaultdict
import msgpack

logger = logging.getLogger(__name__)

class OptimizedSessionManager:
    """High-performance session manager using DiskCache"""
    
    def __init__(self, cache_dir='session_storage', timeout=3600):
        self.cache_dir = cache_dir
        self.timeout = timeout
        
        # Initialize DiskCache with optimized settings
        self.cache = diskcache.Cache(
            cache_dir,
            size_limit=1_000_000_000,  # 1GB limit
            eviction_policy='least-recently-used',
            disk_min_file_size=1024,  # Store small objects in SQLite
            statistics=0  # Disable statistics for performance
        )
        
        # In-memory cache for hot data
        self.memory_cache = {}
        self.memory_cache_lock = Lock()
        self.memory_cache_size = 0
        self.max_memory_cache_size = 100 * 1024 * 1024  # 100MB
        
        # Heartbeat tracking
        self.heartbeats = defaultdict(float)
        
        # Start background cleanup
        self._start_cleanup_thread()
        
    def create_session(self, quiz_id, quiz_data, shared_session_id=None, player_name=None):
        """Create a new session with optimized storage"""
        session_id = str(uuid.uuid4())[:8]
        
        session_data = {
            'session_id': session_id,
            'quiz_id': quiz_id,
            'quiz_title': quiz_data['title'],
            'questions': quiz_data['questions'],
            'current_question': 0,
            'answers': [], # Legacy: for primary player's sequential answers
            'player_answers': {}, # New: for individual player answers {player_name: [answers]}
            'players_ready': {}, # Tracks if players have clicked "Ready"
            'player_completion_status': {}, # New: Tracks if players have completed all questions {player_name: True/False}
            'started_at': datetime.now().isoformat(),
            'shared_session_group': shared_session_id or session_id,
            'player_name': player_name or f'Player {session_id[:4]}', # The creator or first player
            'players': [], # List of player names in the session
            'last_accessed': time.time()
        }
        
        # Initialize players list and player_answers for the creator
        if player_name:
            session_data['players'].append(player_name)
            session_data['player_answers'][player_name] = []
            session_data['player_completion_status'][player_name] = False # Initialize completion status

        # Store in both caches
        self._set_session(session_id, session_data)
        
        logger.info(f"Created session {session_id} for quiz {quiz_id}")
        return session_id
        
    def get_session(self, session_id):
        """Get session with memory cache optimization"""
        # Check memory cache first
        with self.memory_cache_lock:
            if session_id in self.memory_cache:
                session_data = self.memory_cache[session_id]
                session_data['last_accessed'] = time.time()
                return session_data.copy()
        
        # Fall back to disk cache
        session_data = self.cache.get(session_id)
        if session_data:
            session_data['last_accessed'] = time.time()
            # Add to memory cache
            self._add_to_memory_cache(session_id, session_data)
            return session_data.copy()
        
        return None
        
    def update_session(self, session_id, session_data):
        """Update session in both caches"""
        session_data['last_accessed'] = time.time()
        self._set_session(session_id, session_data)
        return True
        
    def submit_answer(self, session_id, answer, question_index, player_choice=None, player_name='Unknown Player'):
        """Submit answer with optimized update for multiplayer"""
        session_data = self.get_session(session_id)
        if not session_data:
            return None
            
        # Ensure player_answers dictionary exists for multiplayer tracking
        if 'player_answers' not in session_data:
            session_data['player_answers'] = {session_data.get('player_name', 'Player 1'): []}
        if player_name not in session_data['player_answers']:
            session_data['player_answers'][player_name] = []
            
        # Ensure player_completion_status is initialized for the player
        if 'player_completion_status' not in session_data:
            session_data['player_completion_status'] = {}
        if player_name not in session_data['player_completion_status']:
            session_data['player_completion_status'][player_name] = False

        # Record the answer for the specific player
        answer_data = {
            'question_index': question_index,
            'answer': answer,
            'timestamp': datetime.now().isoformat()
        }
        
        if player_choice:
            answer_data['player_choice'] = player_choice
            
        # Append to player's answers
        existing_answer_for_player = next((a for a in session_data['player_answers'][player_name] if a['question_index'] == question_index), None)
        if not existing_answer_for_player:
            session_data['player_answers'][player_name].append(answer_data)
            
            # Check if this player has now completed the quiz
            if len(session_data['player_answers'][player_name]) >= len(session_data['questions']):
                session_data['player_completion_status'][player_name] = True
                logger.info(f"Player {player_name} has completed all questions in session {session_id}.")

        else:
            logger.warning(f"Player {player_name} attempted to re-submit answer for question_index {question_index} in session {session_id}. Ignoring.")

        # Legacy/Primary player answer tracking & current_question advancement
        is_primary_player = (player_name == session_data.get('player_name')) or \
                            (session_data.get('players') and player_name == session_data['players'][0])

        if is_primary_player:
            if session_data['current_question'] == question_index:
                legacy_answer_exists = next((a for a in session_data.get('answers', []) if a['question_index'] == question_index), None)
                if not legacy_answer_exists:
                    session_data.get('answers', []).append(answer_data)
                    session_data['current_question'] += 1
        
        # Check if quiz is complete for the primary player (session's main progression)
        is_session_complete_for_primary = session_data['current_question'] >= len(session_data['questions'])
        
        # Update session
        self.update_session(session_id, session_data)
        
        # If complete for primary player, save to results (legacy behavior)
        if is_session_complete_for_primary:
            self._save_results(session_data)
            
        return {
            'success': True,
            'is_complete': is_session_complete_for_primary,
            'current_question_for_session': session_data['current_question'],
            'total_questions': len(session_data['questions']),
            'player_choice_submitted': player_choice,
            'player_name_submitted': player_name,
            'question_index_submitted': question_index
        }
        
    def get_sessions_by_group(self, shared_group_id, quiz_id=None):
        """Get all sessions in a group efficiently"""
        sessions = []
        
        # Check memory cache first
        with self.memory_cache_lock:
            for session_id, session_data in self.memory_cache.items():
                if (session_data.get('shared_session_group') == shared_group_id and
                    (quiz_id is None or session_data.get('quiz_id') == quiz_id)):
                    sessions.append(session_data.copy())
        
        # Then check disk cache for any we might have missed
        # Use cache.iterkeys() for efficiency
        for key in self.cache.iterkeys():
            if key not in [s['session_id'] for s in sessions]:
                session_data = self.cache.get(key)
                if (session_data and
                    session_data.get('shared_session_group') == shared_group_id and
                    (quiz_id is None or session_data.get('quiz_id') == quiz_id)):
                    sessions.append(session_data.copy())
                    
        return sessions
        
    def update_heartbeat(self, session_id):
        """Update player heartbeat"""
        self.heartbeats[session_id] = time.time()
        
    def check_disconnected_players(self, timeout=30):
        """Check for disconnected players"""
        current_time = time.time()
        disconnected = []
        
        for session_id, last_beat in list(self.heartbeats.items()):
            if current_time - last_beat > timeout:
                disconnected.append(session_id)
                del self.heartbeats[session_id]
                
        return disconnected
        
    def _set_session(self, session_id, session_data):
        """Store session in both caches"""
        # Store in disk cache
        self.cache.set(session_id, session_data, expire=self.timeout)
        
        # Store in memory cache
        self._add_to_memory_cache(session_id, session_data)
        
    def _add_to_memory_cache(self, session_id, session_data):
        """Add to memory cache with size management"""
        with self.memory_cache_lock:
            # Estimate size (rough)
            data_size = len(json.dumps(session_data))
            
            # Evict old items if needed
            while (self.memory_cache_size + data_size > self.max_memory_cache_size 
                   and self.memory_cache):
                # Remove least recently accessed
                oldest_id = min(self.memory_cache.items(), 
                              key=lambda x: x[1].get('last_accessed', 0))[0]
                old_data = self.memory_cache.pop(oldest_id)
                self.memory_cache_size -= len(json.dumps(old_data))
                
            # Add new item
            self.memory_cache[session_id] = session_data
            self.memory_cache_size += data_size
            
    def _save_results(self, session_data):
        """Save completed session results"""
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
            'shared_session_group': session_data.get('shared_session_group'),
            'player_name': session_data.get('player_name')
        }
        
        # Analyze choices
        for i, question in enumerate(session_data['questions']):
            answer_data = next((a for a in session_data['answers'] 
                              if a['question_index'] == i), None)
            if answer_data:
                choice = (question['option1'] if answer_data['answer'] == 'left' 
                         else question['option2'])
                result_data['choices_summary'][f'question_{i}'] = {
                    'options': [question['option1'], question['option2']],
                    'choice': choice,
                    'choice_side': answer_data['answer']
                }
        
        # Save to file
        filename = f'{results_dir}/{session_data["session_id"]}.json'
        with open(filename, 'w') as f:
            json.dump(result_data, f, indent=2)
            
    def _start_cleanup_thread(self):
        """Start background cleanup thread"""
        import threading
        
        def cleanup_worker():
            while True:
                try:
                    # Clean expired sessions
                    current_time = time.time()
                    
                    # Clean memory cache
                    with self.memory_cache_lock:
                        expired = [sid for sid, data in self.memory_cache.items()
                                 if current_time - data.get('last_accessed', 0) > self.timeout]
                        for sid in expired:
                            del self.memory_cache[sid]
                            
                    # DiskCache handles its own expiration
                    
                    # Sleep for 5 minutes
                    time.sleep(300)
                    
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")
                    
        thread = threading.Thread(target=cleanup_worker, daemon=True)
        thread.start()
        
    def close(self):
        """Close the cache properly"""
        self.cache.close() 