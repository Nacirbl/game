#!/usr/bin/env python3
"""Quick performance test for session creation"""

import requests
import time
import json
from concurrent.futures import ThreadPoolExecutor
import statistics

def test_session_creation_speed():
    """Test session creation speed after optimizations"""
    base_url = "http://localhost:5000"
    
    # Get a quiz to use
    try:
        response = requests.get(f"{base_url}/api/quizzes", timeout=5)
        quizzes = response.json()
        if not quizzes:
            print("❌ No quizzes available")
            return
        quiz_id = quizzes[0]['id']
        print(f"Using quiz: {quizzes[0]['title']}")
    except Exception as e:
        print(f"❌ Error getting quizzes: {e}")
        return
    
    print("\n🚀 Testing Session Creation Performance (After Optimization)")
    print("=" * 60)
    
    # Test 1: Sequential session creation (baseline)
    print("\n1. Sequential session creation (10 sessions)...")
    start_time = time.time()
    
    for i in range(10):
        response = requests.post(
            f"{base_url}/api/create-session",
            json={'quiz_id': quiz_id, 'player_name': f'SeqPlayer{i}'},
            timeout=10
        )
        if response.status_code != 200:
            print(f"❌ Failed to create session {i}")
    
    sequential_time = time.time() - start_time
    print(f"   Time: {sequential_time:.2f}s ({sequential_time/10*1000:.0f}ms per session)")
    
    # Test 2: Concurrent session creation
    print("\n2. Concurrent session creation (20 sessions, 5 threads)...")
    
    def create_session(thread_id):
        times = []
        for i in range(4):  # 4 sessions per thread = 20 total
            start = time.time()
            response = requests.post(
                f"{base_url}/api/create-session",
                json={'quiz_id': quiz_id, 'player_name': f'Thread{thread_id}_S{i}'},
                timeout=10
            )
            response_time = time.time() - start
            times.append(response_time)
            if response.status_code != 200:
                print(f"❌ Failed: Thread {thread_id}, Session {i}")
        return times
    
    start_time = time.time()
    all_times = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(create_session, i) for i in range(5)]
        for future in futures:
            all_times.extend(future.result())
    
    concurrent_time = time.time() - start_time
    print(f"   Total time: {concurrent_time:.2f}s")
    print(f"   Sessions per second: {20/concurrent_time:.1f}")
    print(f"   Average response time: {statistics.mean(all_times)*1000:.0f}ms")
    print(f"   95th percentile: {statistics.quantiles(all_times, n=20)[18]*1000:.0f}ms")
    
    # Test 3: Check session health
    print("\n3. Session health check...")
    response = requests.get(f"{base_url}/api/session-stats")
    if response.status_code == 200:
        stats = response.json()['stats']
        print(f"   Active sessions: {stats['active_sessions_count']}")
        print(f"   Average session age: {stats['session_age_stats']['avg_age_seconds']:.0f}s")
    else:
        print("   ❌ Failed to get session stats")
    
    # Performance assessment
    print(f"\n📊 PERFORMANCE ASSESSMENT:")
    avg_response_time = statistics.mean(all_times) * 1000
    sessions_per_sec = 20 / concurrent_time
    
    if avg_response_time < 500 and sessions_per_sec > 10:
        print("   ✅ EXCELLENT: Fast response times and good throughput")
    elif avg_response_time < 1000 and sessions_per_sec > 5:
        print("   ✅ GOOD: Acceptable performance for production use")
    elif avg_response_time < 2000:
        print("   ⚠️  FAIR: Performance could be improved")
    else:
        print("   ❌ POOR: Significant performance issues")
    
    return {
        'sequential_time_per_session': sequential_time / 10,
        'concurrent_avg_response_time': statistics.mean(all_times),
        'sessions_per_second': sessions_per_sec,
        'total_sessions_created': 30
    }

if __name__ == "__main__":
    # Wait a moment for Flask to start
    time.sleep(3)
    results = test_session_creation_speed()
    print(f"\n📁 Test completed successfully!") 