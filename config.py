"""Environment-driven settings. No classes, no per-env variants."""
import os

# Admin gate for the quiz-builder page (client-checked; see notes in README)
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'malenanacir')

# LLM (OpenAI-compatible endpoint used for question generation)
DEEPINFRA_API_KEY = os.environ.get('DEEPINFRA_API_KEY', '')
DEEPINFRA_BASE_URL = os.environ.get(
    'DEEPINFRA_BASE_URL', 'https://api.deepinfra.com/v1/openai/')
LLM_MODEL = os.environ.get('LLM_MODEL', 'google/gemma-3-27b-it')

# Sessions (sliding TTL, renewed on activity)
SESSION_TTL = int(os.environ.get('SESSION_TTL', 21600))   # 6 hours
