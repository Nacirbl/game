#!/usr/bin/env python3
"""
Test script to verify player mapping is working in the session API
"""

import requests
import json
import time

BASE_URL = "http://localhost:5000"

def test_player_mapping():
    print("🧪 Testing Player Mapping in Session API...")
    
    try:
        # Create two sessions for multiplayer with player quiz
        quiz_id = "ba50f2e1"  # Use the competition quiz
        
        # Create session for Player 1 (Nacir)
        response1 = requests.post(f"{BASE_URL}/api/create-session", 
                                 json={"quiz_id": quiz_id, "player_name": "Nacir"}, 
                                 timeout=10)
        
        if response1.status_code != 200:
            print("❌ Failed to create session 1")
            return
            
        session1_data = response1.json()
        session1_id = session1_data['session_id']
        print(f"✅ Created session 1: {session1_id} for Nacir")
        
        # Create session for Player 2 (Malena) - join the same group
        response2 = requests.post(f"{BASE_URL}/api/create-session", 
                                 json={"quiz_id": quiz_id, "player_name": "Malena", "shared_session_id": session1_id}, 
                                 timeout=10)
        
        if response2.status_code != 200:
            print("❌ Failed to create session 2")
            return
            
        session2_data = response2.json()
        session2_id = session2_data['session_id']
        print(f"✅ Created session 2: {session2_id} for Malena")
        
        # Test session API for player 1 - should include player mapping
        response = requests.get(f"{BASE_URL}/api/session/{session1_id}", timeout=10)
        
        if response.status_code == 200:
            session_data = response.json()
            if 'player_mapping' in session_data:
                print("✅ Player mapping found in session API!")
                print(f"   Player mapping: {session_data['player_mapping']}")
                
                # Check if it has the actual names
                mapping = session_data['player_mapping']
                if 'Nacir' in str(mapping) or 'Malena' in str(mapping):
                    print("✅ Actual player names found in mapping!")
                else:
                    print("❌ Generic names still being used")
                    
            else:
                print("❌ No player_mapping in session API response")
                print("Session keys:", list(session_data.keys()))
        else:
            print(f"❌ Session API failed: {response.status_code}")
            
        # Test with a quiz that has "Player 1" and "Player 2" in questions
        print("\n🧪 Testing with a 'player' type quiz...")
        
        # First, let's create a player-type quiz
        player_quiz_data = {
            "title": "Test Player Quiz",
            "type": "player",
            "questions": [
                {
                    "prompt": "Who wakes up earlier?",
                    "option1": "Player 1",
                    "option2": "Player 2"
                },
                {
                    "prompt": "Who is more organized?",
                    "option1": "Player 1", 
                    "option2": "Player 2"
                }
            ]
        }
        
        # Create the quiz
        quiz_response = requests.post(f"{BASE_URL}/api/create_quiz", 
                                    json=player_quiz_data, 
                                    timeout=10)
        
        if quiz_response.status_code == 200:
            player_quiz_id = quiz_response.json()['quiz_id']
            print(f"✅ Created player quiz: {player_quiz_id}")
            
            # Create sessions for this player quiz
            response3 = requests.post(f"{BASE_URL}/api/create-session", 
                                     json={"quiz_id": player_quiz_id, "player_name": "Nacir"}, 
                                     timeout=10)
            
            if response3.status_code == 200:
                session3_data = response3.json()
                session3_id = session3_data['session_id']
                
                response4 = requests.post(f"{BASE_URL}/api/create-session", 
                                         json={"quiz_id": player_quiz_id, "player_name": "Malena", "shared_session_id": session3_id}, 
                                         timeout=10)
                
                if response4.status_code == 200:
                    session4_data = response4.json()
                    session4_id = session4_data['session_id']
                    
                    # Test the session API for this player quiz
                    player_session_response = requests.get(f"{BASE_URL}/api/session/{session3_id}", timeout=10)
                    
                    if player_session_response.status_code == 200:
                        player_session_data = player_session_response.json()
                        if 'player_mapping' in player_session_data:
                            print("✅ Player mapping in player quiz session!")
                            print(f"   Questions preview: {player_session_data['questions'][0]['prompt']}")
                            print(f"   Player mapping: {player_session_data['player_mapping']}")
                        else:
                            print("❌ No player mapping in player quiz session")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")

if __name__ == "__main__":
    test_player_mapping() 