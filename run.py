#!/usr/bin/env python3
"""
Development startup script for This or That Quiz App
"""
import os
import sys
from app import app

if __name__ == '__main__':
    # Set development environment
    os.environ['FLASK_ENV'] = 'development'
    
    print("🚀 Starting This or That Quiz App...")
    print("📝 Admin (Create Quiz): http://localhost:5000/admin")
    print("🎮 Home Page: http://localhost:5000/")
    print("📊 Results Viewer: http://localhost:5000/results")
    print("\n✨ Features:")
    print("   • Optimized session management with DiskCache")
    print("   • Test mode for quiz creators (?test=true)")
    print("   • AI-powered question generation")
    print("   • Image-to-quiz conversion")
    print("   • Real-time multiplayer support")
    print("   • Improved performance and caching")
    print("\nPress Ctrl+C to stop the server\n")
    
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\n👋 Thanks for using This or That Quiz App!")
        sys.exit(0) 