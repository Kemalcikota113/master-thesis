#!/bin/bash
# Kill any Vite processes running on port 5173

echo "Checking for processes on port 5173..."

# Find process using port 5173
PID=$(lsof -ti:5173)

if [ -z "$PID" ]; then
    echo "✅ No process found on port 5173"
else
    echo "Found process(es): $PID"
    echo "Killing process(es)..."
    kill -9 $PID
    echo "✅ Port 5173 is now free"
fi

# Also kill any orphaned npm/vite processes
echo ""
echo "Checking for orphaned Vite processes..."
pkill -f "vite.*todomvc-es6-vue" && echo "✅ Killed orphaned Vite processes" || echo "✅ No orphaned processes found"
