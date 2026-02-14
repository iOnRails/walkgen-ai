# WalkGen AI - Smart Video Game Walkthrough Generator

Paste a YouTube gameplay video URL, AI analyzes the transcript, and you get a searchable, timestamped walkthrough with boss fights, puzzles, collectibles, and more.

## Architecture

```
walkgen/
├── backend/
│   ├── main.py              # FastAPI app + endpoints
│   ├── config.py             # Environment config
│   ├── models.py             # Pydantic data models
│   ├── Dockerfile            # Docker build for Railway
│   ├── railway.json          # Railway deploy config
│   ├── requirements.txt
│   └── services/
│       ├── __init__.py
│       ├── youtube.py        # YouTube metadata + transcript extraction
│       ├── analyzer.py       # Claude-powered segment detection
│       └── cache.py          # SQLite caching layer
├── frontend/
│   ├── public/index.html
│   ├── src/
│   │   ├── App.jsx           # Main React app
│   │   ├── api.js            # API client
│   │   └── index.js          # Entry point
│   ├── package.json
│   └── vercel.json           # Vercel deploy config
├── .env.example
├── .gitignore
├── setup.sh                  # One-command local setup
├── SETUP_GUIDE.md            # Complete beginner deployment guide
└── README.md
```

## How It Works

1. User pastes a YouTube URL
2. Backend checks SQLite cache — if already analyzed, returns instantly (free)
3. If not cached: fetches video metadata via YouTube Data API
4. Extracts transcript/captions via `youtube-transcript-api`
5. Transcript is chunked and sent to Claude with a gaming-aware prompt
6. Claude identifies segments (boss, puzzle, exploration, collectible, etc.)
7. Result is cached in SQLite for future instant access
8. Frontend displays the interactive walkthrough with search, filters, and timeline

## Quick Start

### Option A: One-command setup
```bash
chmod +x setup.sh
./setup.sh
```

### Option B: Manual setup

```bash
# 1. Configure
cp .env.example .env
# Edit .env with your API keys

# 2. Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 3. Frontend (new terminal)
cd frontend
npm install
npm start
# Opens at http://localhost:3000
```

## API Keys Required

- **Anthropic API Key** — Powers the AI analysis (~$0.03/video). Get at console.anthropic.com
- **YouTube Data API Key** — Fetches video metadata (free, 10k requests/day). Get at console.cloud.google.com

The transcript extraction uses `youtube-transcript-api` which needs no API key.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/analyze` | Start analysis of a YouTube video |
| GET | `/api/status/{job_id}` | Check analysis progress |
| GET | `/api/walkthrough/{job_id}` | Get completed walkthrough |
| GET | `/api/browse/recent` | Recently analyzed walkthroughs |
| GET | `/api/browse/popular` | Most-viewed walkthroughs |
| GET | `/api/browse/search?q=` | Search cached walkthroughs |
| GET | `/api/health` | Health check + cache stats |

## Deploying to Production

See **SETUP_GUIDE.md** for a complete step-by-step guide. TL;DR:

- **Backend** → Railway (runs Python/FastAPI, ~$5/month)
- **Frontend** → Vercel (hosts React app, free)
- **Total cost** → ~$8/month for 100 videos

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Anthropic SDK, youtube-transcript-api
- **Frontend:** React 18, vanilla CSS
- **AI:** Claude Sonnet 4.5 via Anthropic API
- **Cache:** SQLite with WAL mode
- **Deploy:** Railway (backend) + Vercel (frontend)
