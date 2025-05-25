#!/usr/bin/env python3
"""
Sample quiz generator for This or That app
Run this script to create some sample quizzes for testing
"""

import json
import uuid
import os
from datetime import datetime

# Ensure quizzes directory exists
os.makedirs('quizzes', exist_ok=True)

def create_sample_quiz(title, description, questions):
    """Create a sample quiz and save it to JSON"""
    quiz_id = str(uuid.uuid4())[:8]
    
    quiz_data = {
        'id': quiz_id,
        'title': title,
        'description': description,
        'questions': questions,
        'created_at': datetime.now().isoformat()
    }
    
    with open(f'quizzes/{quiz_id}.json', 'w') as f:
        json.dump(quiz_data, f, indent=2)
    
    print(f"Created quiz '{title}' with ID: {quiz_id}")
    return quiz_id

# Sample quizzes
sample_quizzes = [
    {
        'title': 'Food Preferences',
        'description': 'Discover your favorite foods in this delicious quiz!',
        'questions': [
            {'option1': 'Pizza', 'option2': 'Burger'},
            {'option1': 'Coffee', 'option2': 'Tea'},
            {'option1': 'Ice Cream', 'option2': 'Cake'},
            {'option1': 'Apple', 'option2': 'Burger'},
            {'option1': 'Wine', 'option2': 'Beer'},
        ]
    },
    {
        'title': 'Entertainment Choices',
        'description': 'What type of entertainment do you prefer?',
        'questions': [
            {'option1': 'Movie', 'option2': 'Book'},
            {'option1': 'Netflix', 'option2': 'YouTube'},
            {'option1': 'Music', 'option2': 'TV'},
            {'option1': 'Game', 'option2': 'Movie'},
            {'option1': 'Football', 'option2': 'Basketball'},
        ]
    },
    {
        'title': 'Tech Preferences',
        'description': 'Which technology do you prefer?',
        'questions': [
            {'option1': 'Phone', 'option2': 'Laptop'},
            {'option1': 'iPhone', 'option2': 'Android'},
            {'option1': 'Tablet', 'option2': 'Computer'},
            {'option1': 'Mac', 'option2': 'PC'},
            {'option1': 'Gaming', 'option2': 'Productivity'},
        ]
    },
    {
        'title': 'Lifestyle Choices',
        'description': 'Discover your lifestyle preferences!',
        'questions': [
            {'option1': 'Cat', 'option2': 'Dog'},
            {'option1': 'Summer', 'option2': 'Winter'},
            {'option1': 'Car', 'option2': 'Bike'},
            {'option1': 'City', 'option2': 'Nature'},
            {'option1': 'Morning', 'option2': 'Night'},
        ]
    },
    {
        'title': 'Travel Dreams',
        'description': 'Where would you rather go?',
        'questions': [
            {'option1': 'Beach', 'option2': 'Mountains'},
            {'option1': 'Paris', 'option2': 'Tokyo'},
            {'option1': 'Plane', 'option2': 'Train'},
            {'option1': 'Hotel', 'option2': 'Camping'},
            {'option1': 'Adventure', 'option2': 'Relaxation'},
        ]
    }
]

if __name__ == '__main__':
    print("Creating sample quizzes for This or That app...")
    print("=" * 50)
    
    created_quizzes = []
    
    for quiz in sample_quizzes:
        quiz_id = create_sample_quiz(
            quiz['title'],
            quiz['description'],
            quiz['questions']
        )
        created_quizzes.append({
            'id': quiz_id,
            'title': quiz['title'],
            'url': f'http://localhost:5000/play/{quiz_id}'
        })
    
    print("\n" + "=" * 50)
    print("Sample quizzes created successfully!")
    print("\nQuiz URLs:")
    for quiz in created_quizzes:
        print(f"📋 {quiz['title']}: {quiz['url']}")
    
    print(f"\n🎮 Start the app with: python app.py")
    print(f"🌐 Then visit: http://localhost:5000")
    print(f"✨ Have fun creating and playing quizzes!") 