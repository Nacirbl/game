#!/usr/bin/env python3
"""
Performance test script for the new in-memory session management system.
This script simulates multiple concurrent users to test the robustness of the session system.
"""

import requests
import json
import time
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
import statistics

# Configuration
BASE_URL = "http://localhost:5000"
NUM_CONCURRENT_USERS = 20
NUM_QUESTIONS_PER_QUIZ = 5
TEST_DURATION = 30  # seconds

def create_test_quiz():
    """Create a test quiz for performance testing"""
    quiz_data = {
        "title": f"Performance Test Quiz {uuid.uuid4().hex[:8]}",
        "description": "Auto-generated quiz for performance testing",
        "type": "thisorthat",
        "questions": [
            {
                "prompt": f"Question {i+1}?",
                "option1": f"Option A{i+1}",
                "option2": f"Option B{i+1}"
            }
            for i in range(NUM_QUESTIONS_PER_QUIZ)
        ]
    }
    
    response = requests.post(f"{BASE_URL}/api/create_quiz", json=quiz_data)
    if response.status_code == 200:
        return response.json()["quiz_id"]
    return None

def simulate_user_session(quiz_id, user_id):
    """Simulate a complete user session"""
    start_time = time.time()
    
    try:
        # Create session
        session_response = requests.post(f"{BASE_URL}/api/create-session", json={
            "quiz_id": quiz_id,
            "player_name": f"TestUser{user_id}"
        })
        
        if session_response.status_code != 200:
            return {"error": "Failed to create session", "user_id": user_id}
        
        session_id = session_response.json()["session_id"]
        
        # Answer all questions
        for question_idx in range(NUM_QUESTIONS_PER_QUIZ):
            answer = "left" if question_idx % 2 == 0 else "right"
            
            answer_response = requests.post(
                f"{BASE_URL}/api/session/{session_id}/answer",
                json={"answer": answer}
            )
            
            if answer_response.status_code != 200:
                return {
                    "error": f"Failed to submit answer {question_idx}",
                    "user_id": user_id,
                    "session_id": session_id
                }
            
            # Small delay between questions to simulate real usage
            time.sleep(0.1)
        
        end_time = time.time()
        return {
            "success": True,
            "user_id": user_id,
            "session_id": session_id,
            "duration": end_time - start_time
        }
        
    except Exception as e:
        return {"error": str(e), "user_id": user_id}

def get_health_stats():
    """Get current health and session statistics"""
    try:
        response = requests.get(f"{BASE_URL}/api/health")
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def run_performance_test():
    """Run the performance test"""
    print("🚀 Starting Session Management Performance Test")
    print(f"📊 Test Configuration:")
    print(f"   • Concurrent Users: {NUM_CONCURRENT_USERS}")
    print(f"   • Questions per Quiz: {NUM_QUESTIONS_PER_QUIZ}")
    print(f"   • Base URL: {BASE_URL}")
    print()
    
    # Check if server is running
    try:
        health = get_health_stats()
        if health:
            print(f"✅ Server is healthy")
            print(f"   • Active Sessions: {health.get('active_sessions', 0)}")
            print(f"   • Session Timeout: {health.get('session_timeout', 0)}s")
        else:
            print("❌ Server health check failed")
            return
    except Exception as e:
        print(f"❌ Could not connect to server: {e}")
        return
    
    print()
    
    # Create test quiz
    print("📝 Creating test quiz...")
    quiz_id = create_test_quiz()
    if not quiz_id:
        print("❌ Failed to create test quiz")
        return
    
    print(f"✅ Test quiz created: {quiz_id}")
    print()
    
    # Run concurrent user sessions
    print(f"👥 Starting {NUM_CONCURRENT_USERS} concurrent user sessions...")
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=NUM_CONCURRENT_USERS) as executor:
        # Submit all user session tasks
        futures = [
            executor.submit(simulate_user_session, quiz_id, user_id)
            for user_id in range(NUM_CONCURRENT_USERS)
        ]
        
        # Collect results
        results = []
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
    
    end_time = time.time()
    total_test_time = end_time - start_time
    
    # Analyze results
    successful_sessions = [r for r in results if r.get('success')]
    failed_sessions = [r for r in results if not r.get('success')]
    
    print(f"⏱️  Total test time: {total_test_time:.2f} seconds")
    print(f"✅ Successful sessions: {len(successful_sessions)}/{NUM_CONCURRENT_USERS}")
    print(f"❌ Failed sessions: {len(failed_sessions)}")
    
    if successful_sessions:
        durations = [r['duration'] for r in successful_sessions]
        print(f"📈 Session Performance:")
        print(f"   • Average duration: {statistics.mean(durations):.2f}s")
        print(f"   • Median duration: {statistics.median(durations):.2f}s")
        print(f"   • Min duration: {min(durations):.2f}s")
        print(f"   • Max duration: {max(durations):.2f}s")
    
    if failed_sessions:
        print(f"❌ Failed sessions details:")
        for failure in failed_sessions[:5]:  # Show first 5 failures
            print(f"   • User {failure.get('user_id')}: {failure.get('error')}")
    
    # Final health check
    print()
    final_health = get_health_stats()
    if final_health:
        print(f"📊 Final server stats:")
        print(f"   • Active Sessions: {final_health.get('active_sessions', 0)}")
        print(f"   • Status: {final_health.get('status', 'unknown')}")
    
    print()
    if len(successful_sessions) == NUM_CONCURRENT_USERS:
        print("🎉 All sessions completed successfully! The session manager is working great.")
    elif len(successful_sessions) > NUM_CONCURRENT_USERS * 0.8:
        print("✅ Most sessions completed successfully. Good performance!")
    else:
        print("⚠️  Many sessions failed. Check the server logs for issues.")

if __name__ == "__main__":
    run_performance_test() 