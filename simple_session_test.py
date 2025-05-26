#!/usr/bin/env python3
"""
Simple Session Creation Test
Test to isolate session creation performance issues
"""

import requests
import time
import json

def test_single_session_creation():
    """Test creating a single session to measure baseline performance"""
    base_url = "http://localhost:5000"
    
    # Get a quiz to use
    try:
        response = requests.get(f"{base_url}/api/quizzes", timeout=5)
        quizzes = response.json()
        if not quizzes:
            print("❌ No quizzes available")
            return
        quiz_id = quizzes[0]['id']
        print(f"Using quiz: {quizzes[0]['title']} (ID: {quiz_id})")
    except Exception as e:
        print(f"❌ Error getting quizzes: {e}")
        return
    
    print("\n🔍 Testing Single Session Creation Performance")
    print("=" * 50)
    
    # Test single session creation
    for i in range(5):
        print(f"\nTest {i+1}/5:")
        start_time = time.time()
        
        try:
            response = requests.post(
                f"{base_url}/api/create-session",
                json={
                    'quiz_id': quiz_id,
                    'player_name': f'TestPlayer{i}'
                },
                timeout=10
            )
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print(f"   ✅ Session created: {result['session_id']}")
                    print(f"   ⏱️  Response time: {response_time*1000:.0f}ms")
                else:
                    print(f"   ❌ Session creation failed: {result.get('error')}")
            else:
                print(f"   ❌ HTTP error {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Request error: {e}")
        
        # Small delay between tests
        time.sleep(0.5)

def check_session_stats():
    """Check current session statistics"""
    base_url = "http://localhost:5000"
    
    print("\n📊 Current Session Statistics")
    print("=" * 30)
    
    try:
        response = requests.get(f"{base_url}/api/session-stats", timeout=5)
        if response.status_code == 200:
            stats = response.json()['stats']
            print(f"Active sessions: {stats['active_sessions_count']}")
            print(f"Ready states: {stats['ready_states_count']}")
            print(f"Quiz requests: {stats['quiz_requests_count']}")
            print(f"Group choices: {stats['group_choices_count']}")
            print(f"Unique groups: {stats['unique_groups']}")
            print(f"Solo sessions: {stats['solo_sessions']}")
            print(f"Multiplayer groups: {stats['multiplayer_groups']}")
            print(f"Average session age: {stats['session_age_stats']['avg_age_seconds']:.0f}s")
        else:
            print(f"❌ Failed to get stats: {response.status_code}")
    except Exception as e:
        print(f"❌ Error getting stats: {e}")

if __name__ == "__main__":
    check_session_stats()
    test_single_session_creation()
    check_session_stats() 