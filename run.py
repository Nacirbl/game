#!/usr/bin/env python3
"""
FastAPI startup script for This or That Quiz App
"""
import os
import sys
import uvicorn

if __name__ == '__main__':
    # Set development environment
    os.environ.setdefault('APP_ENV', 'development')
    
    print("🚀 Starting This or That Quiz App (FastAPI)...")
    print("📝 Admin (Create Quiz): http://localhost:2000/admin")
    print("🎮 Home Page: http://localhost:2000/")
    print("📊 API Documentation: http://localhost:2000/docs")
    print("\n✨ Features:")
    print("   • FastAPI with native WebSockets")
    print("   • Type-safe with Pydantic models")
    print("   • Async/await for better performance")
    print("   • Auto-generated API documentation")
    print("   • Optimized session management with DiskCache")
    print("   • AI-powered question generation")
    print("   • Image-to-quiz conversion")
    print("   • Real-time multiplayer support")
    print("\nPress Ctrl+C to stop the server\n")
    
    try:
        # Determine environment
        is_production = os.environ.get('APP_ENV') == 'production'
        
        if is_production:
            print("Running in PRODUCTION mode...")
            # In-memory connection manager and pending invites only work
            # within a single process - use Redis for multi-worker scaling
            use_redis = os.environ.get('USE_REDIS', 'false').lower() == 'true'
            workers = 4 if use_redis else 1
            uvicorn.run(
                "app:app",
                host="0.0.0.0",
                port=2000,
                workers=workers,
                log_level="info"
            )
        else:
            print("Running in DEVELOPMENT mode with auto-reload...")
            uvicorn.run(
                "app:app",
                host="0.0.0.0",
                port=2000,
                reload=True,
                log_level="debug"
            )
    except KeyboardInterrupt:
        print("\n👋 Thanks for using This or That Quiz App!")
        sys.exit(0)