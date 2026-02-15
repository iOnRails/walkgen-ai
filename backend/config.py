import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,https://walkgen-ai.vercel.app"
).split(",")

# Proxy for YouTube transcript fetching (YouTube blocks cloud IPs)
# Sign up free at https://www.webshare.io and get your proxy credentials
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")

# Claude model to use for analysis
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

# Max transcript length to send per chunk (in characters)
TRANSCRIPT_CHUNK_SIZE = 12000
