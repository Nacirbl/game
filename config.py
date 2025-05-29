import os
from datetime import timedelta
import secrets

class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Admin token for quiz creation (fixed for now)
    ADMIN_TOKEN = 'malenanacir'
    
    # Flask settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = 'uploads'
    
    # Session settings
    SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT', 3600))  # 1 hour
    SESSION_CLEANUP_INTERVAL = 300  # 5 minutes
    HEARTBEAT_TIMEOUT = 30  # seconds
    
    # Cache settings - using diskcache for persistence without Redis
    CACHE_TYPE = 'FileSystemCache'
    CACHE_DIR = 'cache'
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300))
    CACHE_THRESHOLD = 1000  # Maximum number of items the cache will store
    
    # Session storage
    SESSION_STORAGE_DIR = 'session_storage'
    
    # API settings
    DEEPINFRA_API_KEY = os.environ.get('DEEPINFRA_API_KEY', 'wtKCca7JOYrwt9EiOe7sKIzmNXa9kJWm')
    DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai/"
    LLM_MODEL_NAME = "google/gemma-3-27b-it"
    
    # Performance settings
    CONNECTION_POOL_SIZE = 10
    REQUEST_TIMEOUT = 30
    MAX_WORKERS = 4
    
    # Optimize file I/O
    USE_MEMORY_CACHE = True
    MEMORY_CACHE_SIZE = 100  # MB
    
class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    
class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    USE_MEMORY_CACHE = True
    MEMORY_CACHE_SIZE = 500  # MB for production
    
class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SESSION_TIMEOUT = 60  # Shorter timeout for tests
    
# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
} 