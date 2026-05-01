#!/bin/bash
# Start backend, frontend (dev), and ngrok tunnel

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NGROK_DOMAIN="cuddle-huff-uncurious.ngrok-free.dev"

echo "Starting backend (FastAPI) on :8000 ..."
cd "$SCRIPT_DIR/backend"
python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Starting frontend (Vite) on :5173 ..."
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo "Starting ngrok tunnel → https://$NGROK_DOMAIN ..."
ngrok http --domain="$NGROK_DOMAIN" 8000 > /tmp/ngrok.log 2>&1 &
NGROK_PID=$!

echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo "  Public:   https://$NGROK_DOMAIN"
echo ""
echo "Press Ctrl+C to stop all."

trap "kill $BACKEND_PID $FRONTEND_PID $NGROK_PID 2>/dev/null" EXIT INT TERM
wait
