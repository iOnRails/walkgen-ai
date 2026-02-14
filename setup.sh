#!/bin/bash
# ─────────────────────────────────────────────
# WalkGen AI - Quick Setup Script
# Run this after cloning the repo to get started locally
# ─────────────────────────────────────────────

set -e

echo ""
echo "========================================"
echo "  WalkGen AI - Local Setup"
echo "========================================"
echo ""

# ── Check prerequisites ──
check_command() {
  if ! command -v "$1" &> /dev/null; then
    echo "ERROR: $1 is not installed."
    echo "  Install it first: $2"
    exit 1
  fi
}

check_command python3 "https://python.org/downloads"
check_command node "https://nodejs.org"
check_command npm "https://nodejs.org"

echo "[OK] Python3, Node, and npm are installed."

# ── Create .env file if it doesn't exist ──
if [ ! -f .env ]; then
  echo ""
  echo "Creating .env file from template..."

  read -p "Enter your Anthropic API key (sk-ant-...): " ANTHROPIC_KEY
  read -p "Enter your YouTube Data API key (AIza...): " YOUTUBE_KEY

  cat > .env << EOF
# WalkGen AI - Environment Variables
# Created by setup.sh on $(date)

ANTHROPIC_API_KEY=$ANTHROPIC_KEY
YOUTUBE_API_KEY=$YOUTUBE_KEY
CORS_ORIGINS=http://localhost:3000
EOF

  echo "[OK] .env file created."
else
  echo "[OK] .env file already exists."
fi

# ── Setup Backend ──
echo ""
echo "Setting up backend..."
cd backend

if [ ! -d "venv" ]; then
  python3 -m venv venv
  echo "[OK] Python virtual environment created."
fi

source venv/bin/activate
pip install -r requirements.txt --quiet
echo "[OK] Backend dependencies installed."

cd ..

# ── Setup Frontend ──
echo ""
echo "Setting up frontend..."
cd frontend
npm install --silent
echo "[OK] Frontend dependencies installed."
cd ..

# ── Done ──
echo ""
echo "========================================"
echo "  Setup Complete!"
echo "========================================"
echo ""
echo "To start the app locally:"
echo ""
echo "  Terminal 1 (Backend):"
echo "    cd backend"
echo "    source venv/bin/activate"
echo "    uvicorn main:app --reload --port 8000"
echo ""
echo "  Terminal 2 (Frontend):"
echo "    cd frontend"
echo "    npm start"
echo ""
echo "Then open http://localhost:3000"
echo ""
