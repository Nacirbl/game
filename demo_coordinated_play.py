#!/usr/bin/env python3
"""
Demo script showing the new coordinated "Play Another" functionality.

This demonstrates how:
1. No browser notifications are needed
2. All players get the same quiz automatically
3. Automatic invitation system for mobile apps
"""

import requests
import json
import time

BASE_URL = "http://localhost:5000"

def demo_coordinated_play_another():
    print("🎮 Demonstrating Coordinated Play Another System")
    print("=" * 50)
    
    # Simulate Player 1 completing a game
    print("\n1. Simulating Player 1 finishing a quiz...")
    test_session_id = "f22e49ab"  # Known completed session
    
    print(f"   Player 1 session: {test_session_id}")
    
    # Player 1 clicks "Play Another"
    print("\n2. Player 1 clicks 'Play Another' (initiates new game)...")
    
    response = requests.post(f"{BASE_URL}/api/play-another-coordinated", 
                           json={"current_session_id": test_session_id})
    
    if response.status_code == 200:
        result = response.json()
        if result.get('success'):
            print("✅ SUCCESS: New game coordinated for all players!")
            print(f"   📚 Quiz Selected: '{result['quiz_title']}'")
            print(f"   👥 Sessions Created: {result['total_sessions_created']}")
            print(f"   🔗 Player 1's New Session: {result['initiator_new_session_id']}")
            
            initiator_session = result['initiator_new_session_id']
            
            # Simulate other players checking for new games
            print("\n3. Other players automatically discover the new game...")
            time.sleep(1)  # Brief delay to simulate real-world scenario
            
            # Check if there's a new game for the original session
            check_response = requests.get(f"{BASE_URL}/api/check-new-game/{test_session_id}")
            if check_response.status_code == 200:
                check_result = check_response.json()
                if check_result.get('has_new_game'):
                    print("✅ SUCCESS: Other players see new game invitation!")
                    print(f"   📚 Game Available: '{check_result['quiz_title']}'")
                    print(f"   🔗 Their New Session: {check_result['new_session_id']}")
                    print(f"   👤 Initiated By: {check_result.get('initiated_by', 'Another player')}")
                    
                    # Demonstrate automatic joining (what happens when they click "Join Game")
                    print("\n4. Other players can join automatically...")
                    print(f"   🚀 Redirect to: /session/{check_result['new_session_id']}")
                    
                    # Verify the new session exists and has the same quiz
                    verify_response = requests.get(f"{BASE_URL}/api/session/{check_result['new_session_id']}")
                    if verify_response.status_code == 200:
                        session_data = verify_response.json()
                        print("✅ SUCCESS: New session is ready and playable!")
                        print(f"   📚 Quiz: {session_data.get('quiz_title', 'Unknown')}")
                        print(f"   📊 Questions: {len(session_data.get('questions', []))}")
                        print(f"   👥 Group ID: {session_data.get('shared_session_group')}")
                    else:
                        print("❌ ERROR: New session not accessible")
                else:
                    print("ℹ️  No new game detected (expected for demo)")
            else:
                print("❌ ERROR: Could not check for new games")
        else:
            print(f"❌ ERROR: {result.get('error')}")
    else:
        print(f"❌ ERROR: HTTP {response.status_code}")
    
    print("\n" + "=" * 50)
    print("🎯 Key Benefits of New System:")
    print("  • No browser notifications needed")
    print("  • All players get the SAME quiz automatically")
    print("  • Mobile-friendly invitation system")
    print("  • Automatic session coordination")
    print("  • Prevents race conditions")

if __name__ == "__main__":
    demo_coordinated_play_another() 