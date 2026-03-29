#!/bin/bash
# Start both backend and frontend

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting backend (FastAPI) on :8000 ..."
cd "$SCRIPT_DIR"
python3 -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Starting frontend (Vite) on :5173 ..."
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT INT TERM
wait
