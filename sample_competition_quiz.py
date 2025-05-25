#!/usr/bin/env python3

import json
import uuid
from datetime import datetime

def create_competition_quiz():
    """Create a sample competition quiz with questions that have correct answers"""
    quiz_data = {
        'title': 'Historical Knowledge Challenge',
        'description': 'Test your knowledge of historical facts and figures',
        'type': 'competition',  # Mark as competition mode
        'created_at': datetime.now().isoformat(),
        'questions': [
            {
                'prompt': 'Who was the famous French Emperor?',
                'option1': 'Louis XIV',
                'option2': 'Napoleon Bonaparte', 
                'correct_answer': 'option2'  # Napoleon is correct
            },
            {
                'prompt': 'Which city is the capital of Australia?',
                'option1': 'Sydney',
                'option2': 'Canberra',
                'correct_answer': 'option2'  # Canberra is correct
            },
            {
                'prompt': 'What year did World War II end?',
                'option1': '1945',
                'option2': '1944',
                'correct_answer': 'option1'  # 1945 is correct
            },
            {
                'prompt': 'Who painted the Mona Lisa?',
                'option1': 'Michelangelo',
                'option2': 'Leonardo da Vinci',
                'correct_answer': 'option2'  # Leonardo da Vinci is correct
            },
            {
                'prompt': 'What is the largest planet in our solar system?',
                'option1': 'Saturn',
                'option2': 'Jupiter',
                'correct_answer': 'option2'  # Jupiter is correct
            },
            {
                'prompt': 'Which element has the chemical symbol "O"?',
                'option1': 'Oxygen',
                'option2': 'Gold',
                'correct_answer': 'option1'  # Oxygen is correct
            }
        ]
    }
    
    # Generate quiz ID
    quiz_id = str(uuid.uuid4())[:8]
    quiz_data['id'] = quiz_id
    
    # Save to quizzes directory
    with open(f'quizzes/{quiz_id}.json', 'w') as f:
        json.dump(quiz_data, f, indent=2)
    
    print(f"Created competition quiz with ID: {quiz_id}")
    print(f"Title: {quiz_data['title']}")
    print(f"Questions: {len(quiz_data['questions'])}")
    
    return quiz_id

if __name__ == '__main__':
    create_competition_quiz() 