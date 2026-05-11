#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi
PORT=${PORT:-8765}
nohup .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port "$PORT" > nohup.out 2>&1 &
echo $! > .pid
sleep 1
echo "bili-multiview started on port $PORT, pid $(cat .pid)"
echo "log: $(pwd)/nohup.out"
