"""
Dynamic Question Database for This or That Quiz
"""
import json
import random
import os
from typing import List, Dict, Optional, Set
from datetime import datetime
import hashlib

class QuestionDatabase:
    """Manages a database of this-or-that questions"""
    
    def __init__(self, db_path: str = 'questions_db.json'):
        self.db_path = db_path
        self.questions = []
        self.categories = {}
        self.category_index = {}
        self.tag_index = {}
        
        # Load database
        self.load_database()
        
    def load_database(self):
        """Load questions from JSON file"""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                self.questions = self.data.get('questions', [])
                self.categories = self.data.get('categories', {})
                
                # Build indices for fast lookup
                self._build_indices()
                
            except Exception as e:
                print(f"Error loading database: {e}")
                self._create_default_database()
        else:
            self._create_default_database()
            
    def _build_indices(self):
        """Build category and tag indices for fast lookup"""
        self.category_index = {}
        self.tag_index = {}
        
        for q in self.questions:
            # Category index
            cat = q.get('category', 'general')
            if cat not in self.category_index:
                self.category_index[cat] = []
            self.category_index[cat].append(q)
            
            # Tag index
            for tag in q.get('tags', []):
                if tag not in self.tag_index:
                    self.tag_index[tag] = []
                self.tag_index[tag].append(q)
                
    def _create_default_database(self):
        """Create default database structure with sample questions"""
        self.data = {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "categories": {
                "general": {"name": "General", "emoji": "🎯", "question_count": 0},
                "food-drink": {"name": "Food & Drink", "emoji": "🍔", "question_count": 0},
                "travel": {"name": "Travel & Places", "emoji": "✈️", "question_count": 0},
                "lifestyle": {"name": "Lifestyle", "emoji": "🏠", "question_count": 0},
                "entertainment": {"name": "Entertainment", "emoji": "🎬", "question_count": 0},
                "technology": {"name": "Technology", "emoji": "📱", "question_count": 0},
                "sports": {"name": "Sports & Fitness", "emoji": "⚽", "question_count": 0},
                "fashion": {"name": "Fashion & Style", "emoji": "👗", "question_count": 0},
                "nature": {"name": "Nature & Animals", "emoji": "🌳", "question_count": 0},
                "work": {"name": "Work & Career", "emoji": "💼", "question_count": 0}
            },
            "questions": []
        }
        
        self.categories = self.data['categories']
        self.questions = self.data['questions']
        self.save_database()
        
    def save_database(self):
        """Save database to JSON file"""
        self.data['questions'] = self.questions
        self.data['categories'] = self.categories
        self.data['last_updated'] = datetime.now().isoformat()
        
        # Update category counts
        for cat_id in self.categories:
            self.categories[cat_id]['question_count'] = len(self.category_index.get(cat_id, []))
        
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
            
    def add_question(self, prompt: str, option1: str, option2: str, 
                    category: str = "general", tags: List[str] = None,
                    difficulty: str = "medium") -> str:
        """Add a new question to the database"""
        # Generate unique ID
        content = f"{prompt}{option1}{option2}"
        q_id = f"q_{hashlib.md5(content.encode()).hexdigest()[:8]}"
        
        # Check if question already exists
        if any(q['id'] == q_id for q in self.questions):
            return q_id  # Question already exists
            
        new_question = {
            "id": q_id,
            "prompt": prompt,
            "option1": option1,
            "option2": option2,
            "category": category,
            "tags": tags or [],
            "difficulty": difficulty,
            "stats": {
                "total_answers": 0,
                "option1_percentage": 50.0
            },
            "created_at": datetime.now().isoformat()
        }
        
        self.questions.append(new_question)
        
        # Update indices
        if category not in self.category_index:
            self.category_index[category] = []
        self.category_index[category].append(new_question)
        
        for tag in tags or []:
            if tag not in self.tag_index:
                self.tag_index[tag] = []
            self.tag_index[tag].append(new_question)
            
        return q_id
        
    def get_random_quiz(self, category: str = None, count: int = 10,
                       exclude_ids: Set[str] = None,
                       tags: List[str] = None) -> Dict:
        """Generate a random quiz from available questions.

        Questions in exclude_ids (recently played by this player) are
        avoided, but if the pool would be starved we top up from the
        excluded set - some overlap is fine, a short quiz is not.
        """
        # Get available questions
        if category and category != "mixed":
            available = self.category_index.get(category, []).copy()
        else:
            available = self.questions.copy()

        # Filter by tags if specified
        if tags:
            available = [q for q in available
                        if any(tag in q.get('tags', []) for tag in tags)]

        # Prefer questions this player hasn't seen recently
        if exclude_ids:
            fresh = [q for q in available if q['id'] not in exclude_ids]
            if len(fresh) >= count:
                available = fresh
            else:
                # Not enough unseen questions left in this category - fill
                # the remainder from the recently-played pool (overlap OK)
                excluded = [q for q in available if q['id'] in exclude_ids]
                needed = count - len(fresh)
                available = fresh + random.sample(
                    excluded, min(needed, len(excluded)))

        # Ensure we have enough questions
        if len(available) < count:
            count = len(available)

        if count == 0:
            return None

        # Select random questions
        selected = random.sample(available, count)
        
        # Generate quiz title
        if category and category != "mixed":
            title = f"{self.categories.get(category, {}).get('name', 'Random')} Quiz"
        else:
            title = "Mixed Bag Quiz"
            
        return {
            "title": title,
            "type": "thisorthat",
            "category": category or "mixed",
            "questions": selected,
            "dynamic": True,
            "created_at": datetime.now().isoformat()
        }
        
    def get_trending_quiz(self, count: int = 10) -> Dict:
        """Get questions with most 50/50 splits (controversial)"""
        # Sort by how close to 50/50 the split is
        sorted_questions = sorted(
            self.questions,
            key=lambda q: abs(50 - q['stats']['option1_percentage'])
        )
        
        return {
            "title": "🔥 Trending Debates",
            "type": "thisorthat",
            "category": "trending",
            "questions": sorted_questions[:count],
            "dynamic": True,
            "created_at": datetime.now().isoformat()
        }
        
    def get_daily_challenge(self) -> Dict:
        """Get the same 10 questions for all users today"""
        # Use today's date as seed
        date_seed = datetime.now().strftime("%Y%m%d")
        random.seed(date_seed)
        
        # Select 10 questions (same for everyone today)
        selected = random.sample(self.questions, min(10, len(self.questions)))
        
        # Reset random seed
        random.seed()
        
        return {
            "title": f"Daily Challenge - {datetime.now().strftime('%B %d')}",
            "type": "thisorthat",
            "category": "daily",
            "questions": selected,
            "dynamic": True,
            "daily": True,
            "created_at": datetime.now().isoformat()
        }
        
    def update_question_stats(self, question_id: str, choice: str):
        """Update statistics for a question based on user choice"""
        for q in self.questions:
            if q['id'] == question_id:
                q['stats']['total_answers'] += 1
                
                if choice == 'left' or choice == q['option1']:
                    # Update rolling average
                    total = q['stats']['total_answers']
                    current_pct = q['stats']['option1_percentage']
                    new_pct = ((current_pct * (total - 1)) + 100) / total
                    q['stats']['option1_percentage'] = round(new_pct, 1)
                else:
                    # Option 2 was chosen
                    total = q['stats']['total_answers']
                    current_pct = q['stats']['option1_percentage']
                    new_pct = ((current_pct * (total - 1)) + 0) / total
                    q['stats']['option1_percentage'] = round(new_pct, 1)
                break
                
    def get_categories_with_counts(self) -> List[Dict]:
        """Get all categories with their question counts"""
        result = []
        for cat_id, cat_data in self.categories.items():
            result.append({
                "id": cat_id,
                "name": cat_data["name"],
                "emoji": cat_data["emoji"],
                "question_count": len(self.category_index.get(cat_id, []))
            })
        return sorted(result, key=lambda x: x['question_count'], reverse=True)
        
    def import_questions_bulk(self, questions_list: List[Dict]) -> int:
        """Import multiple questions at once"""
        added = 0
        for q in questions_list:
            q_id = self.add_question(
                prompt=q.get('prompt', ''),
                option1=q.get('option1', ''),
                option2=q.get('option2', ''),
                category=q.get('category', 'general'),
                tags=q.get('tags', []),
                difficulty=q.get('difficulty', 'medium')
            )
            added += 1
            
        self.save_database()
        return added
        
    def search_questions(self, query: str) -> List[Dict]:
        """Search questions by text"""
        query_lower = query.lower()
        results = []
        
        for q in self.questions:
            if (query_lower in q['prompt'].lower() or
                query_lower in q['option1'].lower() or
                query_lower in q['option2'].lower() or
                any(query_lower in tag for tag in q.get('tags', []))):
                results.append(q)
                
        return results