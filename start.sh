#!/usr/bin/env bash
set -e

while true; do
  echo "▶️  Starting monitor.py at $(date)"
  python monitor.py
  echo "⚠️  monitor.py exited with code $? — restarting in 5s" >&2
  sleep 5
done
