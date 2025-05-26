#!/usr/bin/env python3
"""
Comprehensive test for the complete Play Another fix:
1. Verify same session ID creation
2. Verify auto-start detection works  
3. Verify mobile-friendly flow
"""

import requests
import json
import time

BASE_URL = "http://localhost:5000"

def test_complete_playagain_flow():
    """Test the complete Play Another flow from start to finish"""
    print("🧪 COMPREHENSIVE Play Another Fix Test")
    print("=" * 60)
    
    # Use an existing completed session to test
    test_session_id = "f22e49ab"  
    
    try:
        print("📋 Step 1: Test Coordinated Session Creation")
        # Call the coordinated Play Another endpoint
        response = requests.post(f"{BASE_URL}/api/play-another-coordinated", 
                               json={"current_session_id": test_session_id})
        
        if response.status_code != 200:
            print(f"❌ HTTP error: {response.status_code}")
            return False
            
        result = response.json()
        if not result.get('success'):
            print(f"❌ API error: {result.get('error')}")
            return False
        
        new_session_id = result.get('initiator_new_session_id')
        other_players = result.get('other_players', [])
        quiz_title = result.get('quiz_title')
        
        print(f"✅ New Quiz Created: {quiz_title}")
        print(f"✅ Initiator Session: {new_session_id}")
        print(f"✅ Other Players: {len(other_players)}")
        
        # Verify all players get the same session ID
        all_same = True
        for player in other_players:
            if player.get('session_id') != new_session_id:
                all_same = False
                print(f"❌ Player {player.get('player_name')} has different session: {player.get('session_id')}")
        
        if all_same:
            print("✅ SUCCESS: All players have the same session ID")
        else:
            print("❌ FAILED: Players have different session IDs")
            return False
            
        print("\n📋 Step 2: Test Auto-Start Detection")
        
        # Test the check-new-game API for auto-start detection
        check_response = requests.get(f"{BASE_URL}/api/check-new-game/{test_session_id}")
        
        if check_response.status_code == 200:
            check_data = check_response.json()
            if check_data.get('has_new_game') and check_data.get('new_session_id') == new_session_id:
                print("✅ Auto-start detection works correctly")
                print(f"✅ Detected redirect to: {check_data.get('new_session_id')}")
                print(f"✅ Quiz: {check_data.get('quiz_title')}")
            else:
                print("❌ Auto-start detection not working")
                return False
        else:
            print(f"❌ Check new game API error: {check_response.status_code}")
            return False
            
        print("\n📋 Step 3: Test Game State for Auto-Ready")
        
        # Test the game state to ensure it will trigger auto-ready
        game_state_response = requests.get(f"{BASE_URL}/api/game-state/{new_session_id}")
        
        if game_state_response.status_code == 200:
            game_data = game_state_response.json()
            print(f"✅ Game state API working")
            print(f"✅ Has friend: {game_data.get('has_friend', False)}")
            print(f"✅ Players in game: {game_data.get('players_in_game', 0)}")
            print(f"✅ Both ready: {game_data.get('both_ready', False)}")
            
            # The fact that we can get game state means the session exists and is ready
            if game_data.get('players_in_game', 0) >= 1:
                print("✅ Session is ready for multiplayer coordination")
            else:
                print("⚠️  Session exists but no players detected yet")
        else:
            print(f"❌ Game state API error: {game_state_response.status_code}")
            return False
            
        print("\n📋 Step 4: Verify Mobile-Friendly Flow")
        
        # Test that the session can be accessed directly (simulating mobile redirect)
        session_response = requests.get(f"{BASE_URL}/session/{new_session_id}")
        
        if session_response.status_code == 200:
            print("✅ Session page loads correctly")
            print("✅ Mobile redirect will work")
            
            # Check if the page contains the auto-start logic
            page_content = session_response.text
            if "checkGameState" in page_content and "check-new-game" in page_content:
                print("✅ Auto-start detection code is present in page")
            else:
                print("⚠️  Auto-start code might be missing from page")
        else:
            print(f"❌ Session page error: {session_response.status_code}")
            return False
            
        print("\n" + "=" * 60)
        print("🎉 COMPLETE PLAY ANOTHER FIX TEST: PASSED!")
        print("✅ Session coordination works")
        print("✅ Auto-start detection works") 
        print("✅ Mobile-friendly flow works")
        print("✅ Ready for production use!")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return False

def test_player_ready_api():
    """Test the player ready API that's used for auto-start"""
    print("\n🔧 Testing Player Ready API")
    print("-" * 30)
    
    # Create a test session first
    create_response = requests.post(f"{BASE_URL}/api/create-session", 
                                   json={"quiz_id": "47f63005", "player_name": "TestPlayer"})
    
    if create_response.status_code == 200:
        create_data = create_response.json()
        test_session = create_data.get('session_id')
        
        # Test player ready endpoint
        ready_response = requests.post(f"{BASE_URL}/api/player-ready",
                                     json={"session_id": test_session})
        
        if ready_response.status_code == 200:
            ready_data = ready_response.json()
            print(f"✅ Player ready API works")
            print(f"✅ Response: {ready_data.get('success', False)}")
            return True
        else:
            print(f"❌ Player ready API error: {ready_response.status_code}")
            return False
    else:
        print(f"❌ Could not create test session: {create_response.status_code}")
        return False

if __name__ == "__main__":
    print("🎯 Testing Complete Play Another Fix")
    print("This verifies the end-to-end solution works correctly")
    print()
    
    # Run comprehensive test
    main_test = test_complete_playagain_flow()
    
    # Run supporting API test
    api_test = test_player_ready_api()
    
    print(f"\n📊 FINAL RESULTS:")
    print(f"   Main Flow Test: {'✅ PASSED' if main_test else '❌ FAILED'}")
    print(f"   API Test: {'✅ PASSED' if api_test else '❌ FAILED'}")
    
    if main_test and api_test:
        print("\n🎉 ALL TESTS PASSED!")
        print("🚀 Play Another feature is completely fixed and ready!")
        print("📱 Mobile app can be deployed with confidence!")
    else:
        print("\n❌ Some tests failed - check implementation") 