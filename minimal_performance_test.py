#!/usr/bin/env python3
"""Minimal performance test to isolate bottlenecks"""

import requests
import time

def test_single_session():
    """Test creating a single session to measure baseline"""
    base_url = "http://localhost:5000"
    
    # Get quiz list
    print("Testing individual operations...")
    
    start = time.time()
    response = requests.get(f"{base_url}/api/quizzes", timeout=10)
    quiz_list_time = time.time() - start
    print(f"Quiz list fetch: {quiz_list_time*1000:.0f}ms")
    
    if response.status_code != 200:
        print("❌ Failed to get quiz list")
        return
    
    quizzes = response.json()
    if not quizzes:
        print("❌ No quizzes available")
        return
    
    quiz_id = quizzes[0]['id']
    
    # Create single session
    start = time.time()
    response = requests.post(
        f"{base_url}/api/create-session",
        json={'quiz_id': quiz_id, 'player_name': 'TestPlayer'},
        timeout=10
    )
    session_creation_time = time.time() - start
    print(f"Single session creation: {session_creation_time*1000:.0f}ms")
    
    if response.status_code != 200:
        print(f"❌ Failed to create session: {response.status_code}")
        return
    
    result = response.json()
    if not result.get('success'):
        print(f"❌ Session creation failed: {result.get('error')}")
        return
    
    session_id = result['session_id']
    
    # Get session data
    start = time.time()
    response = requests.get(f"{base_url}/api/session/{session_id}", timeout=10)
    session_get_time = time.time() - start
    print(f"Session data fetch: {session_get_time*1000:.0f}ms")
    
    # Get session stats
    start = time.time()
    response = requests.get(f"{base_url}/api/session-stats", timeout=10)
    stats_time = time.time() - start
    print(f"Session stats: {stats_time*1000:.0f}ms")
    
    print(f"\nTotal time for complete flow: {(quiz_list_time + session_creation_time + session_get_time + stats_time)*1000:.0f}ms")

if __name__ == "__main__":
    time.sleep(2)  # Wait for Flask to start
    test_single_session() 