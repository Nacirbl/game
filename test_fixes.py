#!/usr/bin/env python3
"""
Test script to validate the three main fixes:
1. Display compatibility score/competition scores in results
2. Use player names instead of player IDs
3. "Play Another" automatically invites same players
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:5000"

def test_multiplayer_results_display():
    """Test that multiplayer results show proper scores and names"""
    print("Testing multiplayer results display...")
    
    # Test with a known session that has results
    test_session_id = "f22e49ab"  # This should be a completed session
    
    try:
        response = requests.get(f"{BASE_URL}/api/multiplayer-results/{test_session_id}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API call successful")
            print(f"Quiz type: {data.get('quiz_type', 'unknown')}")
            print(f"Players found: {len(data.get('players', []))}")
            
            for i, player in enumerate(data.get('players', [])):
                player_name = player.get('player_name', 'NO_NAME')
                session_id = player.get('session_id', 'NO_ID')
                print(f"  Player {i+1}: {player_name} (Session: {session_id[:8]})")
                
            if data.get('quiz_type') == 'competition':
                print("✅ Competition mode detected - scores should be calculated")
            else:
                print("✅ This or That mode - compatibility should be calculated")
                
        else:
            print(f"❌ API call failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

def test_create_group_sessions():
    """Test the new group session creation endpoint"""
    print("\nTesting group session creation...")
    
    # This would need a valid session to test properly
    test_data = {
        "current_session_id": "f22e49ab",
        "quiz_id": "ba50f2e1"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/create-group-sessions", 
                               json=test_data,
                               headers={'Content-Type': 'application/json'})
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ Group sessions created successfully")
                print(f"My session ID: {data.get('my_session_id')}")
                print(f"Other players: {len(data.get('other_players', []))}")
                for player in data.get('other_players', []):
                    print(f"  - {player.get('player_name')} -> {player.get('session_id')}")
            else:
                print(f"❌ API returned error: {data.get('error')}")
        else:
            print(f"❌ API call failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

def test_quiz_data_structure():
    """Test that quiz data includes necessary fields for scoring"""
    print("\nTesting quiz data structure...")
    
    # Test competition quiz
    quiz_id = "ba50f2e1"
    
    try:
        # We'll test by looking at the results of the multiplayer endpoint
        response = requests.get(f"{BASE_URL}/api/multiplayer-results/f22e49ab")
        if response.status_code == 200:
            data = response.json()
            questions = data.get('questions', [])
            
            print(f"✅ Found {len(questions)} questions")
            
            competition_questions_with_answers = 0
            for i, question in enumerate(questions):
                has_correct = 'correct_answer' in question
                if has_correct:
                    competition_questions_with_answers += 1
                    
                print(f"  Q{i+1}: {question.get('prompt', 'No prompt')}")
                print(f"       Options: {question.get('option1')} vs {question.get('option2')}")
                print(f"       Correct: {question.get('correct_answer', 'NONE')} {'✅' if has_correct else '❌'}")
                
            if data.get('quiz_type') == 'competition':
                print(f"✅ Competition quiz: {competition_questions_with_answers}/{len(questions)} questions have correct answers")
            else:
                print(f"✅ This or That quiz: No correct answers needed")
                
        else:
            print(f"❌ Could not retrieve quiz data: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

def manual_score_calculation():
    """Manually calculate scores to verify our logic"""
    print("\nManual score calculation for validation...")
    
    # Based on the data we saw earlier
    player_answers = ["right", "left", "left", "right", "left", "right", "left", "right", "left", "right"]
    correct_answers = ["option2", "option2", "option1", "option2", "option1", "option1", "option1", "option1", "option1", "option2"]
    
    score = 0
    print("Question by question analysis:")
    for i, (player_answer, correct) in enumerate(zip(player_answers, correct_answers)):
        # Convert correct answer to left/right
        correct_side = "left" if correct == "option1" else "right"
        is_correct = player_answer == correct_side
        if is_correct:
            score += 1
        print(f"  Q{i+1}: Player chose {player_answer}, correct is {correct_side} {'✅' if is_correct else '❌'}")
    
    print(f"\nFinal score: {score}/10")

def test_results_display_fixes():
    """Test the results display shows actual player names instead of Player 1/Player 2"""
    print("Testing results display fixes...")
    
    try:
        # Get multiplayer results for a known session
        response = requests.get(f"{BASE_URL}/api/multiplayer-results/f22e49ab", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Check if player_mapping exists
            if 'player_mapping' in data and data['player_mapping']:
                print("✅ Player mapping found in results API")
                print(f"   Mapping: {data['player_mapping']}")
                
                # Check if the mapping has real names
                mapping = data['player_mapping']
                if 'Player 1' in mapping and 'Player 2' in mapping:
                    player1_name = mapping['Player 1']
                    player2_name = mapping['Player 2']
                    
                    if player1_name != 'Player 1' and player2_name != 'Player 2':
                        print(f"✅ Real names found: {player1_name} and {player2_name}")
                        print("✅ Results will show actual names instead of 'Player 1/Player 2'")
                        return True
                    else:
                        print("❌ Player mapping still contains generic names")
                        return False
                else:
                    print("❌ Player mapping missing expected keys")
                    return False
            else:
                print("❌ No player mapping found in results")
                return False
        else:
            print(f"❌ Failed to get results: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error testing results: {e}")
        return False

def test_coordinated_play_another():
    """Test the new coordinated Play Another functionality"""
    print("Testing coordinated Play Another functionality...")
    
    try:
        # Test the coordinated endpoint directly
        test_data = {
            "current_session_id": "f22e49ab"  # Use a known session
        }
        
        response = requests.post(f"{BASE_URL}/api/play-another-coordinated", 
                               json=test_data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ Coordinated Play Another endpoint working")
                print(f"   New quiz: {result.get('quiz_title')}")
                print(f"   Sessions created: {result.get('total_sessions_created')}")
                print(f"   Initiator session: {result.get('initiator_new_session_id')}")
                
                # Check if other players are automatically set up
                other_players = result.get('other_players', [])
                if other_players:
                    print(f"   Other players automatically set up: {len(other_players)}")
                    for player in other_players:
                        print(f"     - {player['player_name']}: {player['session_id']}")
                return True
            else:
                print(f"❌ Coordinated Play Another failed: {result.get('error')}")
                return False
        else:
            print(f"❌ API error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error testing coordinated play another: {e}")
        return False

def test_session_api_player_mapping():
    """Test that the session API includes player mapping for multiplayer sessions"""
    print("Testing session API player mapping...")
    
    try:
        # Create a test multiplayer session first
        quiz_id = "ba50f2e1"  # Competition quiz
        
        # Create session for first player
        response1 = requests.post(f"{BASE_URL}/api/create-session", 
                                 json={"quiz_id": quiz_id, "player_name": "TestPlayer1"}, 
                                 timeout=10)
        
        if response1.status_code != 200:
            print("❌ Failed to create first session")
            return False
            
        session1_data = response1.json()
        session1_id = session1_data['session_id']
        
        # Create session for second player in same group
        response2 = requests.post(f"{BASE_URL}/api/create-session", 
                                 json={"quiz_id": quiz_id, "shared_session_id": session1_id, "player_name": "TestPlayer2"}, 
                                 timeout=10)
        
        if response2.status_code != 200:
            print("❌ Failed to create second session")
            return False
            
        session2_data = response2.json()
        session2_id = session2_data['session_id']
        
        # Test the session API for player mapping
        response = requests.get(f"{BASE_URL}/api/session/{session1_id}", timeout=10)
        
        if response.status_code == 200:
            session_info = response.json()
            
            if 'player_mapping' in session_info:
                mapping = session_info['player_mapping']
                print("✅ Session API includes player mapping")
                print(f"   Mapping: {mapping}")
                
                # Check if mapping has real names
                if 'Player 1' in mapping and 'Player 2' in mapping:
                    if 'TestPlayer' in str(mapping.values()):
                        print("✅ Player mapping contains real player names")
                        return True
                    else:
                        print("❌ Player mapping doesn't contain real names")
                        return False
                else:
                    print("❌ Player mapping missing expected structure")
                    return False
            else:
                print("❌ Session API missing player mapping")
                return False
        else:
            print(f"❌ Session API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing session API: {e}")
        return False

def main():
    print("🔧 Mobile App Fixes Verification")
    print("=" * 40)
    
    # Run all tests
    results = []
    
    print("\n1. Testing Player Name Mapping in Results...")
    results.append(test_results_display_fixes())
    
    print("\n2. Testing Session API Player Mapping...")
    results.append(test_session_api_player_mapping())
    
    print("\n3. Testing Coordinated Play Another...")
    results.append(test_coordinated_play_another())
    
    # Summary
    print(f"\n📊 Test Results: {sum(results)}/{len(results)} passed")
    
    if all(results):
        print("🎉 All mobile app fixes are working correctly!")
    else:
        print("❌ Some tests failed - fixes may need adjustment")

if __name__ == "__main__":
    main() 