#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ -f ".pid" ]; then
    PID=$(cat .pid)
    if kill "$PID" 2>/dev/null; then
        echo "stopped pid $PID"
    else
        echo "pid $PID not running"
    fi
    rm -f .pid
else
    pkill -f "uvicorn main:app" && echo "killed via pkill" || echo "no process found"
fi
