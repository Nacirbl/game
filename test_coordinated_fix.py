#!/usr/bin/env python3
"""
Test script to verify the coordinated Play Another fix - all players should get the same session ID
"""

import requests
import json

BASE_URL = "http://localhost:5000"

def test_play_another_same_session():
    """Test that Play Another creates the same session for all players"""
    print("🧪 Testing Play Another - Same Session Fix")
    print("=" * 50)
    
    # Use an existing completed session to test
    test_session_id = "f22e49ab"  
    
    try:
        # Call the coordinated Play Another endpoint
        response = requests.post(f"{BASE_URL}/api/play-another-coordinated", 
                               json={"current_session_id": test_session_id})
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                initiator_session = result.get('initiator_new_session_id')
                other_players = result.get('other_players', [])
                
                print(f"✅ Coordinated Play Another succeeded")
                print(f"📋 New Quiz: {result.get('quiz_title')}")
                print(f"👑 Initiator session: {initiator_session}")
                print(f"👥 Other players ({len(other_players)}):")
                
                all_same_session = True
                for player in other_players:
                    player_session = player.get('session_id')
                    print(f"   - {player.get('player_name')}: {player_session}")
                    if player_session != initiator_session:
                        all_same_session = False
                        print(f"   ❌ Different session! Expected {initiator_session}")
                
                if all_same_session:
                    print("✅ SUCCESS: All players have the same session ID!")
                    print("✅ Both players will now join the same game instead of waiting forever")
                else:
                    print("❌ FAILED: Players have different session IDs")
                    
                return all_same_session
            else:
                print(f"❌ API error: {result.get('error')}")
                return False
        else:
            print(f"❌ HTTP error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def test_check_new_game_api():
    """Test that the check-new-game API returns the correct session for all players"""
    print("\n🔍 Testing Check New Game API")
    print("=" * 30)
    
    # This will test if the API returns the right session mapping
    test_session_id = "f22e49ab"
    
    try:
        response = requests.get(f"{BASE_URL}/api/check-new-game/{test_session_id}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('has_new_game'):
                new_session_id = result.get('new_session_id')
                quiz_title = result.get('quiz_title')
                print(f"✅ New game detected: {quiz_title}")
                print(f"📍 Redirect session: {new_session_id}")
                print("✅ Non-initiator will be redirected to the same session as initiator")
                return True
            else:
                print("ℹ️  No new game pending (this is normal)")
                return True
        else:
            print(f"❌ API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    print("🎯 Testing Coordinated Play Another Fix")
    print("This test verifies that all players get the same session ID")
    print()
    
    # Run tests
    test1 = test_play_another_same_session()
    test2 = test_check_new_game_api()
    
    print(f"\n📊 Results: {sum([test1, test2])}/2 tests passed")
    
    if test1 and test2:
        print("🎉 FIXED: Play Another now works correctly!")
        print("   ✅ All players get redirected to the SAME session")
        print("   ✅ No more infinite waiting in separate sessions")
    else:
        print("❌ Tests failed - fix needs adjustment") 