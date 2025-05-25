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
            {'prompt': 'What\'s your go-to comfort food?', 'option1': 'Pizza', 'option2': 'Burger'},
            {'prompt': 'What\'s your morning drink of choice?', 'option1': 'Coffee', 'option2': 'Tea'},
            {'prompt': 'Which dessert makes you happiest?', 'option1': 'Ice Cream', 'option2': 'Cake'},
            {'prompt': 'Which is your healthy snack choice?', 'option1': 'Apple', 'option2': 'Nuts'},
            {'prompt': 'What\'s your weekend drink?', 'option1': 'Wine', 'option2': 'Beer'},
        ]
    },
    {
        'title': 'Entertainment Choices',
        'description': 'What type of entertainment do you prefer?',
        'questions': [
            {'prompt': 'How do you prefer to unwind?', 'option1': 'Movie', 'option2': 'Book'},
            {'prompt': 'What\'s your video streaming choice?', 'option1': 'Netflix', 'option2': 'YouTube'},
            {'prompt': 'What\'s your audio entertainment?', 'option1': 'Music', 'option2': 'Podcast'},
            {'prompt': 'What\'s your ideal Friday night?', 'option1': 'Gaming', 'option2': 'Movie'},
            {'prompt': 'Which sport do you enjoy watching?', 'option1': 'Football', 'option2': 'Basketball'},
        ]
    },
    {
        'title': 'Tech Preferences',
        'description': 'Which technology do you prefer?',
        'questions': [
            {'prompt': 'What\'s your essential daily device?', 'option1': 'Phone', 'option2': 'Laptop'},
            {'prompt': 'Which smartphone ecosystem?', 'option1': 'iPhone', 'option2': 'Android'},
            {'prompt': 'What\'s your portable work device?', 'option1': 'Tablet', 'option2': 'Laptop'},
            {'prompt': 'Which operating system?', 'option1': 'Mac', 'option2': 'PC'},
            {'prompt': 'What\'s your computer mainly for?', 'option1': 'Gaming', 'option2': 'Work'},
        ]
    },
    {
        'title': 'Lifestyle Choices',
        'description': 'Discover your lifestyle preferences!',
        'questions': [
            {'prompt': 'Which pet would you choose?', 'option1': 'Cat', 'option2': 'Dog'},
            {'prompt': 'What\'s your favorite season?', 'option1': 'Summer', 'option2': 'Winter'},
            {'prompt': 'How do you prefer to get around?', 'option1': 'Car', 'option2': 'Bike'},
            {'prompt': 'Where do you feel most at home?', 'option1': 'City', 'option2': 'Nature'},
            {'prompt': 'When are you most productive?', 'option1': 'Morning', 'option2': 'Night'},
        ]
    },
    {
        'title': 'Travel Dreams',
        'description': 'Where would you rather go?',
        'questions': [
            {'prompt': 'Where do you want to spend your vacation?', 'option1': 'Beach', 'option2': 'Mountains'},
            {'prompt': 'Which city would you visit?', 'option1': 'Paris', 'option2': 'Tokyo'},
            {'prompt': 'How do you prefer to travel?', 'option1': 'Plane', 'option2': 'Train'},
            {'prompt': 'Where would you stay?', 'option1': 'Hotel', 'option2': 'Camping'},
            {'prompt': 'What\'s your travel style?', 'option1': 'Adventure', 'option2': 'Relaxation'},
        ]
    },
    {
        'title': 'Friend Personality Quiz',
        'description': 'Compare personalities with your friends!',
        'questions': [
            {'prompt': 'Who is more likely to be the life of the party?', 'option1': 'Player 1', 'option2': 'Player 2'},
            {'prompt': 'Who would be more patient in a long line?', 'option1': 'Player 1', 'option2': 'Player 2'},
            {'prompt': 'Who is more likely to try exotic food?', 'option1': 'Player 1', 'option2': 'Player 2'},
            {'prompt': 'Who would wake up earlier on vacation?', 'option1': 'Player 1', 'option2': 'Player 2'},
            {'prompt': 'Who is more organized with their belongings?', 'option1': 'Player 1', 'option2': 'Player 2'},
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